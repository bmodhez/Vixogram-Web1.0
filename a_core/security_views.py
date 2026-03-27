from __future__ import annotations

from django.conf import settings
from django.http import HttpResponse
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from a_rtchat.rate_limit import get_client_ip
from a_users.location_ip import vpn_proxy_status_for_ip


VPN_PROXY_WARNING_MESSAGE = (
    'VPN or proxy connections are not allowed on Vixogram. '
    'Please disable your VPN to continue using all features.'
)
VPN_PROXY_CLIENT_BLOCKED_SESSION_KEY = 'vixo_vpn_proxy_client_blocked'


def robots_txt_view(request):
    admin_path = str(getattr(settings, 'ADMIN_URL', 'admin')).strip().strip('/') or 'admin'
    lines = [
        'User-agent: *',
        'Disallow: /admin/',
        f'Disallow: /{admin_path}/',
    ]
    return HttpResponse('\n'.join(lines) + '\n', content_type='text/plain; charset=utf-8')


def axes_lockout_response(request, credentials=None, *args, **kwargs):
    """Render a styled lockout page for admin brute-force protection."""
    try:
        cooloff_hours = float(getattr(settings, 'AXES_COOLOFF_TIME').total_seconds() / 3600.0)
    except Exception:
        cooloff_hours = 12.0

    context = {
        'cooloff_hours': int(cooloff_hours) if cooloff_hours.is_integer() else cooloff_hours,
        'admin_login_path': str(getattr(settings, 'ADMIN_URL_PREFIX', '/admin/')),
        'retry_path': request.get_full_path() if request else '/',
    }
    return render(request, 'axes/lockout.html', context=context, status=429)


def network_security_status_view(request):
    """Return VPN/proxy detection status for the current request IP."""
    enabled = bool(getattr(settings, 'VPN_PROXY_GUARD_ENABLED', True))
    if not enabled:
        return JsonResponse(
            {
                'ok': True,
                'blocked': False,
                'message': '',
                'check_interval_seconds': int(getattr(settings, 'VPN_PROXY_CHECK_INTERVAL_SECONDS', 5) or 5),
            }
        )

    blocked = False
    try:
        try:
            blocked = bool(getattr(request, 'session', None) and request.session.get(VPN_PROXY_CLIENT_BLOCKED_SESSION_KEY))
        except Exception:
            blocked = False

        ip = get_client_ip(request)
        status = vpn_proxy_status_for_ip(ip)
        blocked = bool(blocked or status.get('blocked'))
    except Exception:
        blocked = False

    return JsonResponse(
        {
            'ok': True,
            'blocked': bool(blocked),
            'message': VPN_PROXY_WARNING_MESSAGE if blocked else '',
            'check_interval_seconds': int(getattr(settings, 'VPN_PROXY_CHECK_INTERVAL_SECONDS', 5) or 5),
        }
    )


@require_POST
def network_security_client_report_view(request):
    """Accept client-side VPN/proxy probe result and persist it in session."""
    try:
        enabled = bool(getattr(settings, 'VPN_PROXY_GUARD_ENABLED', True))
    except Exception:
        enabled = True

    if not enabled:
        try:
            if getattr(request, 'session', None):
                request.session.pop(VPN_PROXY_CLIENT_BLOCKED_SESSION_KEY, None)
        except Exception:
            pass
        return JsonResponse({'ok': True, 'blocked': False})

    blocked = False
    try:
        payload = request.body.decode('utf-8') if request.body else '{}'
    except Exception:
        payload = '{}'
    try:
        import json

        data = json.loads(payload or '{}')
        blocked = bool(data.get('blocked'))
    except Exception:
        blocked = False

    try:
        sess = getattr(request, 'session', None)
        if sess is not None:
            if blocked:
                sess[VPN_PROXY_CLIENT_BLOCKED_SESSION_KEY] = True
            else:
                sess.pop(VPN_PROXY_CLIENT_BLOCKED_SESSION_KEY, None)
    except Exception:
        pass

    return JsonResponse({'ok': True, 'blocked': bool(blocked)})
