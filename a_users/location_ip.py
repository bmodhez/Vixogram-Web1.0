from __future__ import annotations

import ipaddress
from typing import Any

import requests
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
