from __future__ import annotations

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from a_rtchat.rate_limit import get_client_ip
from a_users.location_ip import vpn_proxy_status_for_ip


VPN_PROXY_WARNING_MESSAGE = (
    'VPN or proxy connections are not allowed on Vixogram. '
    'Please disable your VPN to continue using all features.'
)
VPN_PROXY_CLIENT_BLOCKED_SESSION_KEY = 'vixo_vpn_proxy_client_blocked'


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
