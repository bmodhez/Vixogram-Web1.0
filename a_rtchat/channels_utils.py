from __future__ import annotations

from .models import ChatGroup


def chatroom_channel_group_name(chat_group: ChatGroup) -> str:
    """Return a Channels-safe group name for a chat room.

    Channels restricts group names to ASCII alphanumerics plus: hyphen, underscore, period.
    We derive the group name from the DB primary key so it remains stable even if the
    human-visible room name contains spaces/emojis.
    """
    room_id = getattr(chat_group, 'pk', None)
    if room_id is None:
        # Should not happen for saved rooms; keep it safe anyway.
        return "chatroom.unknown"
    return f"chatroom.{room_id}"
