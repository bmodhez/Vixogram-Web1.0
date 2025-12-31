from pathlib import Path
import os
from urllib.parse import urlparse
import dj_database_url

# Optional: load local .env (keeps secrets out of code)
try:
    import environ

    env = environ.Env()
    _env_path = Path(__file__).resolve().parent.parent / '.env'
    if _env_path.exists():
        environ.Env.read_env(str(_env_path))
except Exception:
    # If django-environ isn't installed or .env missing, fall back to normal os.environ
    pass

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


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


ENVIRONMENT = os.environ.get("ENVIRONMENT", "development").strip().lower()

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get(
    "SECRET_KEY",
    "django-insecure-change-me-in-env",
)

# Local/dev should be DEBUG=True so uploads and static/media are easy to debug.
# Production must be DEBUG=False.
if ENVIRONMENT != "production":
    DEBUG = True
else:
    DEBUG = _env_bool("DEBUG", default=False)

_cloud_name = os.environ.get('CLOUD_NAME')
_cloud_key = os.environ.get('API_KEY')
_cloud_secret = os.environ.get('API_SECRET')
_use_cloudinary_media = bool(ENVIRONMENT == 'production' and _cloud_name and _cloud_key and _cloud_secret)

# Django 4.2+ storage configuration
if ENVIRONMENT == 'production':
    STORAGES = {
        'default': {
            'BACKEND': 'cloudinary_storage.storage.MediaCloudinaryStorage' if _use_cloudinary_media else 'django.core.files.storage.FileSystemStorage',
        },
        'staticfiles': {
            'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
        },
    }
else:
    STORAGES = {
        'default': {
            'BACKEND': 'django.core.files.storage.FileSystemStorage',
        },
        'staticfiles': {
            'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
        },
    }

ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    ".onrender.com",
    'vixogram-connect.onrender.com',
    
]

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

CSRF_TRUSTED_ORIGINS = [
    "http://localhost:*",
    "http://127.0.0.1:*",
    'https://vixogram-connect.onrender.com',
    'https://vixogram.onrender.com', # Agar koi aur variant hai toh
]

# Always allow Render subdomains (covers Blueprint/Dashboard setups).
CSRF_TRUSTED_ORIGINS.append("https://*.onrender.com")

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
    'a_home',
    'a_users',
    'a_rtchat',
]

SITE_ID = 1

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'a_users.middleware.ActiveUserRequiredMiddleware',
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
            ],
        },
    },
]

ASGI_APPLICATION = 'a_core.asgi.application'

# Render ya Railway par ye variables environment se uthayenge
REDIS_URL = os.environ.get('REDIS_URL')

# Local/dev: don't depend on Redis (prevents WS disconnects when Redis isn't running).
if os.environ.get('ENVIRONMENT') == 'production' and REDIS_URL:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                'hosts': [REDIS_URL],
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

# Agar Render par ho toh DATABASE_URL use karo, warna local SQLite
if os.environ.get('ENVIRONMENT') == 'production':
    DATABASES = {
        'default': dj_database_url.parse(os.environ.get('DATABASE_URL'))
    }
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
STATICFILES_DIRS = [ BASE_DIR / 'static' ]

# --- Abuse prevention / rate limiting defaults (override via env or settings) ---
# Auth (accounts/* POST)
AUTH_RATE_LIMIT = int(os.environ.get('AUTH_RATE_LIMIT', '25'))
AUTH_RATE_LIMIT_PERIOD = int(os.environ.get('AUTH_RATE_LIMIT_PERIOD', '300'))

# Chat HTTP sends (HTMX)
CHAT_MSG_RATE_LIMIT = int(os.environ.get('CHAT_MSG_RATE_LIMIT', '8'))
CHAT_MSG_RATE_PERIOD = int(os.environ.get('CHAT_MSG_RATE_PERIOD', '10'))

# Room-wide flood protection
ROOM_MSG_RATE_LIMIT = int(os.environ.get('ROOM_MSG_RATE_LIMIT', '30'))
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
CHAT_UPLOAD_LIMIT_PER_ROOM = 20
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
# - Otherwise, fall back to console backend (emails printed in runserver terminal).
# You can override everything via environment variables.
EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', '').strip() or None

EMAIL_HOST_USER = (os.getenv('EMAIL_HOST_USER', '') or '').strip()
EMAIL_HOST_PASSWORD = (os.getenv('EMAIL_HOST_PASSWORD', '') or '').strip()
EMAIL_HOST = (os.getenv('EMAIL_HOST', 'smtp.gmail.com') or 'smtp.gmail.com').strip()
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587') or '587')
EMAIL_USE_TLS = _env_bool('EMAIL_USE_TLS', default=True)
EMAIL_USE_SSL = _env_bool('EMAIL_USE_SSL', default=False)
EMAIL_TIMEOUT = int(os.getenv('EMAIL_TIMEOUT', '20') or '20')

# Avoid empty From: headers.
DEFAULT_FROM_EMAIL = (os.getenv('DEFAULT_FROM_EMAIL', '') or '').strip() or (EMAIL_HOST_USER or 'no-reply@localhost')

if not EMAIL_BACKEND:
    if EMAIL_HOST_USER and EMAIL_HOST_PASSWORD:
        EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    else:
        EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# django-allauth (v65+) settings
# Allow login using either email or username.
ACCOUNT_SIGNUP_FIELDS = ['email*', 'username*', 'password1*', 'password2*']
ACCOUNT_LOGIN_METHODS = {'email', 'username'}

# Remember-me behavior:
# - None: show checkbox on login form
# - When checked: persistent session (uses SESSION_COOKIE_AGE)
# - When unchecked: session expires on browser close
ACCOUNT_SESSION_REMEMBER = None

# Make sure browser-close expiry doesn't override remember-me.
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

# Allauth email verification (anti-spam)
# - New users must verify email before they can use the account.
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_EMAIL_VERIFICATION = 'mandatory'

# Password reset UX/security:
# - Prevent account enumeration (default True), and do not send "unknown account" emails.
#   This avoids confusing users with a signup link when they enter a wrong/unregistered email.
ACCOUNT_EMAIL_UNKNOWN_ACCOUNTS = False

# Ensure confirmation links use the correct protocol.
ACCOUNT_DEFAULT_HTTP_PROTOCOL = 'https' if ENVIRONMENT == 'production' else 'http'

# Allauth: use custom styled forms (Tailwind classes)
ACCOUNT_FORMS = {
    'login': 'a_users.allauth_forms.CustomLoginForm',
    'signup': 'a_users.allauth_forms.CustomSignupForm',
    'reset_password': 'a_users.allauth_forms.CustomResetPasswordForm',
    'reset_password_from_key': 'a_users.allauth_forms.CustomResetPasswordKeyForm',
}