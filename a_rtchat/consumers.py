from channels.generic.websocket import WebsocketConsumer
from django.shortcuts import get_object_or_404
from django.http import Http404
from django.template.loader import render_to_string
from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
import os
from django.db.models import Count
from asgiref.sync import async_to_sync
import json
from a_users.badges import get_verified_user_ids
from .models import *


def _reaction_context_for(message, user):
    emojis = getattr(settings, 'CHAT_REACTION_EMOJIS', ['👍', '❤️', '😂', '😮', '😢', '🙏'])

    counts = {}
    for row in (
        MessageReaction.objects.filter(message=message, emoji__in=emojis)
        .values('emoji')
        .annotate(count=Count('id'))
    ):
        counts[row['emoji']] = int(row['count'] or 0)

    reacted = set(
        MessageReaction.objects.filter(message=message, user=user, emoji__in=emojis)
        .values_list('emoji', flat=True)
    )

    pills = []
    for emoji in emojis:
        c = counts.get(emoji, 0)
        if c:
            pills.append({'emoji': emoji, 'count': c, 'reacted': emoji in reacted})
    message.reaction_pills = pills
    return emojis
from django.conf import settings
from .rate_limit import (
    check_rate_limit,
    get_muted_seconds,
    is_fast_long_message,
    is_same_emoji_spam,
    is_duplicate_message,
    make_key,
    record_abuse_violation,
)

from .moderation import moderate_message
from .channels_utils import chatroom_channel_group_name
from .mentions import extract_mention_usernames, resolve_mentioned_users
from .auto_badges import attach_auto_badges


def _celery_broker_configured() -> bool:
    try:
        env_broker = (os.environ.get('CELERY_BROKER_URL') or '').strip()
        settings_broker = (getattr(settings, 'CELERY_BROKER_URL', None) or '').strip()
        return bool(env_broker or settings_broker)
    except Exception:
        return False
from .models_read import ChatReadState
from .models import Notification
from .link_policy import contains_link
from .link_preview import extract_first_http_url, fetch_link_preview
from .room_policy import room_allows_links
from .challenges import (
    get_active_challenge,
    start_challenge,
    check_message as check_challenge_message,
    end_if_expired as challenge_end_if_expired,
    end_challenge as challenge_end,
    cancel_challenge as challenge_cancel,
    challenge_public_state,
    get_win_loss_totals,
)


def _is_chat_blocked(user) -> bool:
    """Chat-blocked users can read chats but cannot send messages.

    Mirrors the intent of the HTTP views' checks; staff users are never considered blocked.
    """
    try:
        if getattr(user, 'is_staff', False):
            return False
        uid = getattr(user, 'id', None)
        if not uid:
            return False

        # IMPORTANT: do not trust `user.profile` here.
        # In long-lived websocket consumers the profile relation can be cached,
        # so block/unblock wouldn't apply in real-time. Always re-check the DB.
        from a_users.models import Profile
        val = (
            Profile.objects.filter(user_id=uid)
            .values_list('chat_blocked', flat=True)
            .first()
        )
        return bool(val)
    except Exception:
        return False


def _resolve_authenticated_user(scope_user):
    """Convert Channels' lazy user wrapper to a real User model instance."""
    if not getattr(scope_user, 'is_authenticated', False):
        return scope_user
    user_model = get_user_model()
    try:
        return user_model.objects.get(pk=scope_user.pk)
    except Exception:
        return scope_user

class ChatroomConsumer(WebsocketConsumer):
    def _send_challenge_event(self, title: str, body: str, state=None):
        try:
            html = render_to_string('a_rtchat/partials/challenge_event.html', {
                'title': title,
                'body': body,
            })
        except Exception:
            html = ''

        try:
            payload = {
                'type': 'challenge_event',
                'html': html,
                'state': state,
            }
            self.send(text_data=json.dumps(payload))
        except Exception:
            return

    def _broadcast_challenge_event(self, title: str, body: str, state=None):
        try:
            html = render_to_string('a_rtchat/partials/challenge_event.html', {
                'title': title,
                'body': body,
            })
        except Exception:
            html = ''

        payload = {
            'type': 'challenge_event_handler',
            'html': html,
        }
        if state is not None:
            payload['state'] = state

        try:
            async_to_sync(self.channel_layer.group_send)(
                self.room_group_name,
                payload,
            )
        except Exception:
            return

    def _send_challenge_state(self, ch):
        try:
            state = challenge_public_state(ch)
            self.send(text_data=json.dumps({
                'type': 'challenge_state',
                'state': state,
            }))
        except Exception:
            return

    def _broadcast_challenge_end_once(self, ch, title: str = 'Challenge ended'):
        if not ch:
            return
        try:
            meta = dict(getattr(ch, 'meta', None) or {})
            if meta.get('ended_notified'):
                return
            meta['ended_notified'] = True
            ch.meta = meta
            ch.save(update_fields=['meta'])

            winners = meta.get('winners') or []
            losers = meta.get('losers') or []
            msg = f"Winners: {len(winners)} • Losers: {len(losers)}"
            self._broadcast_challenge_event(title, msg, state=challenge_public_state(ch))
        except Exception:
            return

    def _maybe_announce_challenge_end(self, ch):
        if not ch:
            return
        try:
            meta = dict(getattr(ch, 'meta', None) or {})
            if meta.get('ended_notified'):
                return
            meta['ended_notified'] = True
            ch.meta = meta
            ch.save(update_fields=['meta'])

            winners = meta.get('winners') or []
            losers = meta.get('losers') or []
            if winners:
                msg = f"Winners: {len(winners)} • Losers: {len(losers)}"
            else:
                msg = "No winners this time."
            self._broadcast_challenge_event('Challenge ended', msg, state=challenge_public_state(ch))
        except Exception:
            return

    def _room_conn_key(self) -> str:
        room_id = getattr(self, 'chatroom', None)
        room_pk = getattr(room_id, 'pk', None)
        user_id = getattr(getattr(self, 'user', None), 'id', None)
        return f"rtchat:room:{room_pk}:user:{user_id}:conns"

    def _inc_room_conn(self) -> int:
        key = self._room_conn_key()
        try:
            current = int(cache.get(key) or 0)
            new_val = current + 1
            cache.set(key, new_val, timeout=120)
            return new_val
        except Exception:
            try:
                cache.set(key, 1, timeout=120)
            except Exception:
                pass
            return 1

    def _dec_room_conn(self) -> int:
        key = self._room_conn_key()
        try:
            current = int(cache.get(key) or 0)
            new_val = max(0, current - 1)
            if new_val <= 0:
                cache.delete(key)
            else:
                cache.set(key, new_val, timeout=120)
            return new_val
        except Exception:
            try:
                cache.delete(key)
            except Exception:
                pass
            return 0

    def _touch_room_conn(self) -> None:
        key = self._room_conn_key()
        try:
            current = cache.get(key)
            if current is None:
                return
            cache.set(key, int(current), timeout=120)
        except Exception:
            return

    def _cleanup_stale_online_users(self) -> None:
        """Best-effort cleanup when disconnect events are missed (tab crash/server restart).

        We treat a user as online in a room only if they have a live connection key.
        """
        try:
            room = getattr(self, 'chatroom', None)
            if not room:
                return
            user_ids = list(room.users_online.values_list('id', flat=True))
        except Exception:
            return

        stale_ids: list[int] = []
        for uid in user_ids:
            try:
                key = f"rtchat:room:{getattr(room, 'pk', None)}:user:{uid}:conns"
                if cache.get(key) is None:
                    stale_ids.append(int(uid))
            except Exception:
                continue

        if stale_ids:
            try:
                room.users_online.remove(*stale_ids)
            except Exception:
                pass

            # Also clear any cached "online since" markers for these users.
            try:
                room_id = getattr(room, 'pk', None)
                if room_id:
                    for uid in stale_ids:
                        try:
                            cache.delete(f"rtchat:room:{room_id}:user:{int(uid)}:online_since")
                        except Exception:
                            continue
            except Exception:
                pass
    def connect(self):
        self.user = _resolve_authenticated_user(self.scope.get('user'))
        self.chatroom_name = self.scope['url_route']['kwargs']['chatroom_name']

        # If the room was deleted / invalid URL, don't raise and spam logs.
        try:
            self.chatroom = ChatGroup.objects.get(group_name=self.chatroom_name)
        except (ChatGroup.DoesNotExist, Http404):
            # 4404 is a commonly-used close code for "not found".
            try:
                self.close(code=4404)
            except Exception:
                self.close()
            return
        self.room_group_name = chatroom_channel_group_name(self.chatroom)

        # Prevent non-members from connecting to private rooms.
        if getattr(self.chatroom, 'is_private', False):
            if not self.user.is_authenticated:
                self.close()
                return
            if self.user not in self.chatroom.members.all():
                self.close()
                return
        
        async_to_sync(self.channel_layer.group_add)(
            self.room_group_name, self.channel_name
        )
        
        self.accept()

        # Mark current messages as read on open (best-effort).
        if getattr(self.user, 'is_authenticated', False):
            try:
                latest_id = int(
                    GroupMessage.objects.filter(group=self.chatroom)
                    .order_by('-id')
                    .values_list('id', flat=True)
                    .first()
                    or 0
                )
                ChatReadState.objects.update_or_create(
                    user=self.user,
                    group=self.chatroom,
                    defaults={'last_read_message_id': latest_id},
                )
                async_to_sync(self.channel_layer.group_send)(
                    self.room_group_name,
                    {
                        'type': 'read_receipt_handler',
                        'reader_id': getattr(self.user, 'id', None),
                        'last_read_id': latest_id,
                    },
                )
            except Exception:
                pass

        # add and update online users (connection-counted + TTL to avoid stale "online")
        if getattr(self.user, 'is_authenticated', False):
            new_count = self._inc_room_conn()
            if new_count == 1:
                try:
                    if self.user not in self.chatroom.users_online.all():
                        # ManyToMany expects a real User instance or a pk
                        self.chatroom.users_online.add(self.user.pk)
                except Exception:
                    pass

                # Continuous online tracking (used for badges like "Active 10 min")
                try:
                    room_id = getattr(self.chatroom, 'pk', None)
                    uid = int(getattr(self.user, 'id', 0) or 0)
                    if room_id and uid:
                        k = f"rtchat:room:{room_id}:user:{uid}:online_since"
                        if cache.get(k) is None:
                            cache.set(k, timezone.now().timestamp(), timeout=60 * 60 * 6)  # 6h safety TTL
                except Exception:
                    pass
            self.update_online_count()
        
        
    def disconnect(self, close_code):
        # Guard against disconnect being called for a partially initialized connection.
        if hasattr(self, 'room_group_name'):
            async_to_sync(self.channel_layer.group_discard)(
                self.room_group_name, self.channel_name
            )
        # remove and update online users
        if getattr(getattr(self, 'user', None), 'is_authenticated', False) and hasattr(self, 'chatroom'):
            try:
                new_count = self._dec_room_conn()
            except Exception:
                new_count = 0

            if new_count <= 0:
                try:
                    if self.user in self.chatroom.users_online.all():
                        self.chatroom.users_online.remove(self.user.pk)
                except Exception:
                    pass

                # Clear continuous-online marker on last disconnect
                try:
                    room_id = getattr(self.chatroom, 'pk', None)
                    uid = int(getattr(self.user, 'id', 0) or 0)
                    if room_id and uid:
                        cache.delete(f"rtchat:room:{room_id}:user:{uid}:online_since")
                except Exception:
                    pass
            self.update_online_count()
        
    def receive(self, text_data):
        text_data_json = json.loads(text_data)
        if not getattr(self.user, 'is_authenticated', False):
            return

        # Keep the per-room connection TTL alive.
        try:
            self._touch_room_conn()
        except Exception:
            pass

        # Allow blocked users to connect/read, but never allow them to send any events.
        if _is_chat_blocked(self.user):
            return

        muted = get_muted_seconds(getattr(self.user, 'id', 0))
        if muted > 0:
            return

        event_type = (text_data_json.get('type') or '').strip().lower()

        # Client heartbeat (keeps online presence accurate).
        if event_type == 'ping':
            # Also used to expire challenges on server time, even if nobody is sending messages.
            try:
                if getattr(self.chatroom, 'is_private', False):
                    active = get_active_challenge(self.chatroom)
                    if active and challenge_end_if_expired(active):
                        try:
                            active.refresh_from_db()
                        except Exception:
                            pass
                        self._broadcast_challenge_end_once(active, title='Challenge ended')
            except Exception:
                pass
            return

        # Challenges: request current state (used on connect).
        if event_type == 'challenge_state':
            try:
                if getattr(self.chatroom, 'is_private', False):
                    active = get_active_challenge(self.chatroom)
                    self._send_challenge_state(active)
            except Exception:
                pass
            return

        # Challenges: start a new challenge (private chats only).
        if event_type == 'challenge_start':
            if not getattr(self.chatroom, 'is_private', False):
                return
            kind = (text_data_json.get('kind') or '').strip().lower()
            try:
                ch = start_challenge(self.chatroom, created_by=self.user, kind=kind)
            except Exception as e:
                try:
                    self.send(text_data=json.dumps({
                        'type': 'error',
                        'code': 'challenge_start_failed',
                        'message': str(e) or 'Could not start challenge.',
                    }))
                except Exception:
                    pass
                return

            self._broadcast_challenge_event('Challenge started', getattr(ch, 'prompt', '') or '', state=challenge_public_state(ch))
            return

        # Challenges: cancel/end the active challenge.
        if event_type == 'challenge_cancel':
            if not getattr(self.chatroom, 'is_private', False):
                return
            try:
                ch = get_active_challenge(self.chatroom)
                if not ch:
                    return
                if not (getattr(self.user, 'is_staff', False) or getattr(ch, 'created_by_id', None) == getattr(self.user, 'id', None)):
                    return
                cancelled = challenge_cancel(ch)
                self._broadcast_challenge_end_once(cancelled, title='Challenge cancelled')
            except Exception:
                pass
            return

        # Read receipts: client can send {type:'read', last_read_id: <int>}.
        if event_type == 'read':
            try:
                last_read_id = int(text_data_json.get('last_read_id') or 0)
            except Exception:
                last_read_id = 0
            if last_read_id <= 0:
                return
            try:
                obj, _created = ChatReadState.objects.get_or_create(user=self.user, group=self.chatroom)
                if last_read_id > int(getattr(obj, 'last_read_message_id', 0) or 0):
                    obj.last_read_message_id = last_read_id
                    obj.save(update_fields=['last_read_message_id', 'updated'])
                async_to_sync(self.channel_layer.group_send)(
                    self.room_group_name,
                    {
                        'type': 'read_receipt_handler',
                        'reader_id': getattr(self.user, 'id', None),
                        'last_read_id': last_read_id,
                    },
                )
            except Exception:
                pass
            return

        # After a limited number of messages, require verified email to continue sending.
        # (Typing events are still allowed.)
        if event_type != 'typing' and not getattr(self.user, 'is_staff', False):
            try:
                qs = getattr(self.user, 'emailaddress_set', None)
                verified = bool(qs and qs.filter(verified=True).exists())
            except Exception:
                verified = False

            if not verified:
                try:
                    limit = int(getattr(settings, 'UNVERIFIED_CHAT_MESSAGE_LIMIT', 12))
                    sent = GroupMessage.objects.filter(author=self.user).count()
                except Exception:
                    sent = 10**9
                    limit = 12

                if sent >= limit:
                    try:
                        self.send(text_data=json.dumps({
                            'type': 'verify_required',
                            'reason': 'Verify your email to continue chatting.',
                        }))
                    except Exception:
                        pass
                    return

        # Rate limit websocket event spam.
        if event_type == 'typing':
            limit = int(getattr(settings, 'WS_TYPING_RATE_LIMIT', 12))
            period = int(getattr(settings, 'WS_TYPING_RATE_PERIOD', 10))
            rl = check_rate_limit(make_key('ws_typing', self.chatroom_name, self.user.id), limit=limit, period_seconds=period)
            if not rl.allowed:
                record_abuse_violation(
                    scope='ws_typing',
                    user_id=self.user.id,
                    room=self.chatroom_name,
                    window_seconds=int(getattr(settings, 'CHAT_ABUSE_WINDOW', 600)),
                    threshold=int(getattr(settings, 'CHAT_ABUSE_STRIKE_THRESHOLD', 5)),
                    mute_seconds=int(getattr(settings, 'CHAT_ABUSE_MUTE_SECONDS', 60)),
                )
                return
        else:
            limit = int(getattr(settings, 'WS_MSG_RATE_LIMIT', 8))
            period = int(getattr(settings, 'WS_MSG_RATE_PERIOD', 10))
            rl = check_rate_limit(make_key('ws_event', self.chatroom_name, self.user.id), limit=limit, period_seconds=period)
            if not rl.allowed:
                record_abuse_violation(
                    scope='ws_event',
                    user_id=self.user.id,
                    room=self.chatroom_name,
                    window_seconds=int(getattr(settings, 'CHAT_ABUSE_WINDOW', 600)),
                    threshold=int(getattr(settings, 'CHAT_ABUSE_STRIKE_THRESHOLD', 5)),
                    mute_seconds=int(getattr(settings, 'CHAT_ABUSE_MUTE_SECONDS', 60)),
                )
                return
        if event_type == 'typing':
            is_typing = bool(text_data_json.get('is_typing'))
            try:
                display_name = self.user.profile.name
            except Exception:
                display_name = getattr(self.user, 'username', '') or ''

            async_to_sync(self.channel_layer.group_send)(
                self.room_group_name,
                {
                    'type': 'typing_handler',
                    'author_id': getattr(self.user, 'id', None),
                    'username': display_name,
                    'is_typing': is_typing,
                },
            )
            return

        body = (text_data_json.get('body') or '').strip()
        if not body:
            return

        # Commands: scoreboard
        # !sc -> your wins total
        # !sc @username -> other user's wins total
        try:
            parts = body.split()
            if parts and parts[0].lower() == '!sc':
                target_user = self.user
                if len(parts) >= 2:
                    raw = (parts[1] or '').strip()
                    if raw.startswith('@'):
                        raw = raw[1:]
                    raw = raw.strip()
                    if raw:
                        user_model = get_user_model()
                        target_user = user_model.objects.filter(username__iexact=raw).only('id', 'username').first()
                        if not target_user:
                            self._send_challenge_event('Score', f"User '@{raw}' not found.")
                            return
                    else:
                        self._send_challenge_event('Score', 'Usage: !sc  OR  !sc @username')
                        return

                totals = get_win_loss_totals(getattr(target_user, 'id', 0), private_only=True)
                wins = int(totals.get('wins') or 0)
                losses = int(totals.get('losses') or 0)
                completed = int(totals.get('completed') or 0)

                name = getattr(target_user, 'username', 'User')
                msg = f"@{name} • Wins: {wins} • Losses: {losses} • Completed: {completed}"
                self._send_challenge_event('Score', msg)
                return
        except Exception:
            # Never block chat on command issues.
            pass

        # Challenges: only enforced in private chats.
        try:
            if getattr(self.chatroom, 'is_private', False):
                active = get_active_challenge(self.chatroom)
                if active:
                    # End expired challenges lazily.
                    if challenge_end_if_expired(active):
                        try:
                            active.refresh_from_db()
                        except Exception:
                            pass
                        self._broadcast_challenge_end_once(active, title='Challenge ended')
                    else:
                        res = check_challenge_message(active, getattr(self.user, 'id', 0), body)
                        if not res.allowed:
                            try:
                                display_name = self.user.profile.name
                            except Exception:
                                display_name = getattr(self.user, 'username', '') or 'User'

                            self._broadcast_challenge_event(
                                'Rule broken ❌',
                                f"{display_name} lost: {res.reason}",
                                state=challenge_public_state(active),
                            )

                            # If everyone lost, end early.
                            try:
                                member_ids = list(self.chatroom.members.values_list('id', flat=True))
                                losers = set((active.meta or {}).get('losers') or [])
                                if member_ids and losers.issuperset(set(member_ids)):
                                    ended = challenge_end(active)
                                    self._broadcast_challenge_end_once(ended, title='Challenge ended')
                            except Exception:
                                pass
                            return

                        if res.ended:
                            # For finish_meme, the challenge ends inside the checker.
                            try:
                                active.refresh_from_db()
                            except Exception:
                                pass
                            if active and getattr(active, 'status', '') != ChatChallenge.STATUS_ACTIVE:
                                self._broadcast_challenge_end_once(active, title='Challenge ended')
        except Exception:
            # Never block chat on challenge system issues.
            pass

        # Links are only allowed in private chats.
        if contains_link(body) and not room_allows_links(self.chatroom):
            try:
                self.send(text_data=json.dumps({
                    'type': 'error',
                    'code': 'links_not_allowed',
                    'message': 'Links are only allowed in private chats.',
                }))
            except Exception:
                pass
            return

        # AI moderation (Gemini) for WS-created messages.
        pending_moderation = None
        if (
            body
            and int(getattr(settings, 'AI_MODERATION_ENABLED', 0))
            and not getattr(self.user, 'is_staff', False)
        ):
            try:
                last_user_msgs = list(
                    self.chatroom.chat_messages.filter(author=self.user)
                    .exclude(body__isnull=True)
                    .exclude(body='')
                    .order_by('-created')
                    .values_list('body', flat=True)[:5]
                )
            except Exception:
                last_user_msgs = []

            ctx = {
                'room': getattr(self.chatroom, 'group_name', self.chatroom_name),
                'room_id': getattr(self.chatroom, 'id', None),
                'user_id': getattr(self.user, 'id', None),
                'last_user_messages': list(reversed(list(last_user_msgs))),
            }

            decision = moderate_message(text=body, context=ctx)
            action = decision.action

            block_min = int(getattr(settings, 'AI_BLOCK_MIN_SEVERITY', 2))
            flag_min = int(getattr(settings, 'AI_FLAG_MIN_SEVERITY', 1))
            min_conf = float(getattr(settings, 'AI_MIN_CONFIDENCE', 0.55))

            if decision.confidence < min_conf:
                action = 'allow'
            elif decision.severity >= block_min:
                action = 'block'
            elif decision.severity >= flag_min:
                action = 'flag'

            log_all = bool(int(getattr(settings, 'AI_LOG_ALL', 0)))
            if log_all or action == 'flag':
                pending_moderation = (decision, action)

            if action == 'block':
                ModerationEvent.objects.create(
                    user=self.user,
                    room=self.chatroom,
                    message=None,
                    text=body[:2000],
                    action='block',
                    categories=decision.categories,
                    severity=decision.severity,
                    confidence=decision.confidence,
                    reason=decision.reason,
                    source='gemini',
                    meta={
                        'model_action': decision.action,
                        'suggested_mute_seconds': decision.suggested_mute_seconds,
                        'via': 'ws',
                    },
                )

                weight = 1 + int(decision.severity >= 2)
                _, auto_muted = record_abuse_violation(
                    scope='ai_block',
                    user_id=self.user.id,
                    room=self.chatroom_name,
                    window_seconds=int(getattr(settings, 'CHAT_ABUSE_WINDOW', 600)),
                    threshold=int(getattr(settings, 'CHAT_ABUSE_STRIKE_THRESHOLD', 5)),
                    mute_seconds=int(getattr(settings, 'CHAT_ABUSE_MUTE_SECONDS', 60)),
                    weight=weight,
                )
                if auto_muted:
                    pass
                return

            if action == 'flag':
                record_abuse_violation(
                    scope='ai_flag',
                    user_id=self.user.id,
                    room=self.chatroom_name,
                    window_seconds=int(getattr(settings, 'CHAT_ABUSE_WINDOW', 600)),
                    threshold=int(getattr(settings, 'CHAT_ABUSE_STRIKE_THRESHOLD', 5)),
                    mute_seconds=int(getattr(settings, 'CHAT_ABUSE_MUTE_SECONDS', 60)),
                    weight=1,
                )

        # Same emoji spam.
        is_emoji_spam, _emoji_retry = is_same_emoji_spam(
            body,
            min_repeats=int(getattr(settings, 'EMOJI_SPAM_MIN_REPEATS', 4)),
            ttl_seconds=int(getattr(settings, 'EMOJI_SPAM_TTL', 15)),
        )
        if is_emoji_spam:
            record_abuse_violation(
                scope='emoji_spam',
                user_id=self.user.id,
                room=self.chatroom_name,
                window_seconds=int(getattr(settings, 'CHAT_ABUSE_WINDOW', 600)),
                threshold=int(getattr(settings, 'CHAT_ABUSE_STRIKE_THRESHOLD', 5)),
                mute_seconds=int(getattr(settings, 'CHAT_ABUSE_MUTE_SECONDS', 60)),
                weight=2,
            )
            return

        # Room-wide flood protection (WS direct send).
        room_rl = check_rate_limit(
            make_key('room_msg', self.chatroom_name),
            limit=int(getattr(settings, 'ROOM_MSG_RATE_LIMIT', 30)),
            period_seconds=int(getattr(settings, 'ROOM_MSG_RATE_PERIOD', 10)),
        )
        if not room_rl.allowed:
            record_abuse_violation(
                scope='room_flood',
                user_id=self.user.id,
                room=self.chatroom_name,
                window_seconds=int(getattr(settings, 'CHAT_ABUSE_WINDOW', 600)),
                threshold=int(getattr(settings, 'CHAT_ABUSE_STRIKE_THRESHOLD', 5)),
                mute_seconds=int(getattr(settings, 'CHAT_ABUSE_MUTE_SECONDS', 60)),
            )
            return

        # Duplicate message detection.
        is_dup, _dup_retry = is_duplicate_message(
            self.chatroom_name,
            self.user.id,
            body,
            ttl_seconds=int(getattr(settings, 'DUPLICATE_MSG_TTL', 15)),
        )
        if is_dup:
            record_abuse_violation(
                scope='dup_msg',
                user_id=self.user.id,
                room=self.chatroom_name,
                window_seconds=int(getattr(settings, 'CHAT_ABUSE_WINDOW', 600)),
                threshold=int(getattr(settings, 'CHAT_ABUSE_STRIKE_THRESHOLD', 5)),
                mute_seconds=int(getattr(settings, 'CHAT_ABUSE_MUTE_SECONDS', 60)),
                weight=2,
            )
            return

        # Fast long message heuristic (WS path).
        is_fast, _fast_retry = is_fast_long_message(
            self.chatroom_name,
            self.user.id,
            message_length=len(body),
            long_length_threshold=int(getattr(settings, 'FAST_LONG_MSG_LEN', 80)),
            min_interval_seconds=int(getattr(settings, 'FAST_LONG_MSG_MIN_INTERVAL', 1)),
        )
        if is_fast:
            record_abuse_violation(
                scope='fast_long_msg',
                user_id=self.user.id,
                room=self.chatroom_name,
                window_seconds=int(getattr(settings, 'CHAT_ABUSE_WINDOW', 600)),
                threshold=int(getattr(settings, 'CHAT_ABUSE_STRIKE_THRESHOLD', 5)),
                mute_seconds=int(getattr(settings, 'CHAT_ABUSE_MUTE_SECONDS', 60)),
            )
            return

        client_nonce = None
        try:
            raw_nonce = text_data_json.get('client_nonce')
            if raw_nonce is not None:
                client_nonce = str(raw_nonce)[:64]
        except Exception:
            client_nonce = None

        reply_to = None
        reply_to_id = text_data_json.get('reply_to_id')
        if reply_to_id:
            try:
                reply_to_pk = int(reply_to_id)
            except (TypeError, ValueError):
                reply_to_pk = None
            if reply_to_pk:
                reply_to = GroupMessage.objects.filter(pk=reply_to_pk, group=self.chatroom).first()
        
        message = GroupMessage.objects.create(
            body = body,
            author = self.user,
            group = self.chatroom,
            reply_to=reply_to,
        )

        # Retention: keep only the newest messages per room (best-effort)
        try:
            from a_rtchat.retention import trim_chat_group_messages

            trim_chat_group_messages(
                chat_group_id=getattr(self.chatroom, 'id', 0),
                keep_last=int(getattr(settings, 'CHAT_MAX_MESSAGES_PER_ROOM', 12000)),
            )
        except Exception:
            pass

        # Public chat bot (Natasha): reply occasionally, async.
        try:
            if (getattr(self.chatroom, 'group_name', '') == 'public-chat'):
                from .natasha_bot import trigger_natasha_reply_after_commit, NATASHA_USERNAME

                if getattr(self.user, 'username', '') != NATASHA_USERNAME:
                    trigger_natasha_reply_after_commit(self.chatroom.id, message.id)
        except Exception:
            pass

        # Best-effort link preview (kept intentionally lightweight).
        try:
            url = extract_first_http_url(body)
            preview = fetch_link_preview(url) if url else None
            if preview:
                message.link_url = preview.url
                message.link_title = preview.title
                message.link_description = preview.description
                message.link_image = preview.image
                message.link_site_name = preview.site_name
                message.save(update_fields=['link_url', 'link_title', 'link_description', 'link_image', 'link_site_name'])
        except Exception:
            pass

        # Mention notifications (per-user channel): @username
        try:
            usernames = extract_mention_usernames(body)
            if usernames:
                mentioned = resolve_mentioned_users(usernames)
                member_ids = None
                # Only restrict mentions to members in private rooms.
                # Group chats are joinable/public, so allow tagging even if the user hasn't joined yet.
                if bool(getattr(self.chatroom, 'is_private', False)):
                    member_ids = set(self.chatroom.members.values_list('id', flat=True))

                preview = (body or '')[:140]
                for u in mentioned:
                    if not getattr(u, 'id', None) or u.id == getattr(self.user, 'id', None):
                        continue
                    if member_ids is not None and u.id not in member_ids:
                        continue

                    # Persist notification only if the user is offline (not connected in any chat WS).
                    try:
                        from a_rtchat.notifications import should_persist_notification

                        if should_persist_notification(
                            user_id=u.id,
                            chatroom_name=getattr(self.chatroom, 'group_name', self.chatroom_name) or self.chatroom_name,
                        ) or bool(getattr(self.chatroom, 'is_private', False)):
                            Notification.objects.create(
                                user=u,
                                from_user=self.user,
                                type='mention',
                                chatroom_name=getattr(self.chatroom, 'group_name', self.chatroom_name) or self.chatroom_name,
                                message_id=message.id,
                                preview=preview,
                                url=f"/chat/room/{(getattr(self.chatroom, 'group_name', self.chatroom_name) or self.chatroom_name) }#msg-{message.id}",
                            )
                    except Exception:
                        pass

                    async_to_sync(self.channel_layer.group_send)(
                        f"notify_user_{u.id}",
                        {
                            'type': 'mention_notify_handler',
                            'from_username': getattr(self.user, 'username', '') or '',
                            'chatroom_name': getattr(self.chatroom, 'group_name', self.chatroom_name) or self.chatroom_name,
                            'message_id': message.id,
                            'preview': preview,
                        },
                    )

                    # Optional: push notification via FCM (offline / background)
                    try:
                        from a_users.tasks import send_mention_push_task

                        if _celery_broker_configured():
                            send_mention_push_task.delay(
                                u.id,
                                from_username=getattr(self.user, 'username', '') or '',
                                chatroom_name=getattr(self.chatroom, 'group_name', self.chatroom_name) or self.chatroom_name,
                                preview=preview,
                            )
                    except Exception:
                        pass
        except Exception:
            # Best-effort: don't block message sends on notify issues
            pass

        if pending_moderation:
            decision, action = pending_moderation
            ModerationEvent.objects.create(
                user=self.user,
                room=self.chatroom,
                message=message,
                text=body[:2000],
                action=action,
                categories=decision.categories,
                severity=decision.severity,
                confidence=decision.confidence,
                reason=decision.reason,
                source='gemini',
                meta={
                    'model_action': decision.action,
                    'suggested_mute_seconds': decision.suggested_mute_seconds,
                    'linked': True,
                    'via': 'ws',
                },
            )
        event = {
            'type': 'message_handler',
            'message_id': message.id,
            'author_id': getattr(self.user, 'id', None),
        }
        if client_nonce:
            event['client_nonce'] = client_nonce
        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name, event
        )

        # Reply notification (best-effort)
        try:
            if reply_to and getattr(reply_to, 'author_id', None) and reply_to.author_id != getattr(self.user, 'id', None):
                target_id = int(reply_to.author_id)
                room_name = getattr(self.chatroom, 'group_name', self.chatroom_name) or self.chatroom_name
                preview = (body or '')[:140]

                # Persist only if the user is not online in this chat.
                try:
                    from a_rtchat.notifications import should_persist_notification

                    if should_persist_notification(user_id=target_id, chatroom_name=room_name) or bool(getattr(self.chatroom, 'is_private', False)):
                        Notification.objects.create(
                            user_id=target_id,
                            from_user=self.user,
                            type='reply',
                            chatroom_name=room_name,
                            message_id=message.id,
                            preview=preview,
                            url=f"/chat/room/{room_name}#msg-{message.id}",
                        )
                except Exception:
                    pass

                async_to_sync(self.channel_layer.group_send)(
                    f"notify_user_{target_id}",
                    {
                        'type': 'reply_notify_handler',
                        'from_username': getattr(self.user, 'username', '') or '',
                        'chatroom_name': room_name,
                        'message_id': message.id,
                        'preview': preview,
                    },
                )
        except Exception:
            pass

    def typing_handler(self, event):
        if event.get('author_id') == getattr(self.user, 'id', None):
            return

        self.send(text_data=json.dumps({
            'type': 'typing',
            'author_id': event.get('author_id'),
            'username': event.get('username') or '',
            'is_typing': bool(event.get('is_typing')),
        }))
        
    def message_handler(self, event):
        if event.get('skip_sender') and event.get('author_id') == getattr(self.user, 'id', None):
            return
        message_id = event['message_id']
        message = GroupMessage.objects.get(id=message_id)
        attach_auto_badges([message], self.chatroom)
        reaction_emojis = _reaction_context_for(message, self.user)

        other_last_read_id = 0
        if getattr(self.chatroom, 'is_private', False) and getattr(self.user, 'is_authenticated', False):
            try:
                other = self.chatroom.members.exclude(id=self.user.id).first()
                if other:
                    other_last_read_id = int(
                        ChatReadState.objects.filter(user=other, group=self.chatroom)
                        .values_list('last_read_message_id', flat=True)
                        .first()
                        or 0
                    )
            except Exception:
                other_last_read_id = 0

        context = {
            'message': message,
            'user': self.user,
            'chat_group': self.chatroom,
            'reaction_emojis': reaction_emojis,
            'other_last_read_id': other_last_read_id,
            'verified_user_ids': get_verified_user_ids([getattr(message, 'author_id', None)]),
        }
        html = render_to_string("a_rtchat/chat_message.html", context=context)
        payload = {
            'type': 'chat_message',
            'html': html,
        }
        if event.get('client_nonce'):
            payload['client_nonce'] = event.get('client_nonce')
        if event.get('author_id'):
            payload['author_id'] = event.get('author_id')
        self.send(text_data=json.dumps(payload))

    def challenge_event_handler(self, event):
        try:
            self.send(text_data=json.dumps({
                'type': 'challenge_event',
                'html': event.get('html') or '',
                'state': event.get('state'),
            }))
        except Exception:
            return

    def read_receipt_handler(self, event):
        try:
            self.send(text_data=json.dumps({
                'type': 'read_receipt',
                'reader_id': event.get('reader_id') or 0,
                'last_read_id': event.get('last_read_id') or 0,
            }))
        except Exception:
            return


    def message_update_handler(self, event):
        message_id = event.get('message_id')
        if not message_id:
            return
        message = GroupMessage.objects.filter(id=message_id).first()
        if not message:
            return
        attach_auto_badges([message], self.chatroom)
        reaction_emojis = _reaction_context_for(message, self.user)

        other_last_read_id = 0
        if getattr(self.chatroom, 'is_private', False) and getattr(self.user, 'is_authenticated', False):
            try:
                other = self.chatroom.members.exclude(id=self.user.id).first()
                if other:
                    other_last_read_id = int(
                        ChatReadState.objects.filter(user=other, group=self.chatroom)
                        .values_list('last_read_message_id', flat=True)
                        .first()
                        or 0
                    )
            except Exception:
                other_last_read_id = 0

        context = {
            'message': message,
            'user': self.user,
            'chat_group': self.chatroom,
            'reaction_emojis': reaction_emojis,
            'other_last_read_id': other_last_read_id,
            'verified_user_ids': get_verified_user_ids([getattr(message, 'author_id', None)]),
        }
        html = render_to_string("a_rtchat/chat_message.html", context=context)
        self.send(text_data=json.dumps({
            'type': 'message_update',
            'message_id': message_id,
            'html': html,
        }))


    def reactions_handler(self, event):
        message_id = event.get('message_id')
        if not message_id:
            return
        message = GroupMessage.objects.filter(id=message_id).first()
        if not message:
            return

        reaction_emojis = _reaction_context_for(message, self.user)
        html = render_to_string(
            "a_rtchat/partials/reactions_bar.html",
            context={
                'message': message,
                'user': self.user,
                'chat_group': self.chatroom,
                'reaction_emojis': reaction_emojis,
            },
        )
        self.send(text_data=json.dumps({
            'type': 'reactions',
            'message_id': message_id,
            'html': html,
        }))


    def message_delete_handler(self, event):
        message_id = event.get('message_id')
        if not message_id:
            return
        self.send(text_data=json.dumps({
            'type': 'message_delete',
            'message_id': message_id,
        }))
        
        
    def update_online_count(self):
        # Best-effort cleanup to avoid "ghost" online users.
        try:
            self._cleanup_stale_online_users()
        except Exception:
            pass

        online_count = self.chatroom.users_online.count()
        
        event = {
            'type': 'online_count_handler',
            'online_count': online_count
        }
        async_to_sync(self.channel_layer.group_send)(self.room_group_name, event)
        
        
    def online_count_handler(self, event):
        online_count = event['online_count']
        self.send(text_data=json.dumps({
            'type': 'online_count',
            'online_count': online_count,
        }))


    def call_invite_handler(self, event):
        """Notify other members about an incoming call."""
        if event.get('author_id') == getattr(self.user, 'id', None):
            return

        # DND: user should not receive call invites.
        try:
            from a_users.models import Profile

            if Profile.objects.filter(user_id=getattr(self.user, 'id', None), is_dnd=True).exists():
                return
        except Exception:
            pass

        self.send(text_data=json.dumps({
            'type': 'call_invite',
            'call_type': event.get('call_type') or 'voice',
            'from_username': event.get('from_username') or '',
            'chatroom_name': self.chatroom_name,
        }))


    def call_presence_handler(self, event):
        """Broadcast call participant presence (best-effort, for UI display)."""
        self.send(text_data=json.dumps({
            'type': 'call_presence',
            'action': event.get('action') or 'join',
            'uid': event.get('uid'),
            'username': event.get('username') or '',
            'call_type': event.get('call_type') or 'voice',
            'chatroom_name': self.chatroom_name,
        }))


    def call_control_handler(self, event):
        """Call control signals (e.g., end call for everyone)."""
        # DND: user should not receive call UI events.
        try:
            from a_users.models import Profile

            if Profile.objects.filter(user_id=getattr(self.user, 'id', None), is_dnd=True).exists():
                return
        except Exception:
            pass
        self.send(text_data=json.dumps({
            'type': 'call_control',
            'action': event.get('action') or '',
            'from_username': event.get('from_username') or '',
            'call_type': event.get('call_type') or 'voice',
            'chatroom_name': self.chatroom_name,
        }))
        
        
class OnlineStatusConsumer(WebsocketConsumer):
    def _conn_key(self) -> str:
        return f"online_status_conn:{getattr(self.user, 'id', 0)}"

    def _inc_conn(self) -> int:
        key = self._conn_key()
        try:
            val = cache.get(key)
            if val is None:
                cache.set(key, 1, timeout=60 * 60)
                return 1
            new_val = int(val) + 1
            cache.set(key, new_val, timeout=60 * 60)
            return new_val
        except Exception:
            try:
                cache.set(key, 1, timeout=60 * 60)
            except Exception:
                pass
            return 1

    def _dec_conn(self) -> int:
        key = self._conn_key()
        try:
            val = cache.get(key)
            if val is None:
                return 0
            new_val = max(0, int(val) - 1)
            if new_val <= 0:
                cache.delete(key)
            else:
                cache.set(key, new_val, timeout=60 * 60)
            return new_val
        except Exception:
            try:
                cache.delete(key)
            except Exception:
                pass
            return 0

    def connect(self):
        self.user = _resolve_authenticated_user(self.scope.get('user'))
        if not getattr(self.user, 'is_authenticated', False):
            self.close()
            return
        self.group_name = 'online-status'
        try:
            self.group, _ = ChatGroup.objects.get_or_create(group_name=self.group_name)
        except Exception:
            self.close()
            return

        # Connection counting prevents flicker when navigating (old socket closes
        # after the new page opens a new socket).
        new_count = self._inc_conn()
        if new_count == 1:
            try:
                if self.user not in self.group.users_online.all():
                    self.group.users_online.add(self.user.pk)
            except Exception:
                pass
            
        async_to_sync(self.channel_layer.group_add)(
            self.group_name, self.channel_name
        )
        
        self.accept()
        self.online_status()
        
        
    def disconnect(self, close_code):
        try:
            new_count = self._dec_conn()
        except Exception:
            new_count = 0

        if new_count <= 0:
            try:
                if self.user in self.group.users_online.all():
                    self.group.users_online.remove(self.user.pk)
            except Exception:
                pass
            
        async_to_sync(self.channel_layer.group_discard)(
            self.group_name, self.channel_name
        )
        self.online_status()
        
        
    def online_status(self):
        event = {
            'type': 'online_status_handler'
        }
        async_to_sync(self.channel_layer.group_send)(
            self.group_name, event
        ) 
        
    def online_status_handler(self, event):
        online_users = self.group.users_online.exclude(id=self.user.id)
        public_chat_users = ChatGroup.objects.get(group_name='public-chat').users_online.exclude(id=self.user.id)
        
        my_chats = self.user.chat_groups.all()
        private_chats_with_users = [chat for chat in my_chats.filter(is_private=True) if chat.users_online.exclude(id=self.user.id)]
        group_chats_with_users = [chat for chat in my_chats.filter(groupchat_name__isnull=False) if chat.users_online.exclude(id=self.user.id)]
        
        if public_chat_users or private_chats_with_users or group_chats_with_users:
            online_in_chats = True
        else:
            online_in_chats = False
        
        context = {
            'online_users': online_users,
            'online_in_chats': online_in_chats,
            'public_chat_users': public_chat_users,
            'user': self.user
        }
        html = render_to_string("a_rtchat/partials/online_status.html", context=context)
        self.send(text_data=html) 


class NotificationsConsumer(WebsocketConsumer):
    """Per-user websocket for global notifications (e.g., call invites).

    This allows users to receive incoming call toasts even if they switch to a
    different chatroom page/tab.
    """

    def connect(self):
        self.user = _resolve_authenticated_user(self.scope.get('user'))
        if not getattr(self.user, 'is_authenticated', False):
            self.close()
            return

        self.group_name = f"notify_user_{self.user.id}"
        async_to_sync(self.channel_layer.group_add)(
            self.group_name, self.channel_name
        )

        self.accept()

    def disconnect(self, close_code):
        try:
            async_to_sync(self.channel_layer.group_discard)(
                self.group_name, self.channel_name
            )
        except Exception:
            pass

    def call_invite_notify_handler(self, event):
        # DND: user should not receive call invites.
        try:
            from a_users.models import Profile

            if Profile.objects.filter(user_id=getattr(self.user, 'id', None), is_dnd=True).exists():
                return
        except Exception:
            pass
        self.send(text_data=json.dumps({
            'type': 'call_invite',
            'call_type': event.get('call_type') or 'voice',
            'from_username': event.get('from_username') or '',
            'chatroom_name': event.get('chatroom_name') or '',
            'call_url': event.get('call_url') or '',
            'call_event_url': event.get('call_event_url') or '',
        }))

    def call_control_notify_handler(self, event):
        # DND: user should not receive call UI events.
        try:
            from a_users.models import Profile

            if Profile.objects.filter(user_id=getattr(self.user, 'id', None), is_dnd=True).exists():
                return
        except Exception:
            pass
        self.send(text_data=json.dumps({
            'type': 'call_control',
            'action': event.get('action') or '',
            'from_username': event.get('from_username') or '',
            'call_type': event.get('call_type') or 'voice',
            'chatroom_name': event.get('chatroom_name') or '',
        }))

    def mention_notify_handler(self, event):
        try:
            from a_users.models import Profile

            if Profile.objects.filter(user_id=getattr(self.user, 'id', None), is_dnd=True).exists():
                return
        except Exception:
            pass
        self.send(text_data=json.dumps({
            'type': 'mention',
            'from_username': event.get('from_username') or '',
            'chatroom_name': event.get('chatroom_name') or '',
            'message_id': event.get('message_id') or 0,
            'preview': event.get('preview') or '',
        }))

    def reply_notify_handler(self, event):
        try:
            from a_users.models import Profile

            if Profile.objects.filter(user_id=getattr(self.user, 'id', None), is_dnd=True).exists():
                return
        except Exception:
            pass
        self.send(text_data=json.dumps({
            'type': 'reply',
            'from_username': event.get('from_username') or '',
            'chatroom_name': event.get('chatroom_name') or '',
            'message_id': event.get('message_id') or 0,
            'preview': event.get('preview') or '',
        }))

    def follow_notify_handler(self, event):
        try:
            from a_users.models import Profile

            if Profile.objects.filter(user_id=getattr(self.user, 'id', None), is_dnd=True).exists():
                return
        except Exception:
            pass
        self.send(text_data=json.dumps({
            'type': 'follow',
            'from_username': event.get('from_username') or '',
            'url': event.get('url') or '',
            'preview': event.get('preview') or '',
        }))

    def support_notify_handler(self, event):
        try:
            from a_users.models import Profile

            if Profile.objects.filter(user_id=getattr(self.user, 'id', None), is_dnd=True).exists():
                return
        except Exception:
            pass
        self.send(text_data=json.dumps({
            'type': 'support',
            'preview': event.get('preview') or '',
            'url': event.get('url') or '',
        }))

    def chat_block_status_notify_handler(self, event):
        try:
            from a_users.models import Profile

            if Profile.objects.filter(user_id=getattr(self.user, 'id', None), is_dnd=True).exists():
                return
        except Exception:
            pass

        self.send(text_data=json.dumps({
            'type': 'chat_block_status',
            'blocked': bool(event.get('blocked')),
            'by_username': event.get('by_username') or '',
        }))


class ProfilePresenceConsumer(WebsocketConsumer):
    """Realtime online/offline for a single user's profile page."""

    def connect(self):
        self.user = _resolve_authenticated_user(self.scope.get('user'))
        if not getattr(self.user, 'is_authenticated', False):
            self.close()
            return

        username = None
        try:
            username = (self.scope.get('url_route', {})
                        .get('kwargs', {})
                        .get('username'))
        except Exception:
            username = None

        if not username:
            self.close()
            return

        try:
            target = get_object_or_404(User, username=username)
        except Exception:
            self.close()
            return

        target_profile = getattr(target, 'profile', None)
        is_bot = bool(getattr(target_profile, 'is_bot', False))
        is_stealth = bool(getattr(target_profile, 'is_stealth', False))
        is_owner = bool(getattr(self.user, 'id', None) == getattr(target, 'id', None))

        self.target_id = getattr(target, 'id', None)
        self.group_name = 'online-status'
        self.is_owner = bool(is_owner)

        self.accept()

        # Bots: don't expose presence.
        if is_bot:
            try:
                self.send(text_data=json.dumps({'type': 'presence', 'online': False}))
            except Exception:
                pass
            try:
                self.close()
            except Exception:
                pass
            return

        # Stealth: everyone except owner sees offline (no realtime subscription).
        if is_stealth and not is_owner:
            try:
                self.send(text_data=json.dumps({'type': 'presence', 'online': False}))
            except Exception:
                pass
            try:
                self.close()
            except Exception:
                pass
            return

        # Subscribe to online-status updates and re-check visibility rules on every event.
        try:
            async_to_sync(self.channel_layer.group_add)(
                self.group_name, self.channel_name
            )
        except Exception:
            pass

        # Initial state
        try:
            online = ChatGroup.objects.filter(group_name='online-status', users_online=target).exists()
        except Exception:
            online = False
        try:
            self.send(text_data=json.dumps({'type': 'presence', 'online': bool(online)}))
        except Exception:
            pass

    def disconnect(self, close_code):
        try:
            if getattr(self, 'group_name', None):
                async_to_sync(self.channel_layer.group_discard)(
                    self.group_name, self.channel_name
                )
        except Exception:
            pass

    def online_status_handler(self, event):
        """Recompute target's visible online state whenever the global presence changes."""
        try:
            from a_users.models import Profile

            prof = (
                Profile.objects
                .filter(user_id=self.target_id)
                .values('is_stealth', 'is_bot')
                .first()
                or {}
            )
            is_bot = bool(prof.get('is_bot', False))
            is_stealth = bool(prof.get('is_stealth', False))

            # Bots: don't expose presence.
            if is_bot:
                try:
                    self.send(text_data=json.dumps({'type': 'presence', 'online': False}))
                except Exception:
                    pass
                try:
                    self.close()
                except Exception:
                    pass
                return

            # Stealth: everyone except owner sees offline.
            if is_stealth and not bool(getattr(self, 'is_owner', False)):
                try:
                    self.send(text_data=json.dumps({'type': 'presence', 'online': False}))
                except Exception:
                    pass
                try:
                    self.close()
                except Exception:
                    pass
                return

            online = bool(ChatGroup.objects.filter(group_name='online-status', users_online_id=self.target_id).exists())
            self.send(text_data=json.dumps({'type': 'presence', 'online': online}))
        except Exception:
            return

    def chat_block_status_notify_handler(self, event):
        try:
            from a_users.models import Profile

            if Profile.objects.filter(user_id=getattr(self.user, 'id', None), is_dnd=True).exists():
                return
        except Exception:
            pass
        self.send(text_data=json.dumps({
            'type': 'chat_block_status',
            'blocked': bool(event.get('blocked')),
            'by_username': event.get('by_username') or '',
        }))