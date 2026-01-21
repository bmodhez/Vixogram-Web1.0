from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve as static_serve
from django.views.generic.base import RedirectView
from django.templatetags.static import static as static_url
from a_core.firebase_views import firebase_messaging_sw
from a_users.allauth_views import CooldownEmailView
from a_home.views import pricing_view

urlpatterns = [
    path('favicon.ico', RedirectView.as_view(url=static_url('favicon.png'), permanent=True)),
    path('admin/', admin.site.urls),
    path('firebase-messaging-sw.js', firebase_messaging_sw, name='firebase-messaging-sw'),
    path('pricing/', pricing_view, name='pricing'),
    path('', include('a_rtchat.urls')),
    path('accounts/email/', CooldownEmailView.as_view(), name='account_email'),
    path('accounts/', include('allauth.urls')),
    path('profile/', include('a_users.urls')),
]

# Static/Media in local/dev
# In production, static/media should be served by the platform/CDN.
if getattr(settings, 'ENVIRONMENT', 'development') != 'production':
    # Serve static even when DEBUG=False (some dev envs set DEBUG=False by mistake).
    static_dirs = list(getattr(settings, 'STATICFILES_DIRS', []) or [])
    static_doc_root = None
    if static_dirs:
        static_doc_root = str(static_dirs[0])
    else:
        # Fallback: assume BASE_DIR/static
        try:
            static_doc_root = str(getattr(settings, 'BASE_DIR') / 'static')
        except Exception:
            static_doc_root = None

    if getattr(settings, 'STATIC_URL', None) and static_doc_root:
        static_prefix = (settings.STATIC_URL or '/static/').lstrip('/')
        urlpatterns += [
            re_path(rf'^{static_prefix}(?P<path>.*)$', static_serve, {'document_root': static_doc_root}),
        ]

    if getattr(settings, 'MEDIA_URL', None) and getattr(settings, 'MEDIA_ROOT', None):
        urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)