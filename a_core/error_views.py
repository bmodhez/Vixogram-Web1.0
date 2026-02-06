from __future__ import annotations

from typing import Any

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


def csrf_failure(request: HttpRequest, reason: str = "", template_name: str = "403.html") -> HttpResponse:
    # Django calls this view when CSRF verification fails.
    # We intentionally keep the message generic for security reasons.
    return render(request, template_name, status=403)


def handler403(request: HttpRequest, exception: Exception | None = None, template_name: str = "403.html") -> HttpResponse:
    # Used for PermissionDenied and other 403s.
    ctx: dict[str, Any] = {}
    return render(request, template_name, ctx, status=403)
