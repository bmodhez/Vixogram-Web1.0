from __future__ import annotations

import logging
import os

from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.core.mail import send_mail
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

# NudeNet unsafe body-part labels that trigger rejection.
_NUDENET_UNSAFE_CLASSES = {
    'FEMALE_GENITALIA_EXPOSED',
    'MALE_GENITALIA_EXPOSED',
    'FEMALE_BREAST_EXPOSED',
    'BUTTOCKS_EXPOSED',
    'ANUS_EXPOSED',
}
_NUDENET_THRESHOLD = 0.5  # confidence score threshold


@shared_task(bind=True, max_retries=0, ignore_result=True)
def moderate_avatar_task(self, profile_pk: int) -> None:
    """Deprecated: avatar moderation is manual via Django admin queue.

    We intentionally keep this task as a no-op so background workers can never
    auto-approve and upload profile pictures to Cloudinary.
    """
    logger.info(
        'moderate_avatar_task is disabled (manual admin approval required). profile=%s',
        profile_pk,
    )
    return


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 5})
def send_welcome_email(self, user_id: int) -> None:
    """Send a welcome email to a newly signed-up user.

    Runs in the background via Celery.
    """

    User = get_user_model()
    user = User.objects.filter(id=user_id).first()
    if not user:
        return

    email = (getattr(user, "email", "") or "").strip()
    if not email:
        return

    site = Site.objects.get_current()
    protocol = getattr(settings, 'ACCOUNT_DEFAULT_HTTP_PROTOCOL', 'http')
    base_url = f"{protocol}://{site.domain}" if site and site.domain else ""
    login_url = f"{base_url}/accounts/login/" if base_url else "/accounts/login/"

    ctx = {
        "user": user,
        "site_name": getattr(site, 'name', '') or 'Vixogram Connect',
        "site_domain": getattr(site, 'domain', ''),
        "login_url": login_url,
    }

    subject = render_to_string("a_users/email/welcome_subject.txt", ctx).strip()
    message = render_to_string("a_users/email/welcome_message.txt", ctx)

    send_mail(
        subject=subject,
        message=message,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        recipient_list=[email],
        fail_silently=False,
    )


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def send_mention_push_task(
    self,
    user_id: int,
    *,
    from_username: str,
    chatroom_name: str,
    preview: str = '',
) -> None:
    """Send an @mention push notification via FCM (best-effort).

    This runs in the background to keep chat message sends fast.
    """

    User = get_user_model()
    user = User.objects.filter(id=user_id, is_active=True).first()
    if not user:
        return

    try:
        from a_users.fcm import send_mention_push

        send_mention_push(
            user,
            from_username=(from_username or '')[:150],
            chatroom_name=(chatroom_name or '')[:128],
            preview=(preview or '')[:300],
        )
    except Exception:
        # Best-effort: never fail the task hard.
        return
