from __future__ import annotations

import hashlib
import hmac
from datetime import timedelta

import requests
from requests.auth import HTTPBasicAuth

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .models import ProPayment, ProSubscription


PRO_PLAN_NAME = 'Vixogram Pro'
PRO_PRICE_INR = 399
PRO_AMOUNT_PAISE = 39900
PRO_DURATION_DAYS = 30


def _razorpay_keys():
    key_id = (getattr(settings, 'RAZORPAY_KEY_ID', '') or '').strip()
    key_secret = (getattr(settings, 'RAZORPAY_KEY_SECRET', '') or '').strip()
    return key_id, key_secret


def _create_or_reuse_razorpay_order(user):
    """Create (or reuse recent) Razorpay order and persist ProPayment row."""
    key_id, key_secret = _razorpay_keys()
    if not key_id or not key_secret:
        return None

    now = timezone.now()
    reuse_cutoff = now - timedelta(minutes=15)
    try:
        existing = (
            ProPayment.objects
            .filter(
                user=user,
                provider=ProPayment.PROVIDER_RAZORPAY,
                status=ProPayment.STATUS_CREATED,
                amount_paise=PRO_AMOUNT_PAISE,
                created_at__gte=reuse_cutoff,
            )
            .order_by('-created_at')
            .first()
        )
        if existing and existing.order_id:
            return existing
    except Exception:
        pass

    receipt = f"pro_{user.id}_{int(now.timestamp())}"
    payload = {
        'amount': int(PRO_AMOUNT_PAISE),
        'currency': 'INR',
        'receipt': receipt,
        'payment_capture': 1,
        'notes': {
            'user_id': str(user.id),
            'plan': PRO_PLAN_NAME,
        },
    }

    res = requests.post(
        'https://api.razorpay.com/v1/orders',
        json=payload,
        auth=HTTPBasicAuth(key_id, key_secret),
        timeout=20,
    )
    res.raise_for_status()
    data = res.json() if res.content else {}
    order_id = (data or {}).get('id')
    if not order_id:
        raise ValueError('Razorpay order id missing')

    payment = ProPayment.objects.create(
        user=user,
        provider=ProPayment.PROVIDER_RAZORPAY,
        status=ProPayment.STATUS_CREATED,
        amount_paise=int(PRO_AMOUNT_PAISE),
        currency='INR',
        order_id=str(order_id),
    )
    return payment


def _activate_subscription(user, provider: str, payment_id: str, order_id: str):
    now = timezone.now()
    sub, _ = ProSubscription.objects.get_or_create(user=user)

    extend_from = now
    try:
        if sub.status == ProSubscription.STATUS_ACTIVE and sub.expires_at and sub.expires_at > now:
            extend_from = sub.expires_at
    except Exception:
        extend_from = now

    if sub.status != ProSubscription.STATUS_ACTIVE or not sub.started_at or not sub.expires_at or sub.expires_at <= now:
        sub.started_at = now

    sub.status = ProSubscription.STATUS_ACTIVE
    sub.expires_at = extend_from + timedelta(days=int(PRO_DURATION_DAYS))
    sub.provider = provider or ''
    sub.last_payment_id = payment_id or ''
    sub.last_order_id = order_id or ''
    sub.save(update_fields=[
        'status',
        'started_at',
        'expires_at',
        'provider',
        'last_payment_id',
        'last_order_id',
        'updated_at',
    ])


@login_required
@require_GET
def pro_checkout_view(request):
    key_id, key_secret = _razorpay_keys()
    payment_enabled = bool(key_id and key_secret)

    payment = None
    if payment_enabled:
        try:
            payment = _create_or_reuse_razorpay_order(request.user)
        except Exception:
            payment = None
            payment_enabled = False

    ctx = {
        'plan_name': PRO_PLAN_NAME,
        'price_label': f"₹{PRO_PRICE_INR} / month",
        'bullets': [
            'Full AI access',
            'No ads',
            'Premium features',
        ],
        'trust_line': 'Cancel anytime',
        'payment_enabled': bool(payment_enabled),
        'razorpay_key_id': key_id,
        'razorpay_order_id': getattr(payment, 'order_id', ''),
        'amount_paise': int(PRO_AMOUNT_PAISE),
        'user_email': getattr(request.user, 'email', '') or '',
        'user_name': getattr(request.user, 'username', '') or '',
    }
    return render(request, 'pro/checkout.html', ctx)


@login_required
@require_POST
def pro_payment_complete_view(request):
    """Verify Razorpay signature and activate subscription."""
    key_id, key_secret = _razorpay_keys()
    if not key_id or not key_secret:
        return JsonResponse({'ok': False, 'error': 'Payments are not configured.'}, status=503)

    order_id = (request.POST.get('razorpay_order_id') or '').strip()
    payment_id = (request.POST.get('razorpay_payment_id') or '').strip()
    signature = (request.POST.get('razorpay_signature') or '').strip()

    if not order_id or not payment_id or not signature:
        return JsonResponse({'ok': False, 'error': 'Missing payment details.'}, status=400)

    try:
        pay = ProPayment.objects.filter(
            user=request.user,
            provider=ProPayment.PROVIDER_RAZORPAY,
            order_id=order_id,
        ).order_by('-created_at').first()
        if not pay:
            return JsonResponse({'ok': False, 'error': 'Order not found.'}, status=404)

        msg = f"{order_id}|{payment_id}".encode('utf-8')
        expected = hmac.new(key_secret.encode('utf-8'), msg, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            try:
                pay.status = ProPayment.STATUS_FAILED
                pay.payment_id = payment_id
                pay.signature = signature
                pay.save(update_fields=['status', 'payment_id', 'signature', 'updated_at'])
            except Exception:
                pass
            return JsonResponse({'ok': False, 'error': 'Payment verification failed.'}, status=400)

        # Mark payment paid
        pay.status = ProPayment.STATUS_PAID
        pay.payment_id = payment_id
        pay.signature = signature
        pay.save(update_fields=['status', 'payment_id', 'signature', 'updated_at'])

        # Activate subscription (30 days)
        _activate_subscription(
            request.user,
            provider=ProPayment.PROVIDER_RAZORPAY,
            payment_id=payment_id,
            order_id=order_id,
        )

        return JsonResponse({'ok': True, 'redirect_url': reverse('pro-success')})
    except Exception:
        return JsonResponse({'ok': False, 'error': 'Could not complete payment.'}, status=500)


@login_required
@require_GET
def pro_success_view(request):
    ctx = {
        'plan_name': PRO_PLAN_NAME,
    }
    return render(request, 'pro/success.html', ctx)
