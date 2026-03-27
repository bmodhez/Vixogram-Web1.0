from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone


def get_story_max_active() -> int:
    """Maximum number of *active* stories a user can have at once."""
    try:
        n = int(getattr(settings, 'STORY_MAX_ACTIVE', 1) or 1)
    except Exception:
        n = 1
    if n < 1:
        n = 1
    return n


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
    """Return whether the user can add a story.

    Story upload is now free for all authenticated users.
    """
    try:
        if not bool(user and getattr(user, 'is_authenticated', False)):
            return False

        max_active = int(get_story_max_active() or 1)
        if max_active <= 1:
            # Single-story plan supports replace-on-upload.
            return True
        return int(get_user_active_story_count(user) or 0) < max_active
    except Exception:
        return False


def get_user_active_story_count(user) -> int:
    """Return currently active story count for a user."""
    if not user or not getattr(user, 'is_authenticated', False):
        return 0

    try:
        from .models import Story

        now = timezone.now()
        cutoff = now - timedelta(hours=int(getattr(Story, 'TTL_HOURS', 24) or 24))
        return int(
            Story.objects
            .filter(user=user)
            .filter(
                Q(expires_at__gt=now)
                | Q(expires_at__isnull=True, created_at__gte=cutoff)
            )
            .count()
        )
    except Exception:
        return 0


def story_upload_locked_message(user) -> str:
    required_points, required_invites = get_story_upload_requirements()
    points, verified_invites = get_user_story_progress(user)

    # Keep it short (used in toasts).
    return (
        f"Minimum requirements not met to add a story. "
        f"Need {required_points} points ({required_invites} verified invites). "
        f"You have {points} points and {verified_invites} invites."
    )
