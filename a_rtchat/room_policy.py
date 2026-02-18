from __future__ import annotations


SHOWCASE_GROUP_NAME = 'Showcase Your Work'
FREE_PROMOTION_GROUP_NAME = 'Free Promotion'


def _display_name(room) -> str:
    return (getattr(room, 'groupchat_name', None) or getattr(room, 'group_name', '') or '').strip()


def is_showcase_room(room) -> bool:
    """Return True if this room is the 'Showcase Your Work' group chat.

    Matches by substring to tolerate emoji/prefix variations.
    """
    name = _display_name(room).lower()
    return 'showcase your work' in name


def is_free_promotion_room(room) -> bool:
    """Return True if this room is the 'Free Promotion' group chat.

    Matches by substring to tolerate emoji/prefix variations.
    """
    name = _display_name(room).lower()
    return 'free promotion' in name


def is_links_room(room) -> bool:
    """Return True if this room is explicitly meant for sharing links.

    Matches by substring to tolerate emoji/prefix variations.
    """
    name = _display_name(room).lower()
    return 'links' in name


def is_meme_central_room(room) -> bool:
    """Return True if this room is the 'Meme Central' group chat.

    Matches by substring to tolerate emoji/prefix variations.
    """
    name = _display_name(room).lower()
    return 'meme central' in name


def room_allows_links(room) -> bool:
    # Default policy: links only in private chats + Showcase + Free Promotion.
    return (
        bool(getattr(room, 'is_private', False))
        or is_showcase_room(room)
        or is_free_promotion_room(room)
        or is_links_room(room)
    )


def room_allows_uploads(room) -> bool:
    # Default policy: uploads only in private code rooms + Showcase Your Work.
    # Exception: historically Free Promotion disallowed uploads, but now allowed.
    private_code = bool(getattr(room, 'is_private', False)) and bool(getattr(room, 'is_code_room', False))
    policy_allowed = private_code or is_showcase_room(room) or is_meme_central_room(room)
    if not policy_allowed:
        return False
    return bool(getattr(room, 'allow_media_uploads', True))
