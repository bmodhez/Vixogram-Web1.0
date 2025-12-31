from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import hashlib
import unicodedata

from django.core.cache import cache
from django.utils import timezone


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    count: int
    limit: int
    period_seconds: int

    @property
    def retry_after(self) -> int:
        # We don't have a portable TTL from all cache backends, so return the window length.
        return max(1, int(self.period_seconds))


def mute_key(user_id: int | str) -> str:
    return make_key('mute', user_id)


def strikes_key(scope: str, user_id: int | str, room: str | None = None) -> str:
    return make_key('strikes', scope, user_id, room)


def get_muted_seconds(user_id: int | str) -> int:
    """Return remaining mute seconds for a user (0 if not muted)."""
    try:
        raw = cache.get(mute_key(user_id))
    except Exception:
        raw = None
    if not raw:
        return 0
    try:
        muted_until = float(raw)
    except Exception:
        return 0
    now = timezone.now().timestamp()
    remaining = int(muted_until - now)
    return max(0, remaining)


def set_muted(user_id: int | str, seconds: int) -> int:
    seconds = int(seconds)
    seconds = max(1, seconds)
    muted_until = timezone.now().timestamp() + seconds
    try:
        cache.set(mute_key(user_id), str(muted_until), timeout=seconds)
    except Exception:
        pass
    return seconds


def record_abuse_violation(
    *,
    scope: str,
    user_id: int | str,
    room: str | None,
    window_seconds: int,
    threshold: int,
    mute_seconds: int,
    weight: int = 1,
) -> tuple[int, int]:
    """Record an abuse strike and auto-mute once threshold is reached.

    Returns: (strikes_count, muted_seconds_remaining)
    """
    window_seconds = max(1, int(window_seconds))
    threshold = max(1, int(threshold))
    mute_seconds = max(1, int(mute_seconds))
    weight = max(1, int(weight))

    key = strikes_key(scope, user_id, room)
    strikes = 0
    for _ in range(weight):
        strikes = _increment_counter(key, period_seconds=window_seconds)

    remaining = get_muted_seconds(user_id)
    if remaining > 0:
        return strikes, remaining

    if strikes >= threshold:
        set_muted(user_id, mute_seconds)
        return strikes, mute_seconds

    return strikes, 0


def _msg_fingerprint(text: str) -> str:
    normalized = (text or '').strip().lower()
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


def duplicate_key(room: str, user_id: int | str) -> str:
    return make_key('dup', room, user_id)


def is_duplicate_message(room: str, user_id: int | str, text: str, ttl_seconds: int) -> tuple[bool, int]:
    """Detect repeated identical messages by the same user in the same room.

    Returns: (is_duplicate, retry_after_seconds)
    """
    ttl_seconds = max(1, int(ttl_seconds))
    fp = _msg_fingerprint(text)
    key = duplicate_key(room, user_id)

    try:
        prev = cache.get(key)
    except Exception:
        prev = None

    if prev == fp:
        return True, ttl_seconds

    try:
        cache.set(key, fp, timeout=ttl_seconds)
    except Exception:
        pass

    return False, 0


def _strip_emoji_joiners(text: str) -> str:
    # Remove variation selectors and zero-width joiner commonly used in emoji sequences.
    return (
        (text or '')
        .replace('\uFE0F', '')
        .replace('\uFE0E', '')
        .replace('\u200D', '')
    )


def is_same_emoji_spam(text: str, *, min_repeats: int = 4, ttl_seconds: int = 15) -> tuple[bool, int]:
    """Detect same-emoji spam like 🤡🤡🤡🤡 (best-effort heuristic).

    Returns: (is_spam, retry_after_seconds)
    """
    ttl_seconds = max(1, int(ttl_seconds))
    min_repeats = max(2, int(min_repeats))

    raw = _strip_emoji_joiners((text or '').strip())
    if not raw:
        return False, 0

    # Remove spaces/newlines for analysis.
    compact = ''.join(ch for ch in raw if not ch.isspace())
    if len(compact) < min_repeats:
        return False, 0

    # If there are alphanumerics, treat as non-emoji spam.
    if any(ch.isalnum() for ch in compact):
        return False, 0

    # Count emoji-ish characters (Symbol, Other) and check uniqueness.
    emojiish = []
    for ch in compact:
        cat = unicodedata.category(ch)
        if cat == 'So':
            emojiish.append(ch)
        else:
            # Allow common punctuation to be present only minimally.
            pass

    if not emojiish:
        return False, 0

    # Require most characters to be emoji-ish and mostly the same symbol.
    ratio = len(emojiish) / max(1, len(compact))
    unique = set(emojiish)
    if ratio >= 0.8 and len(unique) <= 2 and len(emojiish) >= min_repeats:
        # If two unique emojis, still consider spam when one dominates.
        if len(unique) == 1:
            return True, ttl_seconds
        # 2 unique: if one repeats heavily.
        counts = {u: emojiish.count(u) for u in unique}
        if max(counts.values()) >= min_repeats:
            return True, ttl_seconds

    return False, 0


def last_message_key(room: str, user_id: int | str) -> str:
    return make_key('last_msg', room, user_id)


def is_fast_long_message(
    room: str,
    user_id: int | str,
    *,
    message_length: int,
    long_length_threshold: int = 80,
    min_interval_seconds: int = 1,
) -> tuple[bool, int]:
    """Detect copy/paste or bot-like rapid long messages.

    Returns: (is_suspicious, retry_after_seconds)
    """
    long_length_threshold = max(1, int(long_length_threshold))
    min_interval_seconds = max(1, int(min_interval_seconds))
    message_length = int(message_length)

    now = timezone.now().timestamp()
    key = last_message_key(room, user_id)
    try:
        prev = cache.get(key)
    except Exception:
        prev = None

    try:
        cache.set(key, str(now), timeout=60 * 60)
    except Exception:
        pass

    if message_length < long_length_threshold:
        return False, 0

    try:
        prev_ts = float(prev)
    except Exception:
        prev_ts = None

    if prev_ts is None:
        return False, 0

    delta = now - prev_ts
    if delta < float(min_interval_seconds):
        return True, min_interval_seconds

    return False, 0


def _normalize_part(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def make_key(prefix: str, *parts: Any) -> str:
    safe_parts = [p for p in (_normalize_part(x) for x in parts) if p]
    joined = ":".join(safe_parts)
    return f"rl:{prefix}:{joined}" if joined else f"rl:{prefix}"


def _increment_counter(key: str, period_seconds: int) -> int:
    try:
        cache.add(key, 0, timeout=period_seconds)
    except Exception:
        pass

    try:
        return int(cache.incr(key))
    except ValueError:
        # Some backends raise if the key doesn't exist.
        cache.set(key, 1, timeout=period_seconds)
        return 1
    except Exception:
        # Fallback for backends without atomic incr.
        current = int(cache.get(key, 0) or 0) + 1
        cache.set(key, current, timeout=period_seconds)
        return current


def check_rate_limit(key: str, limit: int, period_seconds: int) -> RateLimitResult:
    limit = int(limit)
    period_seconds = int(period_seconds)
    if limit <= 0 or period_seconds <= 0:
        return RateLimitResult(allowed=True, count=0, limit=max(0, limit), period_seconds=max(1, period_seconds))

    count = _increment_counter(key, period_seconds=period_seconds)
    allowed = count <= limit
    return RateLimitResult(allowed=allowed, count=count, limit=limit, period_seconds=period_seconds)


def get_client_ip(request) -> str:
    # Honor X-Forwarded-For (first hop) when behind a proxy.
    xff = (request.META.get('HTTP_X_FORWARDED_FOR') or '').strip()
    if xff:
        return xff.split(',')[0].strip()
    return (request.META.get('REMOTE_ADDR') or '').strip()


def get_client_ip_from_scope(scope) -> str:
    # Channels scope client tuple: (ip, port)
    try:
        client = scope.get('client')
        if client and client[0]:
            return str(client[0])
    except Exception:
        pass

    # Try X-Forwarded-For header if present.
    try:
        headers = dict(scope.get('headers') or [])
        xff = headers.get(b'x-forwarded-for', b'').decode('latin1').strip()
        if xff:
            return xff.split(',')[0].strip()
    except Exception:
        pass

    return ""
