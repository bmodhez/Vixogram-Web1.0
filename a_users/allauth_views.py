from __future__ import annotations

import time
import logging
import smtplib

from allauth.account.views import EmailView
from django.conf import settings
from django.contrib import messages
from django.core.cache import cache


logger = logging.getLogger(__name__)


def _email_delivery_hint() -> str | None:
    """Best-effort hint for dev setups where SMTP isn't configured."""

    backend = (getattr(settings, 'EMAIL_BACKEND', '') or '').strip()
    if not backend:
        return None

    if backend.endswith('filebased.EmailBackend'):
        path = (getattr(settings, 'EMAIL_FILE_PATH', '') or '').strip() or 'tmp_emails'
        return (
            f"Dev mode: email was saved to '{path}'. "
            "To send real emails, set EMAIL_HOST_USER and EMAIL_HOST_PASSWORD (Gmail requires an App Password)."
        )

    if backend.endswith('console.EmailBackend'):
        return (
            "Dev mode: email was printed in the server terminal. "
            "To send real emails, set EMAIL_HOST_USER and EMAIL_HOST_PASSWORD."
        )

    if backend.endswith('dummy.EmailBackend'):
        return (
            "Email sending is disabled (dummy backend). "
            "Configure SMTP via EMAIL_HOST_USER and EMAIL_HOST_PASSWORD."
        )

    return None


class CooldownEmailView(EmailView):
    """Email management view with resend cooldown.

    Prevents spamming verification emails by applying a short cooldown
    when the user clicks "Re-send verification" repeatedly.
    """

    COOLDOWN_SECONDS = 240  # 4 minutes

    def post(self, request, *args, **kwargs):
        # allauth uses submit button name="action_send" for resend verification.
        if 'action_send' in request.POST:
            user_id = getattr(getattr(request, 'user', None), 'id', None)
            if user_id:
                key = f"allauth:email_resend_cooldown:user:{user_id}"
                now = int(time.time())

                # Atomic set: if already set, block.
                if not cache.add(key, now, timeout=self.COOLDOWN_SECONDS):
                    messages.info(request, 'Please wait for 4 min and try again.')
                    # Re-render via redirect (same behavior as allauth).
                    return self.get(request, *args, **kwargs)

        try:
            response = super().post(request, *args, **kwargs)

            # Suppress the "confirmation email sent" banner for resend action.
            if 'action_send' in request.POST:
                try:
                    storage = messages.get_messages(request)
                    kept = []
                    for msg in storage:
                        text = str(getattr(msg, 'message', msg))
                        if 'confirmation email sent' in text.lower():
                            continue
                        kept.append(msg)
                    for msg in kept:
                        messages.add_message(request, msg.level, msg.message, extra_tags=msg.tags)
                except Exception:
                    pass

            return response
        except smtplib.SMTPAuthenticationError:
            logger.exception("SMTP auth failed while sending allauth email")
            messages.error(
                request,
                "Email login failed (SMTP). If you're using Gmail, set an App Password in EMAIL_HOST_PASSWORD.",
            )
            return self.get(request, *args, **kwargs)
        except smtplib.SMTPException:
            logger.exception("SMTP error while sending allauth email")
            messages.error(request, "Could not send email right now. Please try again later.")
            return self.get(request, *args, **kwargs)
