import json

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache


def firebase_config(request):
    """Expose Firebase public config to templates when enabled."""
    enabled = bool(getattr(settings, 'FIREBASE_ENABLED', False))
    cfg = {
        'apiKey': getattr(settings, 'FIREBASE_API_KEY', ''),
        'authDomain': getattr(settings, 'FIREBASE_AUTH_DOMAIN', ''),
        'projectId': getattr(settings, 'FIREBASE_PROJECT_ID', ''),
        'storageBucket': getattr(settings, 'FIREBASE_STORAGE_BUCKET', ''),
        'messagingSenderId': getattr(settings, 'FIREBASE_MESSAGING_SENDER_ID', ''),
        'appId': getattr(settings, 'FIREBASE_APP_ID', ''),
        'measurementId': getattr(settings, 'FIREBASE_MEASUREMENT_ID', ''),
    }

    # Only expose when all required public fields are present.
    required = ['apiKey', 'authDomain', 'projectId', 'messagingSenderId', 'appId']
    ready = enabled and all((cfg.get(k) or '').strip() for k in required)

    return {
        'FIREBASE_ENABLED': bool(ready),
        'FIREBASE_CONFIG_JSON': json.dumps(cfg if ready else {}),
        'FIREBASE_VAPID_PUBLIC_KEY': getattr(settings, 'FIREBASE_VAPID_PUBLIC_KEY', '') if ready else '',
    }


def site_contact(request):
    """Expose basic site contact info to templates."""
    return {
        'CONTACT_EMAIL': (getattr(settings, 'CONTACT_EMAIL', '') or '').strip(),
        'CONTACT_INSTAGRAM_URL': (getattr(settings, 'CONTACT_INSTAGRAM_URL', '') or '').strip(),
    }


def recaptcha_config(request):
    """Expose public reCAPTCHA config to templates."""
    enabled = bool(getattr(settings, 'RECAPTCHA_ENABLED', False))
    site_key = (getattr(settings, 'RECAPTCHA_SITE_KEY', '') or '').strip()
    version = (getattr(settings, 'RECAPTCHA_VERSION', 'v2') or 'v2').strip().lower()
    provider = (getattr(settings, 'RECAPTCHA_PROVIDER', 'standard') or 'standard').strip().lower()
    script_url = (getattr(settings, 'RECAPTCHA_SCRIPT_URL', '') or '').strip()
    action = (getattr(settings, 'RECAPTCHA_ACTION', 'signup') or 'signup').strip() or 'signup'
    if not site_key:
        enabled = False
    return {
        'RECAPTCHA_ENABLED': bool(enabled),
        'RECAPTCHA_SITE_KEY': site_key,
        'RECAPTCHA_VERSION': version,
        'RECAPTCHA_PROVIDER': provider,
        'RECAPTCHA_SCRIPT_URL': script_url,
        'RECAPTCHA_ACTION': action,
        # Helpful dev hint: most Google reCAPTCHA site keys start with "6L".
        'RECAPTCHA_SITE_KEY_LOOKS_VALID': bool(site_key.startswith('6L')),
        'RECAPTCHA_DEBUG': bool(getattr(settings, 'DEBUG', False)),
    }


def welcome_popup(request):
    """Expose a one-time welcome popup flag.

    Reads request.session['show_welcome_popup'] and clears it after consumption
    so the popup displays only once after login/signup.
    """
    try:
        sess = getattr(request, 'session', None)
        if not sess:
            return {'SHOW_WELCOME_POPUP': False, 'WELCOME_POPUP_SOURCE': ''}

        show = bool(sess.get('show_welcome_popup'))
        source = (sess.get('welcome_popup_source') or '').strip()
        if show:
            sess.pop('show_welcome_popup', None)
            sess.pop('welcome_popup_source', None)
        return {'SHOW_WELCOME_POPUP': show, 'WELCOME_POPUP_SOURCE': source if show else ''}
    except Exception:
        return {'SHOW_WELCOME_POPUP': False, 'WELCOME_POPUP_SOURCE': ''}


def location_popup(request):
    """Expose a one-time location permission popup flag.

    Shown once after signup/login when the session flag is present.
    Reads request.session['show_location_popup'] and clears it after consumption.
    """
    try:
        # Never show this prompt inside the Django admin.
        try:
            if str(getattr(request, 'path', '') or '').startswith('/admin'):
                return {'SHOW_LOCATION_POPUP': False}
        except Exception:
            pass

        sess = getattr(request, 'session', None)
        if not sess:
            return {'SHOW_LOCATION_POPUP': False}

        show = bool(sess.get('show_location_popup'))
        if show:
            # Ensure CSRF cookie exists for the JS fetch() POST.
            try:
                from django.middleware.csrf import get_token

                get_token(request)
            except Exception:
                pass
            sess.pop('show_location_popup', None)
            sess.pop('location_popup_source', None)
        return {'SHOW_LOCATION_POPUP': show}
    except Exception:
        return {'SHOW_LOCATION_POPUP': False}


def notifications_popup(request):
    """Expose a one-time notifications permission popup flag.

    Reads request.session['show_notifications_popup'] and clears it after consumption.
    """
    try:
        # Never show this prompt inside the Django admin.
        try:
            if str(getattr(request, 'path', '') or '').startswith('/admin'):
                return {'SHOW_NOTIFICATIONS_POPUP': False}
        except Exception:
            pass

        sess = getattr(request, 'session', None)
        if not sess:
            return {'SHOW_NOTIFICATIONS_POPUP': False}

        show = bool(sess.get('show_notifications_popup'))
        if show:
            # Ensure CSRF cookie exists for JS fetch() POST.
            try:
                from django.middleware.csrf import get_token

                get_token(request)
            except Exception:
                pass
            sess.pop('show_notifications_popup', None)
            sess.pop('notifications_popup_source', None)

        return {'SHOW_NOTIFICATIONS_POPUP': show}
    except Exception:
        return {'SHOW_NOTIFICATIONS_POPUP': False}


def site_stats(request):
    """Expose lightweight site-wide stats to templates (cached)."""
    try:
        cache_key = 'vixo:total_users_count'
        cached = cache.get(cache_key)
        if cached is None:
            User = get_user_model()
            cached = int(User.objects.filter(is_active=True).count())
            cache.set(cache_key, cached, timeout=300)
        return {'TOTAL_USERS_COUNT': int(cached)}
    except Exception:
        return {'TOTAL_USERS_COUNT': 0}
