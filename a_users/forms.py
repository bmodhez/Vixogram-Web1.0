from datetime import timedelta

from django import forms
from django.contrib.auth.models import User
from django.utils import timezone
from django.conf import settings
from .models import Profile
from .models import Story
from .models import UserReport
from .models import SupportEnquiry
import re

from .username_policy import validate_public_username


BIO_MAX_LENGTH = 200


def mask_bio_text(value: str) -> str:
    """Mask links and social handles in bio with asterisks.

    This matches the behavior of the `sanitize_bio` template filter, but
    is applied on save so stored bios stay safe too.
    """
    if not value:
        return value

    text = str(value)
    if not text.strip():
        return text

    patterns = [
        (r'https?://[^\s]+', '*****'),
        (r'www\.[^\s]+', '*****'),
        (r'@[\w\.]+', '*****'),
        (r'(?i)\b(instagram|insta|facebook|fb|tiktok|tik\s*tok|snapchat|snap|telegram|discord|youtube|whatsapp|whats\s*app|twitter|x\.com)\b', '*****'),
    ]
    for pattern, replacement in patterns:
        text = re.sub(pattern, replacement, text)
    return text


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['image', 'cover_image', 'displayname', 'info']
        labels = {
            'info': 'Bio',
            'cover_image': 'Profile background',
        }
        widgets = {
            'image': forms.FileInput(attrs={
                'class': 'w-full text-sm text-gray-300 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-gray-700 file:text-white hover:file:bg-gray-600',
                'accept': 'image/*',
            }),
            'cover_image': forms.FileInput(attrs={
                'class': 'w-full text-sm text-gray-300 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-gray-700 file:text-white hover:file:bg-gray-600',
                'accept': 'image/*',
            }),
            'displayname': forms.TextInput(attrs={
                'placeholder': 'Add display name',
                'class': 'w-full bg-gray-700 text-white border border-gray-600 rounded-lg px-4 py-3 outline-none focus:border-emerald-500',
            }),
            'info': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Add bio',
                'maxlength': str(BIO_MAX_LENGTH),
                'class': 'w-full bg-gray-700 text-white border border-gray-600 rounded-lg px-4 py-3 outline-none focus:border-emerald-500',
            })
        }

    def clean_image(self):
        f = self.cleaned_data.get('image')
        if not f:
            return f

        # Enforce a small upload limit for avatar as well.
        try:
            if hasattr(f, 'size') and int(f.size) > 2 * 1024 * 1024:
                raise forms.ValidationError('Avatar image must be under 2MB.')
        except forms.ValidationError:
            raise
        except Exception:
            pass

        # Basic content-type check.
        ct = getattr(f, 'content_type', '') or ''
        if ct and not str(ct).lower().startswith('image/'):
            raise forms.ValidationError('Please upload a valid image file.')

        return f

    def clean_cover_image(self):
        f = self.cleaned_data.get('cover_image')
        if not f:
            return f

        # Enforce a small upload limit for profile background.
        try:
            if hasattr(f, 'size') and int(f.size) > 2 * 1024 * 1024:
                raise forms.ValidationError('Background image must be under 2MB.')
        except Exception:
            pass

        # Basic content-type check.
        ct = getattr(f, 'content_type', '') or ''
        if ct and not str(ct).lower().startswith('image/'):
            raise forms.ValidationError('Please upload a valid image file.')

        return f

    def clean_info(self):
        bio = self.cleaned_data.get('info')
        if bio is None:
            return bio

        bio_str = str(bio)
        # Enforce hard limit on what the user can store.
        if len(bio_str) > BIO_MAX_LENGTH:
            raise forms.ValidationError(f'Bio must be {BIO_MAX_LENGTH} characters or less.')

        masked = mask_bio_text(bio_str)
        if masked is not None and len(masked) > BIO_MAX_LENGTH:
            raise forms.ValidationError(f'Bio must be {BIO_MAX_LENGTH} characters or less.')

        return masked


class ReportUserForm(forms.Form):
    reason = forms.ChoiceField(
        choices=UserReport.REASON_CHOICES,
        widget=forms.Select(
            attrs={
                'class': 'w-full bg-gray-700 text-white border border-gray-600 rounded-lg px-4 py-3 outline-none focus:border-emerald-500',
            }
        ),
    )

    details = forms.CharField(
        required=False,
        max_length=1000,
        widget=forms.Textarea(
            attrs={
                'rows': 3,
                'placeholder': 'Add details (optional)',
                'class': 'w-full bg-gray-700 text-white border border-gray-600 rounded-lg px-4 py-3 outline-none focus:border-emerald-500',
            }
        ),
    )


class ProfilePrivacyForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['is_private_account', 'is_stealth', 'is_dnd']
        widgets = {
            'is_private_account': forms.CheckboxInput(attrs={
                'class': 'sr-only peer',
            }),
            'is_stealth': forms.CheckboxInput(attrs={
                'class': 'sr-only peer',
            }),
            'is_dnd': forms.CheckboxInput(attrs={
                'class': 'sr-only peer',
            }),
        }


class UsernameChangeForm(forms.Form):
    username = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(
            attrs={
                'placeholder': 'New username',
                'class': 'w-full bg-gray-700 text-white border border-gray-600 rounded-lg px-4 pr-10 py-3 outline-none focus:border-emerald-500',
                'autocomplete': 'off',
                'autocapitalize': 'none',
                'spellcheck': 'false',
            }
        ),
    )

    USERNAME_RE = re.compile(r'^[a-zA-Z0-9_]{3,30}$')

    def __init__(self, *args, user=None, profile=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.profile = profile

    @staticmethod
    def _cooldown_days() -> int:
        try:
            return int(getattr(settings, 'USERNAME_CHANGE_COOLDOWN_DAYS', 21))
        except Exception:
            return 21

    def can_change_now(self) -> tuple[bool, timezone.datetime | None]:
        """Return (can_change, next_available_at)."""
        profile = self.profile
        if not profile:
            return False, None

        # First change after registration is allowed anytime.
        if int(getattr(profile, 'username_change_count', 0) or 0) <= 0:
            return True, None

        last = getattr(profile, 'username_last_changed_at', None)
        if not last:
            return True, None

        next_at = last + timedelta(days=self._cooldown_days())
        now = timezone.now()
        return (now >= next_at), next_at

    def clean_username(self):
        username = (self.cleaned_data.get('username') or '').strip()
        username = username.replace(' ', '')

        if not username:
            raise forms.ValidationError('Username is required.')

        if not self.USERNAME_RE.match(username):
            raise forms.ValidationError('Use 3-30 chars: letters, numbers, underscore, dot.')

        if self.user and getattr(self.user, 'username', '') and username == self.user.username:
            raise forms.ValidationError('That is already your username.')

        # Avoid duplicates (case-insensitive).
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError('This username is already taken.')

        # Enforce global signup-like rules here too.
        validate_public_username(username)

        return username


class SupportEnquiryForm(forms.ModelForm):
    class Meta:
        model = SupportEnquiry
        fields = ['subject', 'message']
        widgets = {
            'subject': forms.TextInput(
                attrs={
                    'placeholder': 'Subject (optional)',
                    'maxlength': '120',
                    'class': 'w-full bg-gray-700 text-white border border-gray-600 rounded-lg px-4 py-3 outline-none focus:border-emerald-500',
                }
            ),
            'message': forms.Textarea(
                attrs={
                    'rows': 5,
                    'placeholder': 'Describe your issue / feedback…',
                    'maxlength': '2000',
                    'class': 'w-full bg-gray-700 text-white border border-gray-600 rounded-lg px-4 py-3 outline-none focus:border-emerald-500',
                }
            ),
        }


class StoryForm(forms.ModelForm):
    class Meta:
        model = Story
        fields = ['image']
        widgets = {
            'image': forms.FileInput(attrs={
                'id': 'story_image_input',
                'class': 'hidden',
                'accept': 'image/*',
            }),
        }

    def clean_image(self):
        f = self.cleaned_data.get('image')
        if not f:
            raise forms.ValidationError('Please choose an image.')

        # Basic content-type check.
        ct = getattr(f, 'content_type', '') or ''
        if ct and not str(ct).lower().startswith('image/'):
            raise forms.ValidationError('Only images are allowed for stories.')

        # Simple size limit to prevent abuse (5MB).
        try:
            if hasattr(f, 'size') and int(f.size) > 5 * 1024 * 1024:
                raise forms.ValidationError('Story image must be under 5MB.')
        except forms.ValidationError:
            raise
        except Exception:
            pass

        return f