from __future__ import annotations

import base64
import hashlib

from django import template
from django.core.cache import cache

from allauth.mfa.adapter import get_adapter
from allauth.mfa.models import Authenticator
from allauth.mfa.utils import decrypt

from a_users.models import BetaFeature

register = template.Library()


def _qr_once_cache_key(user_pk, authenticator_pk, encrypted_secret):
    raw = f"{user_pk}:{authenticator_pk}:{encrypted_secret}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"vixo:mfa:totp_qr_once:{digest}"


@register.simple_tag
def beta_feature_enabled(slug: str) -> bool:
    """Whether a beta feature is currently enabled ("pushed to beta")."""
    slug = (slug or '').strip()
    if not slug:
        return False
    return BetaFeature.objects.filter(slug=slug, is_enabled=True).exists()


@register.simple_tag(takes_context=True)
def beta_feature_access(context, slug: str) -> bool:
    """Whether the current request user can USE the beta feature."""
    slug = (slug or '').strip()
    if not slug:
        return False

    try:
        feature = BetaFeature.objects.get(slug=slug)
    except BetaFeature.DoesNotExist:
        return False

    user = context.get('user')
    return feature.is_accessible_by(user)


@register.simple_tag
def beta_feature_locked_text() -> str:
    return 'To access this beta feature you have to be the member of Founder club'


@register.simple_tag
def mfa_totp_qr_data_uri(user):
    if not user or not getattr(user, "pk", None):
        return ""

    authenticator = Authenticator.objects.filter(
        user=user,
        type=Authenticator.Type.TOTP,
    ).first()
    if not authenticator:
        return ""

    encrypted_secret = (authenticator.data or {}).get("secret")
    if not encrypted_secret:
        return ""

    # One-time reveal: once this QR has been served for this secret, do not serve again.
    try:
        once_key = _qr_once_cache_key(user.pk, authenticator.pk, encrypted_secret)
        if not cache.add(once_key, "1", timeout=None):
            return ""
    except Exception:
        # If cache is unavailable, fall back to existing behavior instead of breaking login.
        pass

    try:
        secret = decrypt(encrypted_secret)
        adapter = get_adapter()
        totp_url = adapter.build_totp_url(user, secret)
        totp_svg = adapter.build_totp_svg(totp_url)
        base64_data = base64.b64encode(totp_svg.encode("utf-8")).decode("utf-8")
        return f"data:image/svg+xml;base64,{base64_data}"
    except Exception:
        return ""
