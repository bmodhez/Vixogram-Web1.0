from __future__ import annotations

try:
    from a_rtchat.models import Notification
except Exception:  # pragma: no cover
    Notification = None

try:
    from .story_policy import can_user_add_story, get_story_upload_requirements, get_user_story_progress
except Exception:  # pragma: no cover
    can_user_add_story = None
    get_story_upload_requirements = None
    get_user_story_progress = None


def notifications_badge(request):
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return {'NAV_NOTIF_UNREAD': 0}
    if Notification is None:
        return {'NAV_NOTIF_UNREAD': 0}
    try:
        c = Notification.objects.filter(user=request.user, is_read=False).count()
        return {'NAV_NOTIF_UNREAD': int(c or 0)}
    except Exception:
        return {'NAV_NOTIF_UNREAD': 0}


def story_upload_gate(request):
    """Global template flags for story upload gating."""
    user = getattr(request, 'user', None)

    required_points, required_invites = 50, 5
    points, verified_invites = 0, 0
    can_add = False

    try:
        if get_story_upload_requirements is not None:
            required_points, required_invites = get_story_upload_requirements()
        if get_user_story_progress is not None:
            points, verified_invites = get_user_story_progress(user)
        if can_user_add_story is not None:
            can_add = bool(can_user_add_story(user))
    except Exception:
        can_add = False

    return {
        'CAN_ADD_STORY': bool(can_add),
        'STORY_REQUIRED_POINTS': int(required_points or 0),
        'STORY_REQUIRED_INVITES': int(required_invites or 0),
        'STORY_POINTS': int(points or 0),
        'STORY_VERIFIED_INVITES': int(verified_invites or 0),
    }
