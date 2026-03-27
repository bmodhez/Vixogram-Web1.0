from __future__ import annotations

import json
import time
import uuid

from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer
from django.conf import settings
from django.core.cache import cache


QUEUE_KEY = 'rv:queue:v1'
WAITING_KEY_PREFIX = 'rv:waiting:v1:'
PAIR_KEY_PREFIX = 'rv:pair:v1:'
ACTIVE_USERS_KEY = 'rv:active:v1'
LOCK_KEY = 'rv:lock:v1'
RECENT_PAIR_KEY_PREFIX = 'rv:recentpair:v1:'


def _now_ts() -> int:
    try:
        return int(time.time())
    except Exception:
        return 0


class RandomVideoConsumer(WebsocketConsumer):
    def _rematch_fallback_wait_seconds(self) -> int:
        try:
            return max(1, int(getattr(settings, 'RANDOM_VIDEO_REMATCH_FALLBACK_WAIT_SECONDS', 10)))
        except Exception:
            return 10

    def _rematch_cooldown_seconds(self) -> int:
        try:
            return max(1, int(getattr(settings, 'RANDOM_VIDEO_REMATCH_COOLDOWN_SECONDS', 12)))
        except Exception:
            return 12

    def _recent_pair_key(self, user_key_a: str, user_key_b: str) -> str:
        left = str(user_key_a or '').strip()
        right = str(user_key_b or '').strip()
        if left <= right:
            return f"{RECENT_PAIR_KEY_PREFIX}{left}|{right}"
        return f"{RECENT_PAIR_KEY_PREFIX}{right}|{left}"

    def _mark_recent_pair(self, user_key_a: str, user_key_b: str) -> None:
        left = str(user_key_a or '').strip()
        right = str(user_key_b or '').strip()
        if not left or not right or left == right:
            return
        try:
            cache.set(self._recent_pair_key(left, right), 1, timeout=self._rematch_cooldown_seconds())
        except Exception:
            return

    def _is_recent_pair(self, user_key_a: str, user_key_b: str) -> bool:
        left = str(user_key_a or '').strip()
        right = str(user_key_b or '').strip()
        if not left or not right or left == right:
            return False
        try:
            return bool(cache.get(self._recent_pair_key(left, right)))
        except Exception:
            return False

    def _limit(self) -> int:
        try:
            return max(1, int(getattr(settings, 'RANDOM_VIDEO_ACTIVE_USERS_LIMIT', 2000)))
        except Exception:
            return 2000

    def _user_key(self) -> str:
        user = self.scope.get('user')
        try:
            if user and getattr(user, 'is_authenticated', False):
                return f"u:{int(getattr(user, 'id', 0) or 0)}"
        except Exception:
            pass

        session = self.scope.get('session')
        try:
            if session and not session.session_key:
                session.save()
            if session and session.session_key:
                return f"s:{session.session_key}"
        except Exception:
            pass

        return f"g:{uuid.uuid4().hex}"

    def _waiting_key(self, ticket: str) -> str:
        return f"{WAITING_KEY_PREFIX}{ticket}"

    def _pair_key(self, channel_name: str) -> str:
        return f"{PAIR_KEY_PREFIX}{channel_name}"

    def _send_json(self, payload: dict) -> None:
        try:
            self.send(text_data=json.dumps(payload))
        except Exception:
            return

    def connect(self):
        self.user_key = self._user_key()
        self.ticket = None
        self.peer_channel = None
        self.room_id = None
        self._active_incremented = False

        try:
            if cache.add(ACTIVE_USERS_KEY, 0, timeout=None):
                pass
            active = cache.incr(ACTIVE_USERS_KEY)
            self._active_incremented = True
        except Exception:
            active = 1
            self._active_incremented = True

        if int(active or 0) > self._limit():
            self.accept()
            self._send_json({'type': 'rejected', 'reason': 'server_busy'})
            self._decrement_active()
            self.close(code=4003)
            return

        self.accept()
        self._send_json({'type': 'ready'})

    def disconnect(self, close_code):
        try:
            self._remove_from_queue()
        except Exception:
            pass

        try:
            self._break_pair(notify_peer=True)
        except Exception:
            pass

        self._decrement_active()

    def _decrement_active(self):
        if not self._active_incremented:
            return
        self._active_incremented = False
        try:
            current = cache.get(ACTIVE_USERS_KEY)
            current_val = int(current or 0)
            if current_val <= 1:
                cache.set(ACTIVE_USERS_KEY, 0, timeout=None)
            else:
                cache.decr(ACTIVE_USERS_KEY)
        except Exception:
            pass

    def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return

        try:
            payload = json.loads(text_data)
        except Exception:
            return

        action = str(payload.get('action') or '').strip().lower()

        if action == 'start':
            self._enqueue_and_match()
            return

        if action == 'skip':
            self._break_pair(notify_peer=True)
            self._enqueue_and_match()
            return

        if action == 'report':
            self._send_json({'type': 'report_ack'})
            return

        if action == 'signal':
            self._relay_signal(payload)
            return

        if action == 'chat':
            self._relay_chat(payload)
            return

        if action == 'typing':
            self._relay_typing(payload)
            return

        if action == 'warn':
            self._relay_warn(payload)
            return

        if action == 'ping':
            self._send_json({'type': 'pong'})

    def _acquire_lock(self) -> bool:
        try:
            return bool(cache.add(LOCK_KEY, '1', timeout=2))
        except Exception:
            return True

    def _release_lock(self):
        try:
            cache.delete(LOCK_KEY)
        except Exception:
            return

    def _queue_list(self) -> list[str]:
        try:
            value = cache.get(QUEUE_KEY) or []
            if isinstance(value, list):
                return [str(x) for x in value if x]
            return []
        except Exception:
            return []

    def _set_queue_list(self, items: list[str]):
        try:
            cache.set(QUEUE_KEY, items, timeout=3600)
        except Exception:
            return

    def _remove_from_queue(self):
        if not self.ticket:
            return

        try:
            cache.delete(self._waiting_key(self.ticket))
        except Exception:
            pass

        if self._acquire_lock():
            try:
                q = self._queue_list()
                q = [x for x in q if x != self.ticket]
                self._set_queue_list(q)
            finally:
                self._release_lock()

        self.ticket = None

    def _enqueue_and_match(self):
        if self.peer_channel:
            return

        self._remove_from_queue()

        my_ticket = uuid.uuid4().hex
        self.ticket = my_ticket
        waiting_payload = {
            'ticket': my_ticket,
            'channel': self.channel_name,
            'user_key': self.user_key,
            'created_at': _now_ts(),
        }
        cache.set(self._waiting_key(my_ticket), waiting_payload, timeout=45)

        if not self._acquire_lock():
            self._send_json({'type': 'waiting'})
            return

        try:
            q = self._queue_list()
            q = [x for x in q if x and x != my_ticket]
            q.append(my_ticket)

            cleaned = []
            for t in q:
                item = cache.get(self._waiting_key(t))
                if not item:
                    continue
                if int(_now_ts() - int(item.get('created_at') or 0)) > 45:
                    cache.delete(self._waiting_key(t))
                    continue
                cleaned.append(t)

            q = cleaned
            now_ts = _now_ts()

            matched = None
            if len(q) >= 2:
                waiting_map = {}
                for t in q:
                    item = cache.get(self._waiting_key(t))
                    if item:
                        waiting_map[t] = item

                pair_indexes = None
                for i in range(len(q) - 1):
                    first = q[i]
                    a = waiting_map.get(first)
                    if not a:
                        continue
                    a_user_key = str(a.get('user_key') or '')
                    if not a_user_key:
                        continue

                    for j in range(i + 1, len(q)):
                        second = q[j]
                        b = waiting_map.get(second)
                        if not b:
                            continue
                        b_user_key = str(b.get('user_key') or '')
                        if not b_user_key:
                            continue
                        if a_user_key == b_user_key:
                            continue
                        if self._is_recent_pair(a_user_key, b_user_key):
                            continue

                        matched = (a, b)
                        pair_indexes = (i, j)
                        cache.delete(self._waiting_key(first))
                        cache.delete(self._waiting_key(second))
                        break

                    if matched:
                        break

                if pair_indexes:
                    i, j = pair_indexes
                    q = [ticket for idx, ticket in enumerate(q) if idx not in (i, j)]
                elif len(q) == 2:
                    first = q[0]
                    second = q[1]
                    a = waiting_map.get(first)
                    b = waiting_map.get(second)

                    if a and b:
                        a_user_key = str(a.get('user_key') or '')
                        b_user_key = str(b.get('user_key') or '')

                        if (
                            a_user_key
                            and b_user_key
                            and a_user_key != b_user_key
                            and self._is_recent_pair(a_user_key, b_user_key)
                        ):
                            wait_limit = self._rematch_fallback_wait_seconds()
                            a_wait = max(0, int(now_ts - int(a.get('created_at') or now_ts)))
                            b_wait = max(0, int(now_ts - int(b.get('created_at') or now_ts)))

                            if a_wait >= wait_limit and b_wait >= wait_limit:
                                matched = (a, b)
                                q = []
                                cache.delete(self._waiting_key(first))
                                cache.delete(self._waiting_key(second))

            self._set_queue_list(q)
        finally:
            self._release_lock()

        if not matched:
            self._send_json({'type': 'waiting'})
            return

        a, b = matched
        room_id = f"rv-{uuid.uuid4().hex[:12]}"

        a_ch = str(a.get('channel') or '')
        b_ch = str(b.get('channel') or '')

        if not a_ch or not b_ch:
            return

        cache.set(
            self._pair_key(a_ch),
            {
                'peer': b_ch,
                'room': room_id,
                'peer_user_key': str(b.get('user_key') or ''),
            },
            timeout=1800,
        )
        cache.set(
            self._pair_key(b_ch),
            {
                'peer': a_ch,
                'room': room_id,
                'peer_user_key': str(a.get('user_key') or ''),
            },
            timeout=1800,
        )

        async_to_sync(self.channel_layer.send)(
            a_ch,
            {
                'type': 'rv_matched',
                'room': room_id,
                'peer_channel': b_ch,
                'offerer': True,
            },
        )
        async_to_sync(self.channel_layer.send)(
            b_ch,
            {
                'type': 'rv_matched',
                'room': room_id,
                'peer_channel': a_ch,
                'offerer': False,
            },
        )

    def _break_pair(self, notify_peer: bool):
        pair = cache.get(self._pair_key(self.channel_name))
        cache.delete(self._pair_key(self.channel_name))

        self.peer_channel = None
        self.room_id = None

        if not pair:
            return

        peer_channel = str(pair.get('peer') or '')
        peer_user_key = str(pair.get('peer_user_key') or '')

        if peer_user_key and notify_peer:
            self._mark_recent_pair(self.user_key, peer_user_key)

        if not peer_channel:
            return

        cache.delete(self._pair_key(peer_channel))

        if notify_peer:
            try:
                async_to_sync(self.channel_layer.send)(
                    peer_channel,
                    {
                        'type': 'rv_peer_left',
                    },
                )
            except Exception:
                pass

    def _relay_signal(self, payload: dict):
        pair = cache.get(self._pair_key(self.channel_name))
        if not pair:
            return

        peer_channel = str(pair.get('peer') or '')
        if not peer_channel:
            return

        data = payload.get('data') or {}
        try:
            async_to_sync(self.channel_layer.send)(
                peer_channel,
                {
                    'type': 'rv_signal',
                    'data': data,
                },
            )
        except Exception:
            return

    def _relay_chat(self, payload: dict):
        pair = cache.get(self._pair_key(self.channel_name))
        if not pair:
            return

        peer_channel = str(pair.get('peer') or '')
        if not peer_channel:
            return

        message = str(payload.get('message') or '').strip()
        if not message:
            return
        if len(message) > 500:
            message = message[:500]

        try:
            async_to_sync(self.channel_layer.send)(
                peer_channel,
                {
                    'type': 'rv_chat_message',
                    'message': message,
                },
            )
        except Exception:
            return

    def _relay_typing(self, payload: dict):
        pair = cache.get(self._pair_key(self.channel_name))
        if not pair:
            return

        peer_channel = str(pair.get('peer') or '')
        if not peer_channel:
            return

        is_typing = bool(payload.get('typing'))

        try:
            async_to_sync(self.channel_layer.send)(
                peer_channel,
                {
                    'type': 'rv_typing',
                    'typing': is_typing,
                },
            )
        except Exception:
            return

    def _relay_warn(self, payload: dict):
        user = self.scope.get('user')
        if not (user and getattr(user, 'is_authenticated', False) and getattr(user, 'is_superuser', False)):
            self._send_json({'type': 'warn_denied'})
            return

        pair = cache.get(self._pair_key(self.channel_name))
        if not pair:
            self._send_json({'type': 'warn_failed', 'reason': 'not_paired'})
            return

        peer_channel = str(pair.get('peer') or '')
        if not peer_channel:
            self._send_json({'type': 'warn_failed', 'reason': 'peer_missing'})
            return

        message = str(payload.get('message') or '').strip()
        if not message:
            self._send_json({'type': 'warn_failed', 'reason': 'empty'})
            return
        if len(message) > 400:
            message = message[:400]

        try:
            async_to_sync(self.channel_layer.send)(
                peer_channel,
                {
                    'type': 'rv_admin_warning',
                    'message': message,
                    'sender': 'Vixogram',
                },
            )
            self._send_json({'type': 'warn_sent'})
        except Exception:
            self._send_json({'type': 'warn_failed', 'reason': 'send_error'})
            return

    def rv_matched(self, event):
        self.peer_channel = str(event.get('peer_channel') or '')
        self.room_id = str(event.get('room') or '')
        self.ticket = None
        self._send_json({
            'type': 'matched',
            'room': self.room_id,
            'offerer': bool(event.get('offerer')),
        })

    def rv_signal(self, event):
        self._send_json({
            'type': 'signal',
            'data': event.get('data') or {},
        })

    def rv_peer_left(self, event):
        cache.delete(self._pair_key(self.channel_name))
        self.peer_channel = None
        self.room_id = None
        self._send_json({'type': 'peer_left'})

    def rv_chat_message(self, event):
        self._send_json({
            'type': 'chat_message',
            'message': str(event.get('message') or ''),
        })

    def rv_typing(self, event):
        self._send_json({
            'type': 'typing',
            'typing': bool(event.get('typing')),
        })

    def rv_admin_warning(self, event):
        self._send_json({
            'type': 'admin_warning',
            'sender': str(event.get('sender') or 'Vixogram'),
            'message': str(event.get('message') or ''),
        })
