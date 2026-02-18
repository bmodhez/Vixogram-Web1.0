from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.staticfiles import views as staticfiles_views
from django.views.generic.base import RedirectView
from django.views.generic import TemplateView
from django.templatetags.static import static as static_url
from a_core.firebase_views import firebase_messaging_sw
from a_core.maintenance_views import maintenance_page_view, maintenance_status_view, maintenance_toggle_view
from a_core.security_views import network_security_status_view, network_security_client_report_view
from a_users.allauth_views import CooldownEmailView, WelcomeLoginView, WelcomeSignupView
from a_home.views import pricing_view

# Error handlers (must be module-level).
handler403 = "a_core.error_views.handler403"

urlpatterns = [
    path('favicon.ico', RedirectView.as_view(url=static_url('favicon.png'), permanent=True)),
    path('maintenance/', maintenance_page_view, name='maintenance'),
    path('api/site/maintenance/status/', maintenance_status_view, name='maintenance-status'),
    path('api/site/maintenance/toggle/', maintenance_toggle_view, name='maintenance-toggle'),
    path('api/security/network-status/', network_security_status_view, name='network-security-status'),
    path('api/security/network-client-report/', network_security_client_report_view, name='network-security-client-report'),
    path('admin/', admin.site.urls),
    path('firebase-messaging-sw.js', firebase_messaging_sw, name='firebase-messaging-sw'),
    path('pricing/', pricing_view, name='pricing'),

    # Public footer pages
    path('about/', TemplateView.as_view(template_name='pages/about.html'), name='about'),
    path('contact/', TemplateView.as_view(template_name='pages/contact.html'), name='contact'),
    path('faq/', TemplateView.as_view(template_name='pages/faq.html'), name='faq'),
    path('help/', TemplateView.as_view(template_name='pages/help_center.html'), name='help-center'),
    path('report-abuse/', TemplateView.as_view(template_name='pages/report_abuse.html'), name='report-abuse'),
    path('community-guidelines/', TemplateView.as_view(template_name='pages/community_guidelines.html'), name='community-guidelines'),
    path('privacy/', TemplateView.as_view(template_name='legal/privacy_policy.html'), name='privacy-policy'),
    path('terms/', TemplateView.as_view(template_name='legal/terms_of_service.html'), name='terms-of-service'),
    path('cookies/', TemplateView.as_view(template_name='legal/cookie_policy.html'), name='cookie-policy'),

    path('', include('a_rtchat.urls')),
    path('accounts/login/', WelcomeLoginView.as_view(), name='account_login'),
    path('accounts/signup/', WelcomeSignupView.as_view(), name='account_signup'),
    path('accounts/email/', CooldownEmailView.as_view(), name='account_email'),
    path('accounts/', include('allauth.urls')),
    path('profile/', include('a_users.urls')),
]

# Static/Media in local/dev
# In production, static/media should be served by the platform/CDN.
if getattr(settings, 'ENVIRONMENT', 'development') != 'production':
    # Serve static assets via Django's staticfiles finders.
    # This keeps Django admin assets working (served from site-packages)
    # and also serves app/project static.
    static_prefix = (getattr(settings, 'STATIC_URL', '/static/') or '/static/').lstrip('/')
    urlpatterns += [
        re_path(
            rf'^{static_prefix}(?P<path>.*)$',
            staticfiles_views.serve,
            {'insecure': True},
        ),
    ]

    if getattr(settings, 'MEDIA_URL', None) and getattr(settings, 'MEDIA_ROOT', None):
        urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)