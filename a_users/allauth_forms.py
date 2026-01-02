from __future__ import annotations

from allauth.account.forms import LoginForm, SignupForm, ResetPasswordForm, ResetPasswordKeyForm


_BASE_INPUT_CLASS = (
    "w-full bg-gray-800/60 border border-gray-700 text-gray-100 rounded-xl "
    "px-4 py-3 placeholder-gray-400 outline-none "
    "focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/30"
)

_CHECKBOX_CLASS = "accent-emerald-500"


class CustomLoginForm(LoginForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if "login" in self.fields:
            self.fields["login"].widget.attrs.update(
                {
                    "class": _BASE_INPUT_CLASS,
                    "placeholder": "Username or email",
                    "autocomplete": "username",
                }
            )

        if "password" in self.fields:
            self.fields["password"].widget.attrs.update(
                {
                    "class": _BASE_INPUT_CLASS + " pr-12",
                    "placeholder": "Password",
                    "autocomplete": "current-password",
                }
            )

        if "remember" in self.fields:
            self.fields["remember"].widget.attrs.update({"class": _CHECKBOX_CLASS})


class CustomSignupForm(SignupForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for name, field in self.fields.items():
            if name in {"password1", "password2"}:
                field.widget.attrs.update(
                    {
                        "class": _BASE_INPUT_CLASS + " pr-12",
                        "placeholder": "Password" if name == "password1" else "Confirm password",
                        "autocomplete": "new-password",
                    }
                )
                continue

            if name == "email":
                field.widget.attrs.update(
                    {
                        "class": _BASE_INPUT_CLASS,
                        "placeholder": "Email address",
                        "autocomplete": "email",
                    }
                )
                continue

            if name == "username":
                field.widget.attrs.update(
                    {
                        "class": _BASE_INPUT_CLASS,
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
                    "class": _BASE_INPUT_CLASS + " pr-12",
                    "placeholder": "New password",
                    "autocomplete": "new-password",
                }
            )

        if "password2" in self.fields:
            self.fields["password2"].widget.attrs.update(
                {
                    "class": _BASE_INPUT_CLASS + " pr-12",
                    "placeholder": "Confirm password",
                    "autocomplete": "new-password",
                }
            )
