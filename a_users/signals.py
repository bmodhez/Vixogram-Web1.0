from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from django.conf import settings
from django.db.models import F
from django.utils import timezone
import os
from .models import Profile
from .models import Referral

try:
    from django.core import signing
except Exception:  # pragma: no cover
    signing = None

try:
    from allauth.account.signals import user_signed_up
    from allauth.account.signals import email_confirmed
except Exception:  # pragma: no cover
    user_signed_up = None
    email_confirmed = None

from .tasks import send_welcome_email

# Profile create/ensure
# NOTE: Don't call `profile.save()` on every `User` save.
# Django updates `last_login` on login, which would trigger this signal and add
# an extra write (and potential file-storage side effects) on every login.
@receiver(post_save, sender=User)
def ensure_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)
        return

    # Best-effort: ensure a profile exists for legacy/admin-created users.
    try:
        _ = instance.profile
    except Profile.DoesNotExist:
        Profile.objects.create(user=instance)


if user_signed_up is not None:
    @receiver(user_signed_up)
    def queue_welcome_email(request, user, **kwargs):
        # Send in background (Celery). In dev, may run eagerly depending on settings.
        try:
            env_broker = (os.environ.get('CELERY_BROKER_URL') or '').strip()
            settings_broker = (getattr(settings, 'CELERY_BROKER_URL', None) or '').strip()
            if env_broker or settings_broker:
                send_welcome_email.delay(user.id)
        except Exception:
            # Avoid blocking signup if broker is down.
            pass


REFERRAL_POINTS_PER_INVITE = 10


if user_signed_up is not None:
    @receiver(user_signed_up)
    def track_signup_referral(request, user, **kwargs):
        """If signup had a valid invite token, store Referral (pending)."""
        if request is None or signing is None:
            return

        token = (request.session.get('invite_ref') or '').strip()
        if not token:
            return

        # Clear it early to avoid accidental reuse.
        try:
            request.session.pop('invite_ref', None)
        except Exception:
            pass

        try:
            payload = signing.loads(token, salt='invite-friends', max_age=60 * 60 * 24 * 90)
            referrer_id = int(payload.get('u'))
        except Exception:
            return

        if not referrer_id:
            return
        if int(getattr(user, 'id', 0) or 0) == referrer_id:
            return

        try:
            referrer = User.objects.get(id=referrer_id)
        except Exception:
            return

        # One referral per new account.
        try:
            Referral.objects.get_or_create(
                referred=user,
                defaults={'referrer': referrer},
            )
        except Exception:
            # Don't block signup.
            pass


if email_confirmed is not None:
    @receiver(email_confirmed)
    def award_referral_points_on_email_verified(request, email_address, **kwargs):
        """Award points to referrer once the referred user's email is verified."""
        try:
            user = getattr(email_address, 'user', None)
            if user is None:
                return
            if not bool(getattr(email_address, 'verified', False)):
                return
        except Exception:
            return

        try:
            referral = Referral.objects.select_related('referrer').get(referred=user)
        except Referral.DoesNotExist:
            return
        except Exception:
            return

        if referral.awarded_at is not None:
            return

        points = int(getattr(settings, 'REFERRAL_POINTS_PER_INVITE', REFERRAL_POINTS_PER_INVITE))
        if points <= 0:
            points = REFERRAL_POINTS_PER_INVITE

        try:
            Profile.objects.filter(user=referral.referrer).update(referral_points=F('referral_points') + points)
            referral.points_awarded = points
            referral.awarded_at = timezone.now()
            referral.save(update_fields=['points_awarded', 'awarded_at'])
        except Exception:
            # Keep it idempotent: if save fails, next confirm can retry.
            pass