from __future__ import annotations

import ipaddress
from typing import Any

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone


def _is_public_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address((ip or '').strip())
        return not (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_multicast
            or addr.is_reserved
            or addr.is_unspecified
        )
    except Exception:
        return False


def _safe_str(v: Any, max_len: int = 80) -> str:
    try:
        s = str(v or '').strip()
    except Exception:
        return ''
    if not s:
        return ''
    return s[:max_len]


def _as_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    s = _safe_str(v, 16).lower()
    return s in {'1', 'true', 't', 'yes', 'y', 'on'}


def geoip_city_country(ip: str) -> tuple[str, str]:
    """Best-effort IP -> (city, country).

    Uses ipwho.is (no API key). Returns empty strings on failure.
    Results are cached by IP for 24h.

    Privacy: caller should NOT persist the IP address.
    """
    ip = (ip or '').strip()
    if not ip or not _is_public_ip(ip):
        return ('', '')

    cache_key = f"vixo:geoip:{ip}"
    try:
        cached = cache.get(cache_key)
        if isinstance(cached, dict):
            city = _safe_str(cached.get('city'))
            country = _safe_str(cached.get('country'))
            if city or country:
                return (city, country)
    except Exception:
        pass

    try:
        resp = requests.get(f"https://ipwho.is/{ip}", timeout=3)
        if resp.status_code != 200:
            return ('', '')
        data = resp.json() if resp.content else {}
        if not isinstance(data, dict) or data.get('success') is not True:
            return ('', '')

        city = _safe_str(data.get('city'))
        country = _safe_str(data.get('country'))
        if not city:
            # fallback to region if city is unavailable
            city = _safe_str(data.get('region'))

        try:
            cache.set(cache_key, {'city': city, 'country': country}, 24 * 3600)
        except Exception:
            pass

        return (city, country)
    except Exception:
        return ('', '')


def vpn_proxy_status_for_ip(ip: str) -> dict[str, Any]:
    """Best-effort VPN/proxy detection for an IP.

    Returns a normalized payload:
      {
        'blocked': bool,
        'vpn': bool,
        'proxy': bool,
        'tor': bool,
        'relay': bool,
        'hosting': bool,
        'reason': str,
      }

    Notes:
    - Uses ipwho.is (no API key).
    - Caches by IP for a short time to avoid repeated upstream calls.
    - Private/loopback IPs are treated as not blocked.
    """
    ip = (ip or '').strip()
    base = {
        'blocked': False,
        'vpn': False,
        'proxy': False,
        'tor': False,
        'relay': False,
        'hosting': False,
        'reason': '',
    }
    if not ip or not _is_public_ip(ip):
        return dict(base)

    try:
        ttl = int(getattr(settings, 'VPN_PROXY_STATUS_CACHE_SECONDS', 120) or 120)
    except Exception:
        ttl = 120
    ttl = max(30, ttl)

    cache_key = f"vixo:netsec:{ip}"
    try:
        cached = cache.get(cache_key)
        if isinstance(cached, dict) and 'blocked' in cached:
            return {
                'blocked': bool(cached.get('blocked')),
                'vpn': bool(cached.get('vpn')),
                'proxy': bool(cached.get('proxy')),
                'tor': bool(cached.get('tor')),
                'relay': bool(cached.get('relay')),
                'hosting': bool(cached.get('hosting')),
                'reason': _safe_str(cached.get('reason'), 40),
            }
    except Exception:
        pass

    out = dict(base)
    try:
        resp = requests.get(f"https://ipwho.is/{ip}", timeout=3)
        if resp.status_code != 200:
            return out
        data = resp.json() if resp.content else {}
        if not isinstance(data, dict) or data.get('success') is not True:
            return out

        security = data.get('security') if isinstance(data.get('security'), dict) else {}
        connection = data.get('connection') if isinstance(data.get('connection'), dict) else {}

        vpn = _as_bool(security.get('vpn')) or _as_bool(data.get('vpn'))
        proxy = _as_bool(security.get('proxy')) or _as_bool(data.get('proxy'))
        tor = _as_bool(security.get('tor')) or _as_bool(data.get('tor'))
        relay = _as_bool(security.get('relay')) or _as_bool(security.get('is_relay'))

        conn_type = _safe_str(connection.get('type'), 24).lower()
        isp = _safe_str(connection.get('isp'), 80).lower()
        org = _safe_str(connection.get('org'), 80).lower()

        # Best-effort vendor/transport heuristic for providers not explicitly tagged
        # by upstream security booleans (e.g., some WARP exits).
        combined = f"{conn_type} {isp} {org}".strip()
        vpn_hints = (
            'warp',
            'vpn',
            'wireguard',
            'openvpn',
            'tunnelbear',
            'nordvpn',
            'expressvpn',
            'surfshark',
            'protonvpn',
            'mullvad',
            'private internet access',
            'pia',
        )
        hinted_vpn = any(h in combined for h in vpn_hints)
        if hinted_vpn and not (vpn or proxy or tor or relay):
            vpn = True

        hosting = bool(
            security.get('hosting')
            or security.get('datacenter')
            or ('hosting' in conn_type)
            or ('data center' in conn_type)
            or ('datacenter' in conn_type)
            or ('cloud' in isp)
        )

        reason = ''
        if vpn:
            reason = 'vpn'
        elif proxy:
            reason = 'proxy'
        elif tor:
            reason = 'tor'
        elif relay:
            reason = 'relay'
        elif hosting:
            reason = 'hosting'

        out = {
            'blocked': bool(vpn or proxy or tor or relay),
            'vpn': bool(vpn),
            'proxy': bool(proxy),
            'tor': bool(tor),
            'relay': bool(relay),
            'hosting': bool(hosting),
            'reason': reason,
        }
    except Exception:
        out = dict(base)

    try:
        cache.set(cache_key, out, timeout=ttl)
    except Exception:
        pass
    return out


def _extract_ip_from_headers(headers: list[tuple[bytes, bytes]] | None) -> str:
    """Extract client IP from ASGI/Channels headers (best-effort)."""
    if not headers:
        return ''
    try:
        for k, v in headers:
            if k.lower() == b'x-forwarded-for':
                raw = (v.decode('utf-8', errors='ignore') or '').strip()
                # first IP in XFF is original client
                first = (raw.split(',')[0] if raw else '').strip()
                return first
    except Exception:
        return ''
    return ''


def _extract_ip_from_request(request) -> str:
    """Extract client IP from a Django request (best-effort)."""
    try:
        meta = getattr(request, 'META', {}) or {}
        xff = (meta.get('HTTP_X_FORWARDED_FOR') or '').strip()
        if xff:
            return (xff.split(',')[0] or '').strip()
        return (meta.get('REMOTE_ADDR') or '').strip()
    except Exception:
        return ''


def maybe_set_profile_city_from_ip(*, user, request=None, scope=None) -> None:
    """Populate Profile.last_location_city/country once, from IP.

    Intended trigger: first message send.

    Rules:
    - Never overwrites an existing city.
    - Only runs if profile has never recorded a location.
    """
    try:
        if not user or not getattr(user, 'is_authenticated', False):
            return
        if getattr(user, 'is_staff', False):
            return
        profile = user.profile
        if getattr(profile, 'last_location_at', None):
            return
        if (getattr(profile, 'last_location_city', '') or '').strip():
            return

        ip = ''
        if scope is not None:
            try:
                ip = _extract_ip_from_headers(scope.get('headers'))
            except Exception:
                ip = ''
            if not ip:
                try:
                    client = scope.get('client')
                    if client and isinstance(client, (list, tuple)) and client[0]:
                        ip = str(client[0]).strip()
                except Exception:
                    ip = ''
        if not ip and request is not None:
            ip = _extract_ip_from_request(request)

        city, country = geoip_city_country(ip)
        if not (city or country):
            return

        profile.last_location_city = city or None
        profile.last_location_country = country or None
        profile.last_location_at = timezone.now()
        profile.save(update_fields=['last_location_city', 'last_location_country', 'last_location_at'])
    except Exception:
        return
