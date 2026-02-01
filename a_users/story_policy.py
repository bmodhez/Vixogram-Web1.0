from __future__ import annotations

from django.conf import settings


def get_story_upload_requirements() -> tuple[int, int]:
    """Return (required_points, required_verified_invites)."""
    try:
        required_points = int(getattr(settings, 'STORY_UPLOAD_REQUIRED_POINTS', 50) or 50)
    except Exception:
        required_points = 50

    try:
        required_invites = int(getattr(settings, 'STORY_UPLOAD_REQUIRED_INVITES', 5) or 5)
    except Exception:
        required_invites = 5

    if required_points < 0:
        required_points = 0
    if required_invites < 0:
        required_invites = 0

    return required_points, required_invites


def get_user_story_progress(user) -> tuple[int, int]:
    """Return (points, verified_invites) for the given user."""
    if not user or not getattr(user, 'is_authenticated', False):
        return 0, 0

    points = 0
    try:
        points = int(getattr(getattr(user, 'profile', None), 'referral_points', 0) or 0)
    except Exception:
        points = 0

    verified_invites = 0
    try:
        from .models import Referral

        verified_invites = int(Referral.objects.filter(referrer=user, awarded_at__isnull=False).count() or 0)
    except Exception:
        verified_invites = 0

    return points, verified_invites


def can_user_add_story(user) -> bool:
    try:
        if user and getattr(user, 'is_authenticated', False) and (getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False)):
            return True
    except Exception:
        pass
    required_points, required_invites = get_story_upload_requirements()
    points, verified_invites = get_user_story_progress(user)
    return bool((points >= required_points) or (verified_invites >= required_invites))


def story_upload_locked_message(user) -> str:
    required_points, required_invites = get_story_upload_requirements()
    points, verified_invites = get_user_story_progress(user)

    # Keep it short (used in toasts).
    return (
        f"Minimum requirements not met to add a story. "
        f"Need {required_points} points ({required_invites} verified invites). "
        f"You have {points} points and {verified_invites} invites."
    )
