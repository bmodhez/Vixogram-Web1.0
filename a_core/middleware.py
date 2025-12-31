from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect

from a_rtchat.rate_limit import check_rate_limit, get_client_ip, make_key


class RateLimitMiddleware:
    """Simple cache-based rate limiting for auth endpoints.

    This protects login/signup/password reset from brute-force and spam.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == 'POST':
            path = (request.path or '')
            watched = (
                '/accounts/login/',
                '/accounts/signup/',
                '/accounts/password/reset/',
                '/accounts/password/reset/key/',
            )
            if any(path.startswith(p) for p in watched):
                ip = get_client_ip(request)
                limit = int(getattr(settings, 'AUTH_RATE_LIMIT', 25))
                period = int(getattr(settings, 'AUTH_RATE_LIMIT_PERIOD', 300))

                key = make_key('auth', path, ip)
                result = check_rate_limit(key, limit=limit, period_seconds=period)
                if not result.allowed:
                    # HTMX callers get a plain 429.
                    if (request.headers.get('HX-Request') or '').lower() == 'true':
                        resp = HttpResponse('Too many attempts. Please try again.', status=429)
                        resp.headers['Retry-After'] = str(result.retry_after)
                        return resp

                    try:
                        messages.error(request, 'Too many attempts. Please wait and try again.')
                    except Exception:
                        pass
                    return redirect(path)

        return self.get_response(request)
