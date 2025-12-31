from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import requests
from django.conf import settings


@dataclass(frozen=True)
class ModerationDecision:
    action: str  # allow | flag | block
    categories: list[str]
    severity: int  # 0-3
    confidence: float  # 0-1
    reason: str
    suggested_mute_seconds: int
    raw: dict[str, Any]


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _clamp_int(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(value)))


def _clamp_float(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _default_decision() -> ModerationDecision:
    return ModerationDecision(
        action='allow',
        categories=[],
        severity=0,
        confidence=0.0,
        reason='',
        suggested_mute_seconds=0,
        raw={},
    )


def _gemini_url(model: str, api_key: str) -> str:
    # Google AI Studio / Generative Language API
    return f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"


def _build_prompt(payload: dict[str, Any]) -> str:
    return (
        "You are a strict chat moderation classifier for a real-time chat app. "
        "Return ONLY valid minified JSON with no extra text.\n\n"
        "Goal: detect abusive language (insults/personal attacks), hate speech (religion/caste/gender/race), "
        "sexual/NSFW, harassment vs jokes (context-aware), spam, and bot-like behavior.\n\n"
        "Rules:\n"
        "- action must be one of: allow, flag, block\n"
        "- categories must be a list of strings from: abusive, hate, sexual, harassment, spam, bot, self_harm, other\n"
        "- severity must be integer 0-3 (0=clean, 1=borderline, 2=bad, 3=severe)\n"
        "- confidence must be 0-1\n"
        "- reason must be a short explanation WITHOUT quoting slurs or explicit content\n"
        "- suggested_mute_seconds integer 0-3600\n"
        "- Prefer allow unless clearly harmful. Prefer flag for ambiguous. Block for severe/clear hate/sexual/harassment threats.\n\n"
        "JSON schema:\n"
        "{\"action\":\"allow|flag|block\",\"categories\":[...],\"severity\":0,\"confidence\":0.0,\"reason\":\"...\",\"suggested_mute_seconds\":0}\n\n"
        f"Input:\n{json.dumps(payload, ensure_ascii=False)}\n"
    )


def moderate_message(*, text: str, context: dict[str, Any] | None = None) -> ModerationDecision:
    api_key = (getattr(settings, 'GEMINI_API_KEY', '') or '').strip()
    if not api_key:
        return _default_decision()

    model = (getattr(settings, 'GEMINI_MODEL', '') or 'gemini-1.5-flash').strip()
    timeout = float(getattr(settings, 'GEMINI_TIMEOUT_SECONDS', 4.0))

    payload = {
        'text': (text or '')[:2000],
        'context': context or {},
    }

    req = {
        'contents': [
            {
                'role': 'user',
                'parts': [{'text': _build_prompt(payload)}],
            }
        ],
        'generationConfig': {
            'temperature': 0.0,
            'maxOutputTokens': 256,
        },
    }

    try:
        resp = requests.post(
            _gemini_url(model, api_key),
            json=req,
            timeout=timeout,
        )
    except Exception:
        return _default_decision()

    if resp.status_code != 200:
        return _default_decision()

    try:
        data = resp.json()
    except Exception:
        return _default_decision()

    # Extract text from candidates
    try:
        text_out = (
            data.get('candidates', [{}])[0]
            .get('content', {})
            .get('parts', [{}])[0]
            .get('text', '')
        )
    except Exception:
        text_out = ''

    if not text_out:
        return _default_decision()

    # Some models may wrap JSON in code fences; strip best-effort.
    cleaned = text_out.strip()
    if cleaned.startswith('```'):
        cleaned = cleaned.strip('`').strip()
        if cleaned.lower().startswith('json'):
            cleaned = cleaned[4:].strip()

    try:
        verdict = json.loads(cleaned)
    except Exception:
        return _default_decision()

    action = str(verdict.get('action', 'allow')).strip().lower()
    if action not in {'allow', 'flag', 'block'}:
        action = 'allow'

    categories_raw = verdict.get('categories', [])
    if not isinstance(categories_raw, list):
        categories_raw = []
    categories = [str(c).strip().lower() for c in categories_raw if str(c).strip()]

    severity = _clamp_int(_safe_int(verdict.get('severity', 0)), 0, 3)
    confidence = _clamp_float(_safe_float(verdict.get('confidence', 0.0)), 0.0, 1.0)
    reason = str(verdict.get('reason', '') or '').strip()[:240]
    suggested_mute_seconds = _clamp_int(_safe_int(verdict.get('suggested_mute_seconds', 0)), 0, 3600)

    return ModerationDecision(
        action=action,
        categories=categories,
        severity=severity,
        confidence=confidence,
        reason=reason,
        suggested_mute_seconds=suggested_mute_seconds,
        raw=verdict if isinstance(verdict, dict) else {},
    )
