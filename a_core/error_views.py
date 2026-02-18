from __future__ import annotations

from typing import Any

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone


def _format_remaining(total_seconds: int) -> str:
    seconds = max(0, int(total_seconds or 0))
    if seconds <= 0:
        return "less than a minute"

    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)

    parts = []
    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")

    if not parts:
        return "less than a minute"
    return ', '.join(parts[:2])


def get_chat_ban_context(request: HttpRequest) -> dict[str, Any] | None:
    user = getattr(request, 'user', None)
    try:
        if not user or not user.is_authenticated:
            return None
        if getattr(user, 'is_staff', False):
            return None
        profile = getattr(user, 'profile', None)
        until = getattr(profile, 'chat_banned_until', None) if profile else None
        if not until:
            return None

        now = timezone.now()
        if until <= now:
            return None

        remaining_seconds = max(0, int((until - now).total_seconds()))
        until_local = timezone.localtime(until)

        return {
            'ban_until_display': until_local.strftime('%d %b %Y, %I:%M %p'),
            'ban_remaining_display': _format_remaining(remaining_seconds),
            'ban_remaining_seconds': remaining_seconds,
        }
    except Exception:
        return None


def render_chat_banned(request: HttpRequest, status: int = 403) -> HttpResponse:
    ctx = get_chat_ban_context(request) or {}
    return render(request, 'chat_banned.html', ctx, status=status)


def csrf_failure(request: HttpRequest, reason: str = "", template_name: str = "403.html") -> HttpResponse:
    # Django calls this view when CSRF verification fails.
    # We intentionally keep the message generic for security reasons.
    return render(request, template_name, status=403)


def handler403(request: HttpRequest, exception: Exception | None = None, template_name: str = "403.html") -> HttpResponse:
    # Used for PermissionDenied and other 403s.
    if get_chat_ban_context(request):
        return render_chat_banned(request, status=403)

    ctx: dict[str, Any] = {}
    return render(request, template_name, ctx, status=403)
