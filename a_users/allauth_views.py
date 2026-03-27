from __future__ import annotations

import time
import logging
import smtplib

from allauth.account.views import EmailView
from allauth.account.views import LoginView
from allauth.account.views import SignupView
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout as django_logout
from django.core.cache import cache
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.views import View

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

    def _cooldown_cache_key(self, request) -> str | None:
        user_id = getattr(getattr(request, 'user', None), 'id', None)
        if not user_id:
            return None
        return f"allauth:email_resend_cooldown:user:{user_id}"

    def _cooldown_remaining_seconds(self, request) -> int:
        key = self._cooldown_cache_key(request)
        if not key:
            return 0
        try:
            started_at = cache.get(key)
            if started_at is None:
                return 0
            now = int(time.time())
            started_at = int(started_at)
            remaining = int(self.COOLDOWN_SECONDS - max(0, now - started_at))
            return max(0, remaining)
        except Exception:
            return 0

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        remaining = self._cooldown_remaining_seconds(self.request)
        ctx['email_resend_cooldown_remaining'] = int(remaining)
        return ctx

    def post(self, request, *args, **kwargs):
        # allauth uses submit button name="action_send" for resend verification.
        if 'action_send' in request.POST:
            key = self._cooldown_cache_key(request)
            if key:
                now = int(time.time())

                # Atomic set: if already set, block.
                if not cache.add(key, now, timeout=self.COOLDOWN_SECONDS):
                    remaining = self._cooldown_remaining_seconds(request)
                    if remaining > 0:
                        messages.error(request, f'Please wait {remaining}s before resending verification.')
                    else:
                        messages.error(request, 'Please wait before resending verification.')
                    # PRG: avoid browser "Confirm Form Resubmission" on refresh/back.
                    return redirect('account_email')

        try:
            response = super().post(request, *args, **kwargs)

            # allauth may return a raw 429 page on burst actions.
            # Keep UX consistent by redirecting back with a friendly message.
            try:
                status_code = int(getattr(response, 'status_code', 200) or 200)
            except Exception:
                status_code = 200
            if status_code == 429:
                remaining = self._cooldown_remaining_seconds(request)
                if remaining > 0:
                    messages.error(request, f'Please wait {remaining}s before resending verification.')
                else:
                    messages.error(request, 'Too many requests. Please try again after a few seconds.')
                return redirect('account_email')

            # Suppress the "confirmation email sent" banner for resend action.
            if 'action_send' in request.POST:
                try:
                    storage = messages.get_messages(request)
                    kept = []
                    removed_confirmation = False
                    for msg in storage:
                        text = str(getattr(msg, 'message', msg))
                        if 'confirmation email sent' in text.lower():
                            removed_confirmation = True
                            continue
                        kept.append(msg)
                    for msg in kept:
                        messages.add_message(request, msg.level, msg.message, extra_tags=msg.tags)
                    if removed_confirmation:
                        messages.success(request, 'Verification email sent successfully.')
                except Exception:
                    pass

            return response
        except smtplib.SMTPAuthenticationError:
            logger.exception("SMTP auth failed while sending allauth email")
            messages.error(
                request,
                "Email login failed (SMTP). If you're using Gmail, set an App Password in EMAIL_HOST_PASSWORD.",
            )
            return redirect('account_email')
        except smtplib.SMTPException:
            logger.exception("SMTP error while sending allauth email")
            messages.error(request, "Could not send email right now. Please try again later.")
            return redirect('account_email')


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
                sess['post_auth_chat_tutorial'] = 'signup'
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
                sess['post_auth_chat_tutorial'] = 'login'
        except Exception:
            pass

        return super().form_valid(form)


class MFACancelToLoginView(View):
    """Cancel MFA stage and force redirect to plain login page."""

    def post(self, request, *args, **kwargs):
        try:
            django_logout(request)
        except Exception:
            pass

        try:
            sess = getattr(request, 'session', None)
            if sess is not None:
                sess.pop('show_welcome_popup', None)
                sess.pop('welcome_popup_source', None)
                sess.pop('post_auth_chat_tutorial', None)
        except Exception:
            pass

        return redirect('/accounts/login/')
