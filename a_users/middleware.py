from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect


class ActiveUserRequiredMiddleware:
    """If an authenticated user is inactive, force logout.

    This closes the gap where a user could remain logged in via an existing
    session after staff blocks them (sets is_active=False).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user is not None and getattr(user, 'is_authenticated', False) and not getattr(user, 'is_active', True):
            logout(request)
            try:
                messages.error(request, 'Your account has been disabled.')
            except Exception:
                pass
            return redirect('account_login')
        return self.get_response(request)
