from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.utils import timezone
from django.conf import settings
import datetime
from datetime import timedelta


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


class FounderClubEnforcementMiddleware:
    """Enforce Founder Club daily activity requirement.

    Rule: after Founder Club is granted, the account must be active at least
    N seconds per day (default 1 hour). If they miss any day, revoke and set
    a reapply cooldown.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user is not None and getattr(user, 'is_authenticated', False):
            try:
                profile = getattr(user, 'profile', None)
                if profile and bool(getattr(profile, 'is_founder_club', False)):
                    today = timezone.localdate()
                    last_checked = getattr(profile, 'founder_club_last_checked', None)
                    if last_checked is None:
                        # Initialize and avoid revoking immediately.
                        profile.founder_club_last_checked = today
                        profile.save(update_fields=['founder_club_last_checked'])
                    elif last_checked < today:
                        from a_users.models import DailyUserActivity

                        min_seconds = int(getattr(settings, 'FOUNDER_CLUB_MIN_ACTIVE_SECONDS_PER_DAY', 3600) or 3600)
                        cooldown_days = int(getattr(settings, 'FOUNDER_CLUB_REAPPLY_COOLDOWN_DAYS', 20) or 20)

                        # Check each missed day from (last_checked) up to yesterday.
                        violated = False
                        check_day = last_checked + datetime.timedelta(days=1)
                        # Check completed days only (up to yesterday)
                        yesterday = today - datetime.timedelta(days=1)
                        while check_day <= yesterday:
                            secs = 0
                            try:
                                row = DailyUserActivity.objects.filter(user=user, date=check_day).first()
                                secs = int(getattr(row, 'active_seconds', 0) or 0)
                            except Exception:
                                secs = 0

                            if secs < min_seconds:
                                violated = True
                                break

                            check_day = check_day + datetime.timedelta(days=1)

                        if violated:
                            now = timezone.now()
                            profile.is_founder_club = False
                            profile.founder_club_revoked_at = now
                            profile.founder_club_reapply_available_at = now + datetime.timedelta(days=cooldown_days)
                            profile.founder_club_last_checked = today
                            profile.save(update_fields=[
                                'is_founder_club',
                                'founder_club_revoked_at',
                                'founder_club_reapply_available_at',
                                'founder_club_last_checked',
                            ])
                            try:
                                messages.error(request, 'Founder Club removed due to inactivity (min 1 hour/day).')
                            except Exception:
                                pass
                        else:
                            profile.founder_club_last_checked = today
                            profile.save(update_fields=['founder_club_last_checked'])
            except Exception:
                pass

        return self.get_response(request)


def _describe_user_agent(ua: str) -> str:
    s = (ua or '').strip().lower()
    if not s:
        return ''

    # OS
    if 'iphone' in s or 'ipad' in s or 'ios' in s:
        os_name = 'iOS'
    elif 'android' in s:
        os_name = 'Android'
    elif 'windows' in s:
        os_name = 'Windows'
    elif 'mac os x' in s or 'macintosh' in s:
        os_name = 'macOS'
    elif 'linux' in s:
        os_name = 'Linux'
    else:
        os_name = ''

    # Browser
    # Order matters: Edge contains "chrome"; Chrome contains "safari".
    if 'edg/' in s or 'edge/' in s:
        browser = 'Edge'
    elif 'opr/' in s or 'opera' in s:
        browser = 'Opera'
    elif 'chrome/' in s or 'crios' in s:
        browser = 'Chrome'
    elif 'firefox/' in s or 'fxios' in s:
        browser = 'Firefox'
    elif 'safari/' in s:
        browser = 'Safari'
    else:
        browser = 'Browser'

    if os_name:
        return f'{browser} on {os_name}'
    return browser


def _get_client_ip_best_effort(request) -> str | None:
    try:
        xff = (request.META.get('HTTP_X_FORWARDED_FOR') or '').strip()
        if xff:
            # XFF may be: client, proxy1, proxy2
            return xff.split(',')[0].strip()[:45]
        ip = (request.META.get('REMOTE_ADDR') or '').strip()
        return ip[:45] if ip else None
    except Exception:
        return None


class UserDeviceTrackingMiddleware:
    """Record/update a user's device based on User-Agent.

    Runs after the response to keep request path fast.
    Throttles writes per (user, UA) to avoid DB spam.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        try:
            user = getattr(request, 'user', None)
            if user is None or not getattr(user, 'is_authenticated', False):
                return response

            ua = (request.META.get('HTTP_USER_AGENT') or '').strip()[:300]
            if not ua:
                return response

            from a_users.models import UserDevice

            now = timezone.now()
            throttle_minutes = int(getattr(settings, 'USER_DEVICE_TRACKING_THROTTLE_MINUTES', 10) or 10)
            cutoff = now - timedelta(minutes=max(1, throttle_minutes))

            ua_hash = UserDevice.hash_user_agent(ua)
            row = (
                UserDevice.objects
                .filter(user_id=user.id, ua_hash=ua_hash)
                .only('id', 'last_seen')
                .first()
            )

            if row is not None and getattr(row, 'last_seen', None) and row.last_seen >= cutoff:
                return response

            label = _describe_user_agent(ua)
            ip = _get_client_ip_best_effort(request)

            if row is None:
                UserDevice.objects.create(
                    user_id=user.id,
                    ua_hash=ua_hash,
                    user_agent=ua,
                    device_label=label,
                    last_ip=ip,
                )
            else:
                UserDevice.objects.filter(pk=row.pk).update(
                    user_agent=ua,
                    device_label=label,
                    last_ip=ip,
                    last_seen=now,
                )
        except Exception:
            # Never break the request if tracking fails.
            return response

        return response
