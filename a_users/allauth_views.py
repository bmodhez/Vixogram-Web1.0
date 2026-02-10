from __future__ import annotations

import time
import logging
import smtplib

from allauth.account.views import EmailView
from allauth.account.views import LoginView
from allauth.account.views import SignupView
from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.http import HttpResponseRedirect

try:
    from urllib.parse import urlencode
except Exception:  # pragma: no cover
    urlencode = None


logger = logging.getLogger(__name__)


def _add_query_param(url: str, key: str, value: str) -> str:
    try:
        from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

        parts = urlsplit(url)
        qs = dict(parse_qsl(parts.query, keep_blank_values=True))
        if key not in qs:
            qs[key] = value
        new_query = urlencode(qs)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))
    except Exception:
        return url


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


class PRGLoginView(LoginView):
    """Login view that avoids browser POST-resubmission screens.

    Browsers show a built-in "Resubmit the form" page when users refresh a POST response.
    This view redirects to GET on invalid POST as well, so refresh stays safe.
    """

    def form_invalid(self, form):
        # Keep message short; inline form errors would be lost after redirect.
        msg = 'Invalid login details. Please try again.'
        try:
            errs = form.non_field_errors()
            if errs:
                msg = str(errs[0])
        except Exception:
            pass
        try:
            messages.error(self.request, msg)
        except Exception:
            pass

        # Preserve ?next= across the redirect.
        try:
            next_name = getattr(self, 'redirect_field_name', 'next') or 'next'
        except Exception:
            next_name = 'next'

        nxt = ''
        try:
            nxt = (self.request.POST.get(next_name) or self.request.GET.get(next_name) or '').strip()
        except Exception:
            nxt = ''

        url = self.request.path
        if nxt and urlencode is not None:
            try:
                url = f"{url}?{urlencode({next_name: nxt})}"
            except Exception:
                url = self.request.path

        return HttpResponseRedirect(url)


class WelcomeSignupView(SignupView):
    """Signup view that schedules the one-time welcome popup."""

    def form_valid(self, form):
        try:
            sess = getattr(self.request, 'session', None)
            if sess is not None:
                sess['show_welcome_popup'] = True
                sess['welcome_popup_source'] = 'signup'
        except Exception:
            pass

        resp = super().form_valid(form)
        try:
            loc = str(resp.get('Location') or '')
            if loc:
                resp['Location'] = _add_query_param(loc, 'welcome', 'signup')
        except Exception:
            pass
        return resp


class WelcomeLoginView(PRGLoginView):
    """Login view that schedules the one-time welcome popup."""

    def form_valid(self, form):
        try:
            sess = getattr(self.request, 'session', None)
            if sess is not None:
                sess['show_welcome_popup'] = True
                sess['welcome_popup_source'] = 'login'
        except Exception:
            pass

        resp = super().form_valid(form)
        try:
            loc = str(resp.get('Location') or '')
            if loc:
                resp['Location'] = _add_query_param(loc, 'welcome', 'login')
        except Exception:
            pass
        return resp
