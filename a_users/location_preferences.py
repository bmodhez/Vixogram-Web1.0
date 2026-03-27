from __future__ import annotations

from django.contrib.auth.models import User
from django.utils.text import slugify


def clean_location_name(value: str, max_len: int = 80) -> str:
    text = str(value or '').strip()
    if not text:
        return ''
    text = ' '.join(text.split())
    return text[:max_len]


def _community_group_name(level: str, value: str) -> str:
    base = slugify(value)[:72] or 'community'
    return f"local-{level}-{base}"


def _community_defaults(level: str, value: str, admin_user: User | None = None) -> dict:
    tag_level = (level or '').strip().lower() or 'local'
    clean_value = clean_location_name(value)
    return {
        'groupchat_name': f"{clean_value} Community",
        'room_description': f"Local {tag_level} community for {clean_value}. #local #{tag_level}",
        'is_private': False,
        'admin': admin_user,
    }


def ensure_local_community_membership(user: User, *, country: str = '', state: str = '', city: str = '') -> list:
    try:
        from a_rtchat.models import ChatGroup
    except Exception:
        return []

    if not user or not getattr(user, 'is_authenticated', False):
        return []

    levels = [
        ('country', clean_location_name(country)),
        ('state', clean_location_name(state)),
        ('city', clean_location_name(city)),
    ]

    created_or_found = []
    for level, value in levels:
        if not value:
            continue

        group_name = _community_group_name(level, value)
        defaults = _community_defaults(level, value, admin_user=user)
        room, created = ChatGroup.objects.get_or_create(group_name=group_name, defaults=defaults)

        updates = []
        if not getattr(room, 'groupchat_name', None):
            room.groupchat_name = defaults['groupchat_name']
            updates.append('groupchat_name')
        if not str(getattr(room, 'room_description', '') or '').strip():
            room.room_description = defaults['room_description']
            updates.append('room_description')
        if bool(getattr(room, 'is_private', False)):
            room.is_private = False
            updates.append('is_private')
        if updates:
            room.save(update_fields=updates)

        try:
            room.members.add(user)
        except Exception:
            pass

        created_or_found.append(room)

    return created_or_found
