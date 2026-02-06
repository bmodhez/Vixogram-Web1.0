from __future__ import annotations

from allauth.account.forms import LoginForm, SignupForm, ResetPasswordForm, ResetPasswordKeyForm

from django.conf import settings
from django.core.exceptions import ValidationError

from .username_policy import validate_public_username
from .recaptcha import verify_recaptcha


_BASE_INPUT_CLASS = (
    "w-full bg-gray-800/60 border border-gray-700 text-gray-100 rounded-xl "
    "pl-4 pr-4 py-3 placeholder-gray-400 outline-none "
    "focus:border-indigo-400 focus:ring-2 focus:ring-indigo-500/30"
)

_LOGIN_INPUT_CLASS = (
    "w-full bg-gray-800/60 border border-gray-700 text-gray-100 rounded-xl "
    "pl-4 pr-4 py-3 placeholder-gray-400 outline-none "
    "focus:border-indigo-400 focus:ring-2 focus:ring-indigo-500/30"
)

_CHECKBOX_CLASS = "accent-indigo-500"


def _validate_gmail_address(email: str) -> str:
    email = (email or '').strip()
    if not email:
        return email
    lower = email.lower()
    if not lower.endswith('@gmail.com'):
        raise ValidationError('Please use a valid @gmail.com email address.')
    # Safety: avoid trailing spaces/odd casing being stored.
    return lower


class CustomLoginForm(LoginForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if "login" in self.fields:
            self.fields["login"].widget.attrs.update(
                {
                    "class": f"{_LOGIN_INPUT_CLASS} !pl-12",
                    "placeholder": "Username or email",
                    "autocomplete": "username",
                }
            )

        if "password" in self.fields:
            self.fields["password"].widget.attrs.update(
                {
                    "class": f"{_LOGIN_INPUT_CLASS} !pl-12",
                    "placeholder": "Password",
                    "autocomplete": "current-password",
                }
            )

        if "remember" in self.fields:
            self.fields["remember"].widget.attrs.update({"class": _CHECKBOX_CLASS})


class CustomSignupForm(SignupForm):
    def clean(self):
        cleaned = super().clean()

        if bool(getattr(settings, 'RECAPTCHA_REQUIRED', False)):
            token = (self.data.get('g-recaptcha-response') or '').strip()
            if not token:
                raise ValidationError('Please complete the reCAPTCHA.')

            req = getattr(self, 'request', None)
            remote_ip = None
            try:
                remote_ip = (req.META.get('REMOTE_ADDR') or '').strip() if req else None
            except Exception:
                remote_ip = None

            version = (getattr(settings, 'RECAPTCHA_VERSION', 'v2') or 'v2').strip().lower()
            if version == 'v3':
                expected_action = (getattr(settings, 'RECAPTCHA_ACTION', 'signup') or 'signup').strip() or 'signup'
                min_score = float(getattr(settings, 'RECAPTCHA_MIN_SCORE', 0.5))
                ok, _data = verify_recaptcha(
                    token=token,
                    remote_ip=remote_ip,
                    expected_action=expected_action,
                    min_score=min_score,
                )
            else:
                ok, _data = verify_recaptcha(token=token, remote_ip=remote_ip)
            if not ok:
                raise ValidationError('reCAPTCHA verification failed. Please try again.')

        return cleaned

    def clean_username(self):
        username = super().clean_username()
        validate_public_username(username)
        return username

    def clean_email(self):
        email = super().clean_email()
        return _validate_gmail_address(email)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Persist invite/referral token across the signup POST.
        try:
            req = getattr(self, 'request', None)
            if req is not None:
                ref = (req.GET.get('ref') or '').strip()
                if ref:
                    req.session['invite_ref'] = ref
        except Exception:
            pass

        for name, field in self.fields.items():
            if name in {"password1", "password2"}:
                field.widget.attrs.update(
                    {
                        "class": f"{_BASE_INPUT_CLASS} !pl-12",
                        "placeholder": "Create password" if name == "password1" else "Confirm password",
                        "autocomplete": "new-password",
                    }
                )
                continue

            if name == "email":
                field.widget.attrs.update(
                    {
                        "class": f"{_BASE_INPUT_CLASS} !pl-12",
                        "placeholder": "Email address",
                        "autocomplete": "email",
                    }
                )
                continue

            if name == "username":
                field.widget.attrs.update(
                    {
                        "class": f"{_BASE_INPUT_CLASS} !pl-12",
                        "placeholder": "Username",
                        "autocomplete": "username",
                    }
                )
                continue

            field.widget.attrs.update({"class": _BASE_INPUT_CLASS})


class CustomResetPasswordForm(ResetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if "email" in self.fields:
            self.fields["email"].widget.attrs.update(
                {
                    "class": _BASE_INPUT_CLASS,
                    "placeholder": "Email address",
                    "autocomplete": "email",
                }
            )


class CustomResetPasswordKeyForm(ResetPasswordKeyForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if "password1" in self.fields:
            self.fields["password1"].widget.attrs.update(
                {
                    "class": _BASE_INPUT_CLASS,
                    "placeholder": "New password",
                    "autocomplete": "new-password",
                }
            )

        if "password2" in self.fields:
            self.fields["password2"].widget.attrs.update(
                {
                    "class": _BASE_INPUT_CLASS,
                    "placeholder": "Confirm password",
                    "autocomplete": "new-password",
                }
            )


try:
    from allauth.account.forms import AddEmailForm
except Exception:  # pragma: no cover
    AddEmailForm = None


if AddEmailForm is not None:
    class CustomAddEmailForm(AddEmailForm):
        def clean_email(self):
            email = super().clean_email()
            return _validate_gmail_address(email)
