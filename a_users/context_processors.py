from __future__ import annotations

try:
    from a_rtchat.models import Notification
except Exception:  # pragma: no cover
    Notification = None

try:
    from a_users.models import FollowRequest
except Exception:  # pragma: no cover
    FollowRequest = None

try:
    from .story_policy import (
        can_user_add_story,
        get_story_max_active,
        get_story_upload_requirements,
        get_user_active_story_count,
        get_user_story_progress,
    )
except Exception:  # pragma: no cover
    can_user_add_story = None
    get_story_max_active = None
    get_story_upload_requirements = None
    get_user_active_story_count = None
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


def follow_requests_badge(request):
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return {'NAV_FOLLOWREQ_PENDING': 0}
    if FollowRequest is None:
        return {'NAV_FOLLOWREQ_PENDING': 0}
    try:
        c = FollowRequest.objects.filter(to_user=request.user).count()
        return {'NAV_FOLLOWREQ_PENDING': int(c or 0)}
    except Exception:
        return {'NAV_FOLLOWREQ_PENDING': 0}


def story_upload_gate(request):
    """Global template flags for story upload gating."""
    user = getattr(request, 'user', None)

    # Story upload is free for all authenticated users, but active story count is limited.
    required_points, required_invites = 0, 0
    points, verified_invites = 0, 0
    max_active = 1
    active_count = 0

    try:
        if callable(get_story_max_active):
            max_active = int(get_story_max_active() or 1)
    except Exception:
        max_active = 1

    try:
        if callable(get_user_active_story_count):
            active_count = int(get_user_active_story_count(user) or 0)
    except Exception:
        active_count = 0

    try:
        if callable(can_user_add_story):
            can_add = bool(can_user_add_story(user))
        else:
            if int(max_active or 1) <= 1:
                can_add = bool(user and getattr(user, 'is_authenticated', False))
            else:
                can_add = bool(user and getattr(user, 'is_authenticated', False) and active_count < max_active)
    except Exception:
        can_add = False

    limit_message = (
        'Only 1 active story is allowed. Uploading a new story will replace the previous one.'
        if int(max_active or 1) == 1
        else f'Free plan limited to {max_active} stories.'
    )

    return {
        'CAN_ADD_STORY': bool(can_add),
        'STORY_MAX_ACTIVE': int(max_active or 1),
        'STORY_ACTIVE_COUNT': int(active_count or 0),
        'STORY_LIMIT_MESSAGE': str(limit_message),
        'STORY_REQUIRED_POINTS': int(required_points or 0),
        'STORY_REQUIRED_INVITES': int(required_invites or 0),
        'STORY_POINTS': int(points or 0),
        'STORY_VERIFIED_INVITES': int(verified_invites or 0),
    }
