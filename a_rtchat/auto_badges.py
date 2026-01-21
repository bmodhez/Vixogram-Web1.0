from __future__ import annotations

from datetime import timedelta
from typing import Dict, Iterable, List, Optional

from django.db.models import Count, DurationField, ExpressionWrapper, F, Max, Min
from django.core.cache import cache
from django.utils import timezone

from .models import ChatGroup, GroupMessage, MessageReaction


def compute_auto_badges(
    chat_group: ChatGroup,
    user_ids: Iterable[int],
    now=None,
) -> Dict[int, List[dict]]:
    """Compute lightweight, behavior-based badges for users inside a chat room.

    These badges are meant to be dynamic (not daily streaks) and are computed from
    recent room activity.

    Returns: {user_id: [{key, icon, label}, ...]}
    """

    ids = [int(uid) for uid in set(int(x) for x in (user_ids or []) if x)]
    if not ids:
        return {}

    now = now or timezone.now()

    out: Dict[int, List[dict]] = {uid: [] for uid in ids}

    def add(uid: int, key: str, icon: str, label: str) -> None:
        if uid not in out:
            return
        out[uid].append({'key': key, 'icon': icon, 'label': label})

    # 🔥 Active 10 min
    # Show only when the user has been continuously online in this room for >=10 minutes.
    # If they leave before 10 and come back, the timer resets.
    try:
        room_id = int(getattr(chat_group, 'pk', 0) or 0)
        if room_id:
            online_ids = set(
                int(x)
                for x in chat_group.users_online.filter(id__in=ids).values_list('id', flat=True)
                if int(x) > 0
            )

            for uid in online_ids:
                try:
                    k = f"rtchat:room:{room_id}:user:{uid}:online_since"
                    ts = cache.get(k)
                    if ts is None:
                        continue
                    since = float(ts)
                    if (now.timestamp() - since) >= (10 * 60):
                        add(uid, 'active_10m', '🔥', 'Active 10 min')
                except Exception:
                    continue
    except Exception:
        pass

    # ⚡ Fast replier (frequent quick replies in the last 24h)
    try:
        since = now - timedelta(hours=24)
        delta = ExpressionWrapper(F('created') - F('reply_to__created'), output_field=DurationField())
        rows = (
            GroupMessage.objects.filter(
                group=chat_group,
                author_id__in=ids,
                reply_to__isnull=False,
                created__gte=since,
            )
            .exclude(reply_to__author_id=F('author_id'))
            .annotate(delta=delta)
            .filter(delta__lte=timedelta(seconds=90))
            .values('author_id')
            .annotate(c=Count('id'))
        )
        for r in rows:
            uid = int(r['author_id'])
            c = int(r.get('c') or 0)
            if c >= 3:
                add(uid, 'fast_replier', '⚡', 'Fast replier')
    except Exception:
        pass

    # 👑 Room OG (room admin OR joined early in room lifetime)
    try:
        admin_id = int(getattr(chat_group, 'admin_id', 0) or 0)
        if admin_id and admin_id in out:
            add(admin_id, 'room_og', '👑', 'Room OG')

        # If user's first message was within 7 days of room creation, count as OG.
        created = getattr(chat_group, 'created', None)
        if created:
            cutoff = created + timedelta(days=7)
            rows = (
                GroupMessage.objects.filter(group=chat_group, author_id__in=ids)
                .values('author_id')
                .annotate(first=Min('created'))
            )
            for r in rows:
                uid = int(r['author_id'])
                if uid == admin_id:
                    continue
                first = r.get('first')
                if first and first <= cutoff:
                    add(uid, 'room_og', '👑', 'Room OG')
    except Exception:
        pass

    # 🧠 Helpful guy (their messages received reactions recently)
    try:
        since = now - timedelta(days=7)
        rows = (
            MessageReaction.objects.filter(
                message__group=chat_group,
                message__author_id__in=ids,
                created__gte=since,
            )
            .exclude(user_id=F('message__author_id'))
            .values('message__author_id')
            .annotate(c=Count('id'))
        )
        for r in rows:
            uid = int(r['message__author_id'])
            c = int(r.get('c') or 0)
            if c >= 5:
                add(uid, 'helpful', '🧠', 'Helpful guy')
    except Exception:
        pass

    # Keep stable ordering for UX
    order = {'active_10m': 0, 'fast_replier': 1, 'room_og': 2, 'helpful': 3}
    for uid in list(out.keys()):
        out[uid].sort(key=lambda b: order.get(b.get('key') or '', 999))

    return out


def attach_auto_badges(messages: Iterable[GroupMessage], chat_group: ChatGroup) -> None:
    """Attach computed badges onto message objects as `message.auto_badges`.

    This avoids needing template filters and keeps rendering changes small.
    """

    msgs = list(messages or [])
    if not msgs:
        return

    user_ids = [getattr(m, 'author_id', None) for m in msgs]
    mapping = compute_auto_badges(chat_group=chat_group, user_ids=user_ids)
    for m in msgs:
        uid = int(getattr(m, 'author_id', 0) or 0)
        try:
            setattr(m, 'auto_badges', mapping.get(uid, []))
        except Exception:
            pass
