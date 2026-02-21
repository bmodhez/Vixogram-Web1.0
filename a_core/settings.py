from pathlib import Path
import os

from urllib.parse import urlparse
import dj_database_url
from django.core.exceptions import ImproperlyConfigured


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# --- Internationalization / Time zone ---
# The project previously relied on Django defaults (UTC). Set an explicit time zone
# so timestamps like chat bans show the expected local time in templates.
LANGUAGE_CODE = (os.environ.get('LANGUAGE_CODE') or 'en-us').strip() or 'en-us'
TIME_ZONE = (os.environ.get('TIME_ZONE') or 'Asia/Kolkata').strip() or 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

# Optional: load local .env (keeps secrets out of code)
#
# IMPORTANT:
# - For local/dev, we want the real `.env` file to be the single source of truth.
# - On hosted platforms (Render, etc.) you typically don't have a `.env` file on disk;
#   env vars come from the platform dashboard.
#
# We use overwrite=True so `.env` wins over stale machine/user-level env vars.
try:
    import environ

    env = environ.Env()
    _env_path = BASE_DIR / '.env'
    _env_alt_path = BASE_DIR / 'env'
    if _env_path.exists():
        environ.Env.read_env(str(_env_path), overwrite=True)
    elif _env_alt_path.exists():
        environ.Env.read_env(str(_env_alt_path), overwrite=True)
except Exception:
    # If django-environ isn't installed or .env missing, fall back to normal os.environ
    pass


# --- Groq (OpenAI-compatible) settings for Natasha bot ---
# IMPORTANT: Do NOT hardcode API keys in code. Set via environment.
# NOTE: These must be computed AFTER .env is loaded.
GROQ_API_KEY = (os.environ.get('GROQ_API_KEY') or '').strip()
GROQ_MODEL = (os.environ.get('GROQ_MODEL') or 'openai/gpt-oss-120b').strip() or 'openai/gpt-oss-120b'

# --- OpenRouter (OpenAI-compatible) settings for Natasha bot ---
OPENROUTER_API_KEY = (os.environ.get('OPENROUTER_API_KEY') or '').strip()
OPENROUTER_MODEL = (
    (os.environ.get('OPENROUTER_MODEL') or 'meta-llama/llama-3.2-3b-instruct:free').strip()
    or 'meta-llama/llama-3.2-3b-instruct:free'
)


# Detect Render platform early (used to pick safer defaults)
IS_RENDER = bool((os.environ.get('RENDER_EXTERNAL_URL') or '').strip() or (os.environ.get('RENDER') or '').strip())


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "t", "yes", "y", "on"}


def _origin_from_url(url: str) -> str | None:
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


ENVIRONMENT = (os.environ.get("ENVIRONMENT") or ("production" if IS_RENDER else "development")).strip().lower()

# Public contact info (shown in navbar + support page)
CONTACT_EMAIL = (os.environ.get('CONTACT_EMAIL') or '').strip()
CONTACT_INSTAGRAM_URL = (
    (os.environ.get('CONTACT_INSTAGRAM_URL') or 'https://www.instagram.com/bhavinmodhh/').strip()
)

# Google reCAPTCHA (Signup protection)
# IMPORTANT: Do NOT hardcode keys in code. Use environment vars or local .env.
#
# Supports:
# - v2 checkbox (default)
# - v3 (score-based, no visible checkbox)
# - enterprise script/verify endpoint (optional)
RECAPTCHA_SITE_KEY = (os.environ.get('RECAPTCHA_SITE_KEY') or '').strip()
RECAPTCHA_SECRET_KEY = (os.environ.get('RECAPTCHA_SECRET_KEY') or '').strip()

RECAPTCHA_PROVIDER = (os.environ.get('RECAPTCHA_PROVIDER') or 'standard').strip().lower()
if RECAPTCHA_PROVIDER not in {'standard', 'enterprise'}:
    RECAPTCHA_PROVIDER = 'standard'

RECAPTCHA_VERSION = (os.environ.get('RECAPTCHA_VERSION') or 'v2').strip().lower()
if RECAPTCHA_VERSION not in {'v2', 'v3'}:
    RECAPTCHA_VERSION = 'v2'

_default_verify_url = (
    'https://www.google.com/recaptcha/enterprise/siteverify'
    if RECAPTCHA_PROVIDER == 'enterprise'
    else 'https://www.google.com/recaptcha/api/siteverify'
)
RECAPTCHA_VERIFY_URL = (os.environ.get('RECAPTCHA_VERIFY_URL') or _default_verify_url).strip()
RECAPTCHA_TIMEOUT_SECONDS = float(os.environ.get('RECAPTCHA_TIMEOUT_SECONDS') or 4.0)

# v3-only settings
RECAPTCHA_ACTION = (os.environ.get('RECAPTCHA_ACTION') or 'signup').strip() or 'signup'
RECAPTCHA_MIN_SCORE = float(os.environ.get('RECAPTCHA_MIN_SCORE') or 0.5)

# Script URL used by templates
_recaptcha_script_base = (
    'https://www.google.com/recaptcha/enterprise.js'
    if RECAPTCHA_PROVIDER == 'enterprise'
    else 'https://www.google.com/recaptcha/api.js'
)
if RECAPTCHA_VERSION == 'v3' and RECAPTCHA_SITE_KEY:
    RECAPTCHA_SCRIPT_URL = f"{_recaptcha_script_base}?render={RECAPTCHA_SITE_KEY}"
else:
    RECAPTCHA_SCRIPT_URL = _recaptcha_script_base

RECAPTCHA_ENABLED = _env_bool('RECAPTCHA_ENABLED', default=bool(RECAPTCHA_SITE_KEY and RECAPTCHA_SECRET_KEY))

# Whether signup must pass reCAPTCHA verification.
# Default: only require in production when reCAPTCHA is enabled.
RECAPTCHA_REQUIRED = _env_bool(
    'RECAPTCHA_REQUIRED',
    default=bool(RECAPTCHA_ENABLED and ENVIRONMENT == 'production'),
)

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = (os.environ.get("SECRET_KEY") or "").strip() or "django-insecure-change-me-in-env"

# In production, refuse to start if a real SECRET_KEY isn't configured.
if ENVIRONMENT == "production" and SECRET_KEY == "django-insecure-change-me-in-env":
    raise ImproperlyConfigured(
        "SECRET_KEY is required when ENVIRONMENT=production. "
        "Set a strong random value in your hosting platform environment vars."
    )

# DEBUG:
# - In production, default is False.
# - In dev, default is True, but allow overriding via env var (so you can test
#   proper 404/500 pages, email flows, etc.).
DEBUG = _env_bool("DEBUG", default=(ENVIRONMENT != "production"))

_cloud_name = os.environ.get('CLOUD_NAME')
_cloud_key = os.environ.get('API_KEY')
_cloud_secret = os.environ.get('API_SECRET')
_cloudinary_creds_present = bool(_cloud_name and _cloud_key and _cloud_secret)

# Cloudinary media uploads
# - Production defaults to Cloudinary when creds exist.
# - You can force-enable in dev by setting USE_CLOUDINARY_MEDIA=1.
USE_CLOUDINARY_MEDIA = _env_bool(
    'USE_CLOUDINARY_MEDIA',
    default=(ENVIRONMENT == 'production' and _cloudinary_creds_present),
)
_use_cloudinary_media = bool(USE_CLOUDINARY_MEDIA and _cloudinary_creds_present)

# Django 4.2+ storage configuration
# Media (uploads): Cloudinary when enabled, else local filesystem.
# Static: In production, use Whitenoise compression WITHOUT manifest hashing.
# This prevents runtime 500s if a referenced static file wasn't collected.
_static_backend = (
    'whitenoise.storage.CompressedStaticFilesStorage'
    if ENVIRONMENT == 'production'
    else 'django.contrib.staticfiles.storage.StaticFilesStorage'
)

STORAGES = {
    'default': {
        'BACKEND': (
            'a_core.storage.ModeratedMediaCloudinaryStorage'
            if _use_cloudinary_media
            else 'django.core.files.storage.FileSystemStorage'
        ),
    },
    'staticfiles': {
        'BACKEND': _static_backend,
    },
}

# Cloudinary upload moderation provider
# - Default: AWS Rekognition (aws_rek)
# - Override via env: CLOUDINARY_UPLOAD_MODERATION
CLOUDINARY_UPLOAD_MODERATION = (os.environ.get('CLOUDINARY_UPLOAD_MODERATION') or 'aws_rek').strip() or 'aws_rek'

# If True, block saving media when moderation returns pending.
# This gives "before save" semantics (user must retry later).
CLOUDINARY_UPLOAD_BLOCK_PENDING = _env_bool('CLOUDINARY_UPLOAD_BLOCK_PENDING', default=True)

# In production, prefer stability over strictness: serve static files using
# Django's staticfiles finders as a fallback. This prevents runtime 500/404s
# if collectstatic output is missing/stale on a deploy.
if ENVIRONMENT == 'production':
    WHITENOISE_USE_FINDERS = True



ALLOWED_HOSTS: list[str] = []

# Dev-friendly defaults.
if ENVIRONMENT != "production":
    ALLOWED_HOSTS.extend(
        [
            "localhost",
            "127.0.0.1",
            ".onrender.com",
        ]
    )

    # VS Code Dev Tunnels (opt-in; keep off by default for safety).
    if _env_bool("DEVTUNNEL_ENABLED", default=False):
        ALLOWED_HOSTS.extend(
            [
                ".devtunnels.ms",
                ".inc1.devtunnels.ms",
            ]
        )

# Known production hosts (add your custom domain via env ALLOWED_HOSTS).
ALLOWED_HOSTS.extend(
    [
        "vixogram-connect.onrender.com",
        "vixogram.onrender.com",
    ]
)

# Render exposes the external URL for the service; use it to auto-trust the correct host.
RENDER_EXTERNAL_URL = (os.environ.get("RENDER_EXTERNAL_URL") or "").strip()
_render_origin = _origin_from_url(RENDER_EXTERNAL_URL) if RENDER_EXTERNAL_URL else None
if _render_origin:
    try:
        _render_host = urlparse(RENDER_EXTERNAL_URL).netloc.split(":")[0]
        if _render_host and _render_host not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(_render_host)
    except Exception:
        pass

_extra_allowed_hosts = os.environ.get("ALLOWED_HOSTS", "").strip()
if _extra_allowed_hosts:
    ALLOWED_HOSTS.extend([h.strip() for h in _extra_allowed_hosts.split(",") if h.strip()])

CSRF_TRUSTED_ORIGINS: list[str] = []

# Dev-only origins
if ENVIRONMENT != "production":
    CSRF_TRUSTED_ORIGINS.extend(
        [
            "http://localhost",
            "http://127.0.0.1",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ]
    )
    if _env_bool("DEVTUNNEL_ENABLED", default=False):
        CSRF_TRUSTED_ORIGINS.extend(
            [
                "https://*.devtunnels.ms",
                "http://*.devtunnels.ms",
                "https://*.inc1.devtunnels.ms",
                "http://*.inc1.devtunnels.ms",
            ]
        )

# Production/service origins
CSRF_TRUSTED_ORIGINS.extend(
    [
        "https://vixogram-connect.onrender.com",
        "https://vixogram.onrender.com",
    ]
)

if _render_origin and _render_origin not in CSRF_TRUSTED_ORIGINS:
    CSRF_TRUSTED_ORIGINS.append(_render_origin)

# Render terminates TLS at the proxy; trust HTTPS origins in production.
if ENVIRONMENT == "production":
    CSRF_TRUSTED_ORIGINS.extend(
        [
            "https://*.onrender.com",
        ]
    )

_extra_csrf_trusted = os.environ.get("CSRF_TRUSTED_ORIGINS", "").strip()
if _extra_csrf_trusted:
    CSRF_TRUSTED_ORIGINS.extend(
        [o.strip() for o in _extra_csrf_trusted.split(",") if o.strip()]
    )

if ENVIRONMENT == "production" or (_render_origin and _render_origin.startswith("https://")):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True

    # SecurityMiddleware hardening (safe defaults; override via env if needed).
    SECURE_SSL_REDIRECT = _env_bool("SECURE_SSL_REDIRECT", default=(ENVIRONMENT == "production"))
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = (os.environ.get("SECURE_REFERRER_POLICY") or "same-origin").strip() or "same-origin"

    # Start with a conservative HSTS default (1 hour). Increase once you confirm
    # HTTPS is stable for your domain.
    try:
        SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS") or "3600")
    except Exception:
        SECURE_HSTS_SECONDS = 3600
    SECURE_HSTS_INCLUDE_SUBDOMAINS = _env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", default=False)
    SECURE_HSTS_PRELOAD = _env_bool("SECURE_HSTS_PRELOAD", default=False)

# VS Code Port Forwarding / Dev Tunnels typically terminates TLS at the proxy.
# IMPORTANT: Do NOT auto-enable this just because ALLOWED_HOSTS contains
# ".devtunnels.ms"; that would force https:// links even for local 127.0.0.1.
# Enable explicitly when you are actually serving via a Dev Tunnel.
_using_devtunnel = _env_bool('DEVTUNNEL_ENABLED', default=False)
if _using_devtunnel:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Custom CSRF failure view (shows a friendly 403 page).
CSRF_FAILURE_VIEW = "a_core.error_views.csrf_failure"

# Application definition
INSTALLED_APPS = [
    'daphne', # Daphne ko sabse upar rehne dein
    'channels',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    'django_cleanup.apps.CleanupConfig',
    'cloudinary_storage',
    'cloudinary',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'django_htmx',
    # Project package: included so its management commands are discoverable.
    'a_core',
    'a_home',
    'a_users.apps.AUsersConfig',
    'a_rtchat',
]

# Password hashing
#
# Django's default PBKDF2 iterations can be slow on low-CPU hosts (login/signup feel laggy).
# You can tune it via env var PBKDF2_ITERATIONS.
# This custom hasher will NOT downgrade existing stronger hashes.
PASSWORD_HASHERS = [
    'a_core.hashers.ConfigurablePBKDF2PasswordHasher',
    # Fallbacks (in case older hashes exist)
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher',
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.BCryptSHA256PasswordHasher',
]

# Authentication
# - Keep allauth backend for its flows.
# - Add a simple backend to allow logging in via User.email as well as username
#   (useful for users created via admin/legacy data without an allauth EmailAddress row).
AUTHENTICATION_BACKENDS = [
    'a_users.auth_backends.EmailOrUsernameModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

SITE_ID = 1

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'a_core.middleware.ForceCustom404Middleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'a_users.middleware.UserDeviceTrackingMiddleware',
    'a_core.middleware.VpnProxyEnforcementMiddleware',
    'a_core.middleware.MaintenanceModeMiddleware',
    'a_users.middleware.ActiveUserRequiredMiddleware',
    'a_users.middleware.FounderClubEnforcementMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'a_core.middleware.RateLimitMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
    'django_htmx.middleware.HtmxMiddleware',
]


# Cloudinary settings verify karein (Images ke liye)
CLOUDINARY_STORAGE = {
    'CLOUD_NAME': os.environ.get('CLOUD_NAME'),
    'API_KEY': os.environ.get('API_KEY'),
    'API_SECRET': os.environ.get('API_SECRET'),
}



ROOT_URLCONF = 'a_core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [ BASE_DIR / 'templates' ], # Root templates folder use hoga
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'a_core.context_processors.firebase_config',
                'a_core.context_processors.site_contact',
                'a_core.context_processors.recaptcha_config',
                'a_core.context_processors.welcome_popup',
                'a_core.context_processors.location_popup',
                'a_core.context_processors.notifications_popup',
                'a_core.context_processors.email_verify_popup',
                'a_core.context_processors.vpn_proxy_popup',
                'a_core.context_processors.site_stats',
                'a_users.context_processors.notifications_badge',
                'a_users.context_processors.follow_requests_badge',
                'a_users.context_processors.story_upload_gate',
                'a_rtchat.context_processors.admin_reports_badge',
                'a_rtchat.context_processors.mobile_ads_config',
                'a_rtchat.context_processors.global_announcement',
            ],
        },
    },
]

# --- Mobile Ads (future-safe, mobile-only UI logic lives in JS) ---
# Default: ON in dev, OFF in production unless explicitly enabled.
MOBILE_ADS_ENABLED = _env_bool('MOBILE_ADS_ENABLED', default=(ENVIRONMENT != 'production'))
MOBILE_ADS_DISABLE_FOR_STAFF = _env_bool('MOBILE_ADS_DISABLE_FOR_STAFF', default=(ENVIRONMENT == 'production'))

# External-ad friendly defaults (configure via env vars for real ads).
# Tip: set *_CTA_URL to your advertiser landing page.
MOBILE_AD_CHAT_LIST_TITLE = os.environ.get('MOBILE_AD_CHAT_LIST_TITLE', 'Sponsored')
MOBILE_AD_CHAT_LIST_BODY = os.environ.get('MOBILE_AD_CHAT_LIST_BODY', '')
MOBILE_AD_CHAT_LIST_CTA_TEXT = os.environ.get('MOBILE_AD_CHAT_LIST_CTA_TEXT', 'Learn more')
MOBILE_AD_CHAT_LIST_CTA_URL = os.environ.get('MOBILE_AD_CHAT_LIST_CTA_URL', '')
MOBILE_AD_CHAT_LIST_IMAGE_URL = os.environ.get('MOBILE_AD_CHAT_LIST_IMAGE_URL', '')
MOBILE_AD_CHAT_LIST_ADVERTISER = os.environ.get('MOBILE_AD_CHAT_LIST_ADVERTISER', '')

MOBILE_AD_CHAT_FEED_TITLE = os.environ.get('MOBILE_AD_CHAT_FEED_TITLE', 'Sponsored')
MOBILE_AD_CHAT_FEED_BODY = os.environ.get('MOBILE_AD_CHAT_FEED_BODY', '')
MOBILE_AD_CHAT_FEED_CTA_TEXT = os.environ.get('MOBILE_AD_CHAT_FEED_CTA_TEXT', 'Open')
MOBILE_AD_CHAT_FEED_CTA_URL = os.environ.get('MOBILE_AD_CHAT_FEED_CTA_URL', '')
MOBILE_AD_CHAT_FEED_IMAGE_URL = os.environ.get('MOBILE_AD_CHAT_FEED_IMAGE_URL', '')
MOBILE_AD_CHAT_FEED_ADVERTISER = os.environ.get('MOBILE_AD_CHAT_FEED_ADVERTISER', '')

# --- IPL Live Score integration (backend-only API calls) ---
IPL_RAPIDAPI_KEY = (os.environ.get('IPL_RAPIDAPI_KEY') or '').strip()
IPL_RAPIDAPI_HOST = (os.environ.get('IPL_RAPIDAPI_HOST') or 'cricbuzz-cricket.p.rapidapi.com').strip()
IPL_CRICBUZZ_LIVE_URL = (
    os.environ.get('IPL_CRICBUZZ_LIVE_URL')
    or 'https://cricbuzz-cricket.p.rapidapi.com/matches/v1/live'
)
IPL_RAPIDAPI_TIMEOUT_SECONDS = float(os.environ.get('IPL_RAPIDAPI_TIMEOUT_SECONDS') or 8.0)
IPL_POLL_INTERVAL_SECONDS = int(os.environ.get('IPL_POLL_INTERVAL_SECONDS') or 180)
IPL_SCORE_CACHE_TTL_SECONDS = int(os.environ.get('IPL_SCORE_CACHE_TTL_SECONDS') or 21600)
IPL_LIVE_SCORE_CHAT_ROOM = (os.environ.get('IPL_LIVE_SCORE_CHAT_ROOM') or 'public-chat').strip() or 'public-chat'

# Widget defaults (client can still drag/reposition; this is initial placement).
IPL_WIDGET_DEFAULT_POSITION = (os.environ.get('IPL_WIDGET_DEFAULT_POSITION') or 'top-center').strip()
IPL_WIDGET_DEFAULT_MINIMIZED = _env_bool('IPL_WIDGET_DEFAULT_MINIMIZED', default=False)

ASGI_APPLICATION = 'a_core.asgi.application'

# Render ya Railway par ye variables environment se uthayenge
REDIS_URL = os.environ.get('REDIS_URL')


def _redis_ssl_cert_reqs_from_env() -> object | None:
    """Return an ssl_cert_reqs value compatible with redis-py.

    Supported env values:
    - none / false / 0: disable cert verification (NOT recommended, but sometimes needed)
    - required / true / 1: require cert verification (default)
    """
    raw = (os.environ.get('REDIS_SSL_CERT_REQS') or '').strip().lower()
    if not raw:
        return None
    if raw in {'none', 'false', '0', 'off', 'no'}:
        return None
    # redis-py defaults to ssl.CERT_REQUIRED when using rediss://, so we don't
    # need to explicitly set it here.
    return 'required'


def _redis_connection_options() -> dict:
    opts: dict = {
        'socket_connect_timeout': float(os.environ.get('REDIS_CONNECT_TIMEOUT', '1.0')),
        'socket_timeout': float(os.environ.get('REDIS_SOCKET_TIMEOUT', '1.5')),
        'retry_on_timeout': True,
    }

    # Optional TLS tuning for hosted Redis providers.
    # Only applied if REDIS_SSL_CERT_REQS is explicitly set.
    ssl_cert_reqs = _redis_ssl_cert_reqs_from_env()
    if ssl_cert_reqs is not None:
        opts['ssl_cert_reqs'] = ssl_cert_reqs

    return opts

# --- Cache / sessions (important for scale) ---
# Rate limiting and other anti-abuse features rely on Django's cache.
# If you scale to multiple processes/instances, you should use a shared cache
# (Redis) so limits and mutes are consistent across all workers.
USE_REDIS_CACHE = _env_bool(
    'USE_REDIS_CACHE',
    default=(ENVIRONMENT == 'production' and bool((REDIS_URL or '').strip())),
)

if USE_REDIS_CACHE and REDIS_URL:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': REDIS_URL,
            'OPTIONS': {
                **_redis_connection_options(),
            },
        }
    }
    # Use cache-backed sessions with DB fallback (safer than pure cache sessions).
    SESSION_ENGINE = 'django.contrib.sessions.backends.cached_db'
    SESSION_CACHE_ALIAS = 'default'
else:
    # Local/dev fallback (single-process friendly)
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'vixogram-locmem',
        }
    }

# Local/dev: don't depend on Redis (prevents WS disconnects when Redis isn't running).
if ENVIRONMENT == 'production' and REDIS_URL:
    _redis_host_entry: object

    # channels_redis supports either string URLs or dicts.
    # For TLS Redis (rediss://), some providers need ssl_cert_reqs disabled.
    # We only apply that if REDIS_SSL_CERT_REQS is explicitly set.
    ssl_cert_reqs = _redis_ssl_cert_reqs_from_env()
    if ssl_cert_reqs is not None:
        _redis_host_entry = {
            'address': REDIS_URL,
            'ssl_cert_reqs': ssl_cert_reqs,
        }
    else:
        _redis_host_entry = REDIS_URL

    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                'hosts': [_redis_host_entry],
            },
        },
    }
else:
    # Note: InMemory channel layer works only within a single process.
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        },
    }

# Agar production ho toh DATABASE_URL required hai, warna local SQLite
if ENVIRONMENT == 'production':
    _database_url = (os.environ.get('DATABASE_URL') or '').strip()
    if not _database_url:
        raise ImproperlyConfigured(
            'DATABASE_URL is required when ENVIRONMENT=production (e.g. on Render). '
            'Set it in Render Dashboard (PostgreSQL Internal Database URL).'
        )
    DATABASES = {
        'default': dj_database_url.parse(_database_url)
    }

    # Keep DB connections open briefly to reduce connection churn under load.
    # (Most managed Postgres services recommend this.)
    try:
        DATABASES['default'].setdefault('CONN_MAX_AGE', int(os.environ.get('DB_CONN_MAX_AGE', '60')))
    except Exception:
        DATABASES['default']['CONN_MAX_AGE'] = 60
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
# Static & Media Files
# Use leading slashes so URLs resolve correctly from nested routes (e.g. /chat/room/...)
STATIC_URL = '/static/'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
    # Allows serving assets committed under frontend/public/static (e.g. incoming.wav)
    # without copying them into the Django static folder.
    BASE_DIR / 'frontend' / 'public' / 'static',
]

# --- Abuse prevention / rate limiting defaults (override via env or settings) ---
# Auth (accounts/* POST)
AUTH_RATE_LIMIT = int(os.environ.get('AUTH_RATE_LIMIT', '25'))
AUTH_RATE_LIMIT_PERIOD = int(os.environ.get('AUTH_RATE_LIMIT_PERIOD', '300'))

# Chat HTTP sends (HTMX)
CHAT_MSG_RATE_LIMIT = int(os.environ.get('CHAT_MSG_RATE_LIMIT', '8'))
CHAT_MSG_RATE_PERIOD = int(os.environ.get('CHAT_MSG_RATE_PERIOD', '10'))

# Chat message retention (per room)
# Keep only the newest N messages per room; older messages are deleted.
CHAT_MAX_MESSAGES_PER_ROOM = int(os.environ.get('CHAT_MAX_MESSAGES_PER_ROOM', '250'))

# Private rooms can have a different cap to protect DB size.
# Default is higher than public rooms, but still bounded.
PRIVATE_CHAT_MAX_MESSAGES_PER_ROOM = int(os.environ.get('PRIVATE_CHAT_MAX_MESSAGES_PER_ROOM', '1000'))

# Chat UI performance
# Initial messages rendered into the DOM on room open. Keep this small to prevent
# low-end devices from freezing when rooms have large histories.
CHAT_INITIAL_MESSAGES = int(os.environ.get('CHAT_INITIAL_MESSAGES', '40'))
# Page size when the user taps "Load older".
CHAT_HISTORY_PAGE_SIZE = int(os.environ.get('CHAT_HISTORY_PAGE_SIZE', '35'))

# Email verification: unverified users are allowed a limited number of messages.
# After this, they must verify their email to continue chatting.
UNVERIFIED_CHAT_MESSAGE_LIMIT = int(os.environ.get('UNVERIFIED_CHAT_MESSAGE_LIMIT', '3'))

# Invite points
# Points are awarded after the referred user verifies email (see a_users.signals).
# Default tuned so 35 verified invites ~ 450 points.
REFERRAL_POINTS_PER_INVITE = int(os.environ.get('REFERRAL_POINTS_PER_INVITE', '13'))

# Founder Club (invite rewards)
FOUNDER_CLUB_REQUIRED_POINTS = int(os.environ.get('FOUNDER_CLUB_REQUIRED_POINTS', '450'))
FOUNDER_CLUB_REQUIRED_INVITES = int(os.environ.get('FOUNDER_CLUB_REQUIRED_INVITES', '35'))
FOUNDER_CLUB_MIN_ACCOUNT_AGE_DAYS = int(os.environ.get('FOUNDER_CLUB_MIN_ACCOUNT_AGE_DAYS', '20'))
FOUNDER_CLUB_MIN_ACTIVE_SECONDS_PER_DAY = int(os.environ.get('FOUNDER_CLUB_MIN_ACTIVE_SECONDS_PER_DAY', '3600'))
FOUNDER_CLUB_REAPPLY_COOLDOWN_DAYS = int(os.environ.get('FOUNDER_CLUB_REAPPLY_COOLDOWN_DAYS', '20'))

# Chat burst protection (fast spam): if a user sends too many messages in a very short window,
# apply a short cooldown (uses the same cache backend as other rate limits).
CHAT_BURST_MSG_LIMIT = int(os.environ.get('CHAT_BURST_MSG_LIMIT', '5'))
CHAT_BURST_MSG_PERIOD = int(os.environ.get('CHAT_BURST_MSG_PERIOD', '3'))
CHAT_BURST_COOLDOWN_SECONDS = int(os.environ.get('CHAT_BURST_COOLDOWN_SECONDS', '10'))

# Room-wide flood protection
ROOM_MSG_RATE_LIMIT = int(os.environ.get('ROOM_MSG_RATE_LIMIT', '1000'))
ROOM_MSG_RATE_PERIOD = int(os.environ.get('ROOM_MSG_RATE_PERIOD', '10'))

# Duplicate message detection
DUPLICATE_MSG_TTL = int(os.environ.get('DUPLICATE_MSG_TTL', '15'))

# Emoji spam detection (e.g., 🤡🤡🤡🤡)
EMOJI_SPAM_MIN_REPEATS = int(os.environ.get('EMOJI_SPAM_MIN_REPEATS', '4'))
EMOJI_SPAM_TTL = int(os.environ.get('EMOJI_SPAM_TTL', '15'))

# Copy/paste + bot-like typing speed heuristics
PASTE_LONG_MSG_LEN = int(os.environ.get('PASTE_LONG_MSG_LEN', '60'))
PASTE_TYPED_MS_MAX = int(os.environ.get('PASTE_TYPED_MS_MAX', '400'))
TYPING_CPS_THRESHOLD = int(os.environ.get('TYPING_CPS_THRESHOLD', '25'))
SPEED_SPAM_TTL = int(os.environ.get('SPEED_SPAM_TTL', '10'))

# Notifications persistence
#
# If False, some in-app notifications are only sent via websocket toasts when
# the recipient is online, which can make the dropdown look empty.
PERSIST_NOTIFICATIONS_WHEN_ONLINE = _env_bool('PERSIST_NOTIFICATIONS_WHEN_ONLINE', default=True)

# Fast long message heuristic (server-side)
FAST_LONG_MSG_LEN = int(os.environ.get('FAST_LONG_MSG_LEN', '80'))
FAST_LONG_MSG_MIN_INTERVAL = int(os.environ.get('FAST_LONG_MSG_MIN_INTERVAL', '1'))

# WebSocket events
WS_TYPING_RATE_LIMIT = int(os.environ.get('WS_TYPING_RATE_LIMIT', '12'))
WS_TYPING_RATE_PERIOD = int(os.environ.get('WS_TYPING_RATE_PERIOD', '10'))
WS_MSG_RATE_LIMIT = int(os.environ.get('WS_MSG_RATE_LIMIT', '8'))
WS_MSG_RATE_PERIOD = int(os.environ.get('WS_MSG_RATE_PERIOD', '10'))

# Uploads / poll
CHAT_UPLOAD_RATE_LIMIT = int(os.environ.get('CHAT_UPLOAD_RATE_LIMIT', '3'))
CHAT_UPLOAD_RATE_PERIOD = int(os.environ.get('CHAT_UPLOAD_RATE_PERIOD', '60'))
CHAT_POLL_RATE_LIMIT = int(os.environ.get('CHAT_POLL_RATE_LIMIT', '240'))
CHAT_POLL_RATE_PERIOD = int(os.environ.get('CHAT_POLL_RATE_PERIOD', '60'))

# Abuse strikes -> auto mute
CHAT_ABUSE_WINDOW = int(os.environ.get('CHAT_ABUSE_WINDOW', '600'))
CHAT_ABUSE_STRIKE_THRESHOLD = int(os.environ.get('CHAT_ABUSE_STRIKE_THRESHOLD', '5'))
CHAT_ABUSE_MUTE_SECONDS = int(os.environ.get('CHAT_ABUSE_MUTE_SECONDS', '60'))

# AI moderation (Gemini)
# IMPORTANT: Keep API key in environment (never hardcode it).
AI_MODERATION_ENABLED = int(os.environ.get('AI_MODERATION_ENABLED', '0'))
AI_LOG_ALL = int(os.environ.get('AI_LOG_ALL', '0'))
AI_MIN_CONFIDENCE = float(os.environ.get('AI_MIN_CONFIDENCE', '0.55'))
AI_FLAG_MIN_SEVERITY = int(os.environ.get('AI_FLAG_MIN_SEVERITY', '1'))
AI_BLOCK_MIN_SEVERITY = int(os.environ.get('AI_BLOCK_MIN_SEVERITY', '2'))

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-1.5-flash')
GEMINI_TIMEOUT_SECONDS = float(os.environ.get('GEMINI_TIMEOUT_SECONDS', '4.0'))

# Other endpoints
PRIVATE_ROOM_CREATE_RATE_LIMIT = int(os.environ.get('PRIVATE_ROOM_CREATE_RATE_LIMIT', '5'))
PRIVATE_ROOM_CREATE_RATE_PERIOD = int(os.environ.get('PRIVATE_ROOM_CREATE_RATE_PERIOD', '300'))
PRIVATE_ROOM_JOIN_RATE_LIMIT = int(os.environ.get('PRIVATE_ROOM_JOIN_RATE_LIMIT', '10'))
PRIVATE_ROOM_JOIN_RATE_PERIOD = int(os.environ.get('PRIVATE_ROOM_JOIN_RATE_PERIOD', '300'))
GROUPCHAT_CREATE_RATE_LIMIT = int(os.environ.get('GROUPCHAT_CREATE_RATE_LIMIT', '10'))
GROUPCHAT_CREATE_RATE_PERIOD = int(os.environ.get('GROUPCHAT_CREATE_RATE_PERIOD', '600'))

CHAT_EDIT_RATE_LIMIT = int(os.environ.get('CHAT_EDIT_RATE_LIMIT', '30'))
CHAT_EDIT_RATE_PERIOD = int(os.environ.get('CHAT_EDIT_RATE_PERIOD', '60'))
CHAT_DELETE_RATE_LIMIT = int(os.environ.get('CHAT_DELETE_RATE_LIMIT', '20'))
CHAT_DELETE_RATE_PERIOD = int(os.environ.get('CHAT_DELETE_RATE_PERIOD', '60'))

CALL_INVITE_RATE_LIMIT = int(os.environ.get('CALL_INVITE_RATE_LIMIT', '6'))
CALL_INVITE_RATE_PERIOD = int(os.environ.get('CALL_INVITE_RATE_PERIOD', '60'))
CALL_PRESENCE_RATE_LIMIT = int(os.environ.get('CALL_PRESENCE_RATE_LIMIT', '60'))
CALL_PRESENCE_RATE_PERIOD = int(os.environ.get('CALL_PRESENCE_RATE_PERIOD', '60'))
CALL_EVENT_RATE_LIMIT = int(os.environ.get('CALL_EVENT_RATE_LIMIT', '30'))
CALL_EVENT_RATE_PERIOD = int(os.environ.get('CALL_EVENT_RATE_PERIOD', '60'))

# VPN/proxy guard
VPN_PROXY_GUARD_ENABLED = _env_bool('VPN_PROXY_GUARD_ENABLED', default=True)
VPN_PROXY_BYPASS_ADMIN = _env_bool('VPN_PROXY_BYPASS_ADMIN', default=False)
VPN_PROXY_STATUS_CACHE_SECONDS = int(os.environ.get('VPN_PROXY_STATUS_CACHE_SECONDS', '120'))
VPN_PROXY_CHECK_INTERVAL_SECONDS = int(os.environ.get('VPN_PROXY_CHECK_INTERVAL_SECONDS', '5'))

AGORA_TOKEN_RATE_LIMIT = int(os.environ.get('AGORA_TOKEN_RATE_LIMIT', '30'))
AGORA_TOKEN_RATE_PERIOD = int(os.environ.get('AGORA_TOKEN_RATE_PERIOD', '300'))

ADMIN_BLOCK_TOGGLE_RATE_LIMIT = int(os.environ.get('ADMIN_BLOCK_TOGGLE_RATE_LIMIT', '60'))
ADMIN_BLOCK_TOGGLE_RATE_PERIOD = int(os.environ.get('ADMIN_BLOCK_TOGGLE_RATE_PERIOD', '60'))
STATIC_ROOT = BASE_DIR / 'staticfiles' 

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Chat upload limits
# Override if needed (e.g., for production):
# - CHAT_UPLOAD_LIMIT_PER_ROOM: max uploads per user per room
# - CHAT_UPLOAD_MAX_BYTES: max single file size
CHAT_UPLOAD_LIMIT_PER_ROOM = int(os.environ.get('CHAT_UPLOAD_LIMIT_PER_ROOM', '15'))
CHAT_UPLOAD_MAX_BYTES = 10 * 1024 * 1024

# Agora (Voice/Video Calls)
# IMPORTANT: Do not hardcode your Agora certificate in git.
# Set these via environment variables or a local .env file.
AGORA_APP_ID = os.environ.get('AGORA_APP_ID', '')
AGORA_APP_CERTIFICATE = os.environ.get('AGORA_APP_CERTIFICATE', '')
AGORA_TOKEN_EXPIRE_SECONDS = int(os.environ.get('AGORA_TOKEN_EXPIRE_SECONDS', '3600'))

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_REDIRECT_URL = '/'

# Email settings
# - If EMAIL_HOST_USER + EMAIL_HOST_PASSWORD are set, send real emails via SMTP.
# - Otherwise, avoid printing emails in the runserver terminal.
# You can override everything via environment variables.
EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', '').strip() or None

EMAIL_HOST_USER = (os.getenv('EMAIL_HOST_USER', '') or '').strip()
EMAIL_HOST_PASSWORD = (os.getenv('EMAIL_HOST_PASSWORD', '') or '').strip()
EMAIL_HOST = (os.getenv('EMAIL_HOST', 'smtp.gmail.com') or 'smtp.gmail.com').strip()
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587') or '587')
EMAIL_USE_TLS = _env_bool('EMAIL_USE_TLS', default=True)
EMAIL_USE_SSL = _env_bool('EMAIL_USE_SSL', default=False)
EMAIL_TIMEOUT = int(os.getenv('EMAIL_TIMEOUT', '8') or '8')

# Avoid empty From: headers.
DEFAULT_FROM_EMAIL = (os.getenv('DEFAULT_FROM_EMAIL', '') or '').strip() or (EMAIL_HOST_USER or 'no-reply@localhost')

# When using file-based email backend, store messages here (so they don't spam the console).
EMAIL_FILE_PATH = (os.getenv('EMAIL_FILE_PATH', '') or '').strip() or str(BASE_DIR / 'tmp_emails')

if not EMAIL_BACKEND:
    if EMAIL_HOST_USER and EMAIL_HOST_PASSWORD:
        EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    else:
        # Dev default: keep emails available without printing them to the terminal.
        # Production safety: if SMTP isn't configured, drop emails instead of leaking them to logs.
        if ENVIRONMENT == 'development':
            EMAIL_BACKEND = 'django.core.mail.backends.filebased.EmailBackend'
        else:
            EMAIL_BACKEND = 'django.core.mail.backends.dummy.EmailBackend'

# Ensure the folder exists for file-based email backend.
if EMAIL_BACKEND == 'django.core.mail.backends.filebased.EmailBackend':
    try:
        os.makedirs(EMAIL_FILE_PATH, exist_ok=True)
    except Exception:
        pass

# django-allauth (v65+) settings
# Allow login using either email or username.
# Product onboarding: username is chosen after the welcome popup (Step 1).
ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*']
ACCOUNT_LOGIN_METHODS = {'email', 'username'}

# Remember-me behavior:
# - None: show checkbox on login form
# - When checked: persistent session (uses SESSION_COOKIE_AGE)
# - When unchecked: session expires on browser close
ACCOUNT_SESSION_REMEMBER = None

# Default behavior when the user does NOT check remember-me.
# Allauth will override this per-session when remember-me is checked.
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# Default persistent-session duration (used when remember-me is checked).
# Django's default is 1209600 seconds (14 days). Keep that as default but make it configurable.
SESSION_COOKIE_AGE = int(os.environ.get('SESSION_COOKIE_AGE', '1209600'))

# Allauth email verification (anti-spam)
# - New users must verify email before they can use the account.
ACCOUNT_UNIQUE_EMAIL = True
# Product requirement: allow signup/login without forcing verification immediately.
# Users can manually request verification from settings.
_email_verification_default = 'optional'
ACCOUNT_EMAIL_VERIFICATION = (os.getenv('ACCOUNT_EMAIL_VERIFICATION', _email_verification_default) or _email_verification_default).strip().lower()

# Email subjects should not be prefixed with "[example.com]".
ACCOUNT_EMAIL_SUBJECT_PREFIX = ""

# If True, suppress the automatic verification email sent right after signup.
# Users can still trigger email verification manually from the Email settings page.
ALLAUTH_SUPPRESS_SIGNUP_CONFIRMATION_EMAIL = _env_bool('ALLAUTH_SUPPRESS_SIGNUP_CONFIRMATION_EMAIL', default=True)

# Password reset UX/security:
# - When True, allauth may send an "Unknown Account" email if a user attempts
#   to access/reset using an email that is not registered.
# - Note: this can increase account-enumeration surface (trade-off accepted here
#   because the product wants this email).
ACCOUNT_EMAIL_UNKNOWN_ACCOUNTS = True

# Ensure confirmation links use the correct protocol.
ACCOUNT_DEFAULT_HTTP_PROTOCOL = 'https' if (ENVIRONMENT == 'production' or _using_devtunnel) else 'http'

# Allauth adapter override:
# - Prevents SMTP/network errors from crashing signup/password-reset views.
ACCOUNT_ADAPTER = 'a_users.allauth_adapter.CustomAccountAdapter'
ALLAUTH_FAIL_EMAIL_SILENTLY = _env_bool('ALLAUTH_FAIL_EMAIL_SILENTLY', default=(ENVIRONMENT == 'production'))

# If True, send allauth emails (verification, password reset) in the background
# so signup/login responses are not blocked by slow SMTP.
# Note: if SMTP is misconfigured, users may not receive emails; check logs.
ALLAUTH_ASYNC_EMAIL = _env_bool('ALLAUTH_ASYNC_EMAIL', default=(ENVIRONMENT == 'production'))

# Allauth: use custom styled forms (Tailwind classes)
ACCOUNT_FORMS = {
    'login': 'a_users.allauth_forms.CustomLoginForm',
    'signup': 'a_users.allauth_forms.CustomSignupForm',
    'add_email': 'a_users.allauth_forms.CustomAddEmailForm',
    'reset_password': 'a_users.allauth_forms.CustomResetPasswordForm',
    'reset_password_from_key': 'a_users.allauth_forms.CustomResetPasswordKeyForm',
}

# Allauth rate limits
# NOTE: allauth's built-in rate limiting keys off the client IP. Behind proxies
# (e.g. Render), REMOTE_ADDR can be the proxy IP for all users, causing global
# lockouts like "Too many failed login attempts". We already enforce auth
# throttling via our own RateLimitMiddleware (which honors X-Forwarded-For), so
# disable allauth rate limiting by default in production.
_allauth_rate_limits_enabled_default = False if ENVIRONMENT == 'production' else True
ALLAUTH_RATE_LIMITS_ENABLED = _env_bool('ALLAUTH_RATE_LIMITS_ENABLED', default=_allauth_rate_limits_enabled_default)
if not ALLAUTH_RATE_LIMITS_ENABLED:
    ACCOUNT_RATE_LIMITS = False
else:
    # Optional targeted override, e.g. "10/m/ip,5/300s/key".
    _login_failed_rl = (os.getenv('ACCOUNT_RATE_LIMIT_LOGIN_FAILED', '') or '').strip()
    if _login_failed_rl:
        ACCOUNT_RATE_LIMITS = {
            'login_failed': _login_failed_rl,
        }

# Sentry (Error + Performance Monitoring)
# Enabled only if SENTRY_DSN is set.
SENTRY_DSN = (os.getenv('SENTRY_DSN', '') or '').strip()
SENTRY_TRACES_SAMPLE_RATE = float(os.getenv('SENTRY_TRACES_SAMPLE_RATE', '0.0') or '0.0')
SENTRY_PROFILES_SAMPLE_RATE = float(os.getenv('SENTRY_PROFILES_SAMPLE_RATE', '0.0') or '0.0')

if SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.django import DjangoIntegration

        sentry_sdk.init(
            dsn=SENTRY_DSN,
            environment=ENVIRONMENT,
            integrations=[DjangoIntegration(), CeleryIntegration()],
            send_default_pii=_env_bool('SENTRY_SEND_DEFAULT_PII', default=False),
            traces_sample_rate=max(0.0, min(1.0, SENTRY_TRACES_SAMPLE_RATE)),
            profiles_sample_rate=max(0.0, min(1.0, SENTRY_PROFILES_SAMPLE_RATE)),
        )
    except Exception:
        # Never fail app startup because of monitoring.
        pass


# --- Firebase Cloud Messaging (Web Push) ---
# Public config is safe to expose to the client, but keep server credentials in env only.
FIREBASE_ENABLED = _env_bool('FIREBASE_ENABLED', default=False)
FIREBASE_API_KEY = (os.getenv('FIREBASE_API_KEY', '') or '').strip()
FIREBASE_AUTH_DOMAIN = (os.getenv('FIREBASE_AUTH_DOMAIN', '') or '').strip()
FIREBASE_PROJECT_ID = (os.getenv('FIREBASE_PROJECT_ID', '') or '').strip()
FIREBASE_STORAGE_BUCKET = (os.getenv('FIREBASE_STORAGE_BUCKET', '') or '').strip()
FIREBASE_MESSAGING_SENDER_ID = (os.getenv('FIREBASE_MESSAGING_SENDER_ID', '') or '').strip()
FIREBASE_APP_ID = (os.getenv('FIREBASE_APP_ID', '') or '').strip()
FIREBASE_MEASUREMENT_ID = (os.getenv('FIREBASE_MEASUREMENT_ID', '') or '').strip()

# Web push (VAPID) public key (safe to expose)
FIREBASE_VAPID_PUBLIC_KEY = (os.getenv('FIREBASE_VAPID_PUBLIC_KEY', '') or '').strip()

# Server-side send credentials (secret): provide either raw JSON or base64 JSON.
FIREBASE_SERVICE_ACCOUNT_JSON = (os.getenv('FIREBASE_SERVICE_ACCOUNT_JSON', '') or '').strip()
FIREBASE_SERVICE_ACCOUNT_B64 = (os.getenv('FIREBASE_SERVICE_ACCOUNT_B64', '') or '').strip()