from __future__ import annotations

import logging
import random
import re
import string
import threading

from allauth.account.adapter import DefaultAccountAdapter
from allauth.account import adapter as allauth_adapter_module
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.urls import reverse

from .username_policy import validate_public_username


logger = logging.getLogger(__name__)


class CustomAccountAdapter(DefaultAccountAdapter):
    @staticmethod
    def _username_base_from_email(email: str) -> str:
        try:
            local = (email or '').split('@', 1)[0]
        except Exception:
            local = ''
        local = (local or '').strip().lower()
        # Keep only [a-z0-9_], collapse others.
        local = re.sub(r'[^a-z0-9_]+', '_', local)
        local = re.sub(r'_+', '_', local).strip('_')
        if not local:
            local = 'vixo'
        # Ensure minimum length.
        if len(local) < 3:
            local = f"{local}vixo"
        return local[:18]

    @classmethod
    def _generate_unique_username(cls, email: str) -> str:
        User = get_user_model()
        base = cls._username_base_from_email(email)

        # Try base first, then base + suffix.
        candidates = [base]
        for _ in range(25):
            suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=5))
            candidates.append(f"{base}_{suffix}")

        for candidate in candidates:
            candidate = (candidate or '').strip().lower()
            if not candidate:
                continue
            try:
                validate_public_username(candidate)
            except Exception:
                continue
            try:
                if not User.objects.filter(username__iexact=candidate).exists():
                    return candidate
            except Exception:
                continue

        # Fallback: random username.
        for _ in range(50):
            candidate = 'vx_' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
            try:
                validate_public_username(candidate)
            except Exception:
                continue
            try:
                if not User.objects.filter(username__iexact=candidate).exists():
                    return candidate
            except Exception:
                continue

        # Last resort (should be extremely rare).
        return 'vx_' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))

    def save_user(self, request, user, form, commit=True):
        # allauth may call save_user with commit=True; we ensure username exists
        # even when it is not collected at signup.
        user = super().save_user(request, user, form, commit=False)

        try:
            if not (getattr(user, 'username', '') or '').strip():
                email = (getattr(user, 'email', '') or '').strip()
                user.username = self._generate_unique_username(email)
                # Make Step 1 mandatory for this session.
                try:
                    if request is not None and getattr(request, 'session', None) is not None:
                        request.session['onboarding_needs_username'] = True
                except Exception:
                    pass
        except Exception:
            pass

        if commit:
            user.save()
        return user

    def clean_username(self, username, *args, **kwargs):
        username = super().clean_username(username, *args, **kwargs)
        validate_public_username(username)
        return username

    def send_mail(self, template_prefix: str, email: str, context: dict) -> None:
        # Requirement: do NOT auto-send verification email right after signup.
        # Users will manually request verification from the Email settings page.
        try:
            if bool(getattr(settings, 'ALLAUTH_SUPPRESS_SIGNUP_CONFIRMATION_EMAIL', False)):
                prefix = (template_prefix or '').lower()
                if 'email_confirmation' in prefix:
                    try:
                        request = allauth_adapter_module.context.request
                    except Exception:
                        request = None

                    if request is not None:
                        try:
                            # Most reliable: resolver view name.
                            rm = getattr(request, 'resolver_match', None)
                            if rm and getattr(rm, 'view_name', '') == 'account_signup':
                                return None
                        except Exception:
                            pass

                        try:
                            signup_path = reverse('account_signup')
                            if str(getattr(request, 'path', '') or '').startswith(signup_path):
                                return None
                        except Exception:
                            pass
        except Exception:
            # If anything goes wrong, do not break email sending.
            pass

        # On slow networks/SMTP, sending verification mail can block the signup POST
        # long enough that users click twice (first request succeeds, second shows
        # "already exists"). Allow async email sending to keep the UX snappy.
        if bool(getattr(settings, 'ALLAUTH_ASYNC_EMAIL', False)):
            def _bg_send():
                try:
                    DefaultAccountAdapter.send_mail(self, template_prefix, email, context)
                except Exception:
                    logger.exception("Failed to send allauth email (async) '%s' to %s", template_prefix, email)

            try:
                t = threading.Thread(target=_bg_send, name='allauth-send-mail', daemon=True)
                t.start()
                return None
            except Exception:
                # Fallback to sync send.
                pass

        try:
            return super().send_mail(template_prefix, email, context)
        except Exception:
            logger.exception("Failed to send allauth email '%s' to %s", template_prefix, email)

            # In production, don't crash the whole flow if SMTP is unreachable.
            if getattr(settings, 'ALLAUTH_FAIL_EMAIL_SILENTLY', False):
                try:
                    request = allauth_adapter_module.context.request
                except Exception:
                    request = None
                if request is not None:
                    try:
                        messages.error(request, 'Email service is temporarily unavailable. Please try again later.')
                    except Exception:
                        pass
                return None

            raise

    def send_confirmation_mail(self, request, emailconfirmation, signup):
        """Suppress signup confirmation email when configured.

        Keeps manual resend working from the Email settings page.
        """
        try:
            if bool(getattr(settings, 'ALLAUTH_SUPPRESS_SIGNUP_CONFIRMATION_EMAIL', False)) and bool(signup):
                return None
        except Exception:
            pass
        return super().send_confirmation_mail(request, emailconfirmation, signup)
