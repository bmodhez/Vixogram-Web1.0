from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any

import requests
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache

from .channels_utils import chatroom_channel_group_name
from .models import ChatGroup, GroupMessage


logger = logging.getLogger(__name__)

IPL_SCORE_GLOBAL_GROUP = 'ipl_live_scores'
IPL_CACHE_KEY_STATE = 'ipl:live:state:v1'
IPL_CACHE_KEY_HASH = 'ipl:live:hash:v1'
IPL_CACHE_KEY_LAST_BROADCAST = 'ipl:live:last_broadcast:v1'


@dataclass
class IplCycleResult:
    live: bool
    changed: bool
    broadcasted: bool
    reason: str = ''


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _pick(*values: Any) -> str:
    for val in values:
        text = str(val or '').strip()
        if text:
            return text
    return ''


def _format_innings(innings: dict[str, Any] | None) -> str:
    if not innings:
        return ''
    runs = _to_int(innings.get('runs'))
    wickets = _to_int(innings.get('wickets'))
    overs = _pick(innings.get('overs'))
    if overs:
        return f"{runs}/{wickets} ({overs})"
    return f"{runs}/{wickets}"


def _is_live_status(match_info: dict[str, Any]) -> bool:
    state = _pick(match_info.get('state'), match_info.get('status')).lower()
    if not state:
        return False
    return any(token in state for token in ('live', 'in progress', 'innings break', 'stumps'))


def _extract_innings_score(team_score: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(team_score, dict):
        return None

    for key in ('inngs1', 'innings1', 'inns1'):
        if isinstance(team_score.get(key), dict):
            return team_score.get(key)
    for key in ('inngs2', 'innings2', 'inns2'):
        if isinstance(team_score.get(key), dict):
            return team_score.get(key)
    return None


def _iter_match_nodes(payload: Any):
    if isinstance(payload, dict):
        if isinstance(payload.get('matchInfo'), dict):
            yield payload

        for key in ('typeMatches', 'matches', 'matchList', 'data'):
            raw = payload.get(key)
            if isinstance(raw, list):
                for item in raw:
                    yield from _iter_match_nodes(item)

        for key in ('seriesMatches',):
            raw = payload.get(key)
            if isinstance(raw, list):
                for item in raw:
                    if isinstance(item, dict) and isinstance(item.get('seriesAdWrapper'), dict):
                        yield from _iter_match_nodes(item['seriesAdWrapper'])
                    else:
                        yield from _iter_match_nodes(item)

    elif isinstance(payload, list):
        for item in payload:
            yield from _iter_match_nodes(item)


def _normalize_match_node(node: dict[str, Any]) -> dict[str, Any] | None:
    match_info = node.get('matchInfo') or {}
    if not isinstance(match_info, dict):
        return None

    if not _is_live_status(match_info):
        return None

    team1 = match_info.get('team1') or {}
    team2 = match_info.get('team2') or {}
    score_root = node.get('matchScore') or {}

    team1_score = _extract_innings_score(score_root.get('team1Score'))
    team2_score = _extract_innings_score(score_root.get('team2Score'))

    team1_short = _pick(team1.get('teamSName'), team1.get('teamName'), 'TEAM 1')
    team2_short = _pick(team2.get('teamSName'), team2.get('teamName'), 'TEAM 2')
    team1_name = _pick(team1.get('teamName'), team1_short)
    team2_name = _pick(team2.get('teamName'), team2_short)

    team1_score_text = _format_innings(team1_score)
    team2_score_text = _format_innings(team2_score)

    status_text = _pick(match_info.get('status'), match_info.get('stateTitle'), match_info.get('state'), 'LIVE')
    match_id = _pick(match_info.get('matchId'), match_info.get('id'))

    snapshot = {
        'is_live': True,
        'provider': 'cricbuzz-rapidapi',
        'match_id': match_id,
        'team1_short': team1_short,
        'team2_short': team2_short,
        'team1_name': team1_name,
        'team2_name': team2_name,
        'team1_score': team1_score_text,
        'team2_score': team2_score_text,
        'status': status_text,
        'team1_logo': '',
        'team2_logo': '',
    }
    snapshot['compact'] = (
        f"{snapshot['team1_score']} vs {snapshot['team2_score']}"
        if (snapshot['team1_score'] and snapshot['team2_score'])
        else _pick(snapshot['team1_score'], snapshot['team2_score'], status_text)
    )
    snapshot['headline'] = f"{team1_short} {snapshot['team1_score']} vs {team2_short} {snapshot['team2_score']}"
    return snapshot


def _state_hash(snapshot: dict[str, Any]) -> str:
    relevant = {
        'match_id': snapshot.get('match_id'),
        'team1': snapshot.get('team1_short'),
        'team2': snapshot.get('team2_short'),
        's1': snapshot.get('team1_score'),
        's2': snapshot.get('team2_score'),
        'status': snapshot.get('status'),
    }
    payload = json.dumps(relevant, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def _api_headers() -> dict[str, str]:
    headers = {
        'x-rapidapi-host': str(getattr(settings, 'IPL_RAPIDAPI_HOST', '') or '').strip(),
        'x-rapidapi-key': str(getattr(settings, 'IPL_RAPIDAPI_KEY', '') or '').strip(),
    }
    return {k: v for k, v in headers.items() if v}


def _fetch_live_snapshot_from_api() -> dict[str, Any] | None:
    url = str(getattr(settings, 'IPL_CRICBUZZ_LIVE_URL', '') or '').strip()
    headers = _api_headers()
    if not url or not headers.get('x-rapidapi-key') or not headers.get('x-rapidapi-host'):
        return None

    timeout = float(getattr(settings, 'IPL_RAPIDAPI_TIMEOUT_SECONDS', 8.0) or 8.0)
    resp = requests.get(url, headers=headers, timeout=timeout)
    if resp.status_code >= 400:
        raise RuntimeError(f"RapidAPI error: HTTP {resp.status_code}")

    data = resp.json()
    for node in _iter_match_nodes(data):
        normalized = _normalize_match_node(node)
        if normalized:
            return normalized
    return None


def get_cached_ipl_state() -> dict[str, Any] | None:
    cached = cache.get(IPL_CACHE_KEY_STATE)
    if isinstance(cached, dict):
        return cached
    return None


def _broadcast_global_score(snapshot: dict[str, Any]) -> bool:
    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            IPL_SCORE_GLOBAL_GROUP,
            {
                'type': 'ipl_score_handler',
                'score': snapshot,
            },
        )
        return True
    except Exception:
        logger.exception('Failed to broadcast IPL score globally')
        return False


def _persist_public_admin_message(snapshot: dict[str, Any]) -> None:
    room_name = str(getattr(settings, 'IPL_LIVE_SCORE_CHAT_ROOM', 'public-chat') or 'public-chat').strip()
    if not room_name:
        return

    room = None
    try:
        if room_name == 'public-chat':
            room, _ = ChatGroup.objects.get_or_create(group_name='public-chat')
        else:
            room = ChatGroup.objects.filter(group_name=room_name).first()
        if not room:
            return
    except Exception:
        return

    user_model = get_user_model()
    admin_user = (
        user_model.objects.filter(is_superuser=True).order_by('id').first()
        or user_model.objects.filter(is_staff=True).order_by('id').first()
    )
    if not admin_user:
        return

    headline = str(snapshot.get('headline') or '').strip()
    status = str(snapshot.get('status') or '').strip()
    body = f"🏏 IPL Live: {headline} • {status}"[:290]
    try:
        msg = GroupMessage.objects.create(
            author=admin_user,
            group=room,
            body=body,
        )
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            chatroom_channel_group_name(room),
            {
                'type': 'message_handler',
                'message_id': int(msg.id),
                'author_id': int(getattr(admin_user, 'id', 0) or 0),
            },
        )
    except Exception:
        logger.exception('Failed to persist/broadcast IPL admin message')


def run_ipl_live_cycle() -> IplCycleResult:
    try:
        snapshot = _fetch_live_snapshot_from_api()
    except Exception as exc:
        logger.warning('IPL fetch failed: %s', exc)
        return IplCycleResult(live=False, changed=False, broadcasted=False, reason='api_error')

    ttl = int(getattr(settings, 'IPL_SCORE_CACHE_TTL_SECONDS', 60 * 60 * 6) or (60 * 60 * 6))

    if not snapshot:
        cache.delete(IPL_CACHE_KEY_STATE)
        cache.delete(IPL_CACHE_KEY_HASH)
        return IplCycleResult(live=False, changed=False, broadcasted=False, reason='not_live')

    current_hash = _state_hash(snapshot)
    previous_hash = str(cache.get(IPL_CACHE_KEY_HASH) or '').strip()
    changed = current_hash != previous_hash

    cache.set(IPL_CACHE_KEY_STATE, snapshot, ttl)
    cache.set(IPL_CACHE_KEY_HASH, current_hash, ttl)

    if not changed:
        return IplCycleResult(live=True, changed=False, broadcasted=False, reason='unchanged')

    broadcasted = _broadcast_global_score(snapshot)
    if broadcasted:
        cache.set(IPL_CACHE_KEY_LAST_BROADCAST, snapshot, ttl)

    _persist_public_admin_message(snapshot)
    return IplCycleResult(live=True, changed=True, broadcasted=broadcasted, reason='updated')
