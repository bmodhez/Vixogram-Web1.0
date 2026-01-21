from __future__ import annotations

from django.conf import settings

try:
    from a_users.models import UserReport
except Exception:  # pragma: no cover
    UserReport = None

try:
    from a_users.models import SupportEnquiry
except Exception:  # pragma: no cover
    SupportEnquiry = None


def admin_reports_badge(request):
    """Expose open report count to templates for staff users."""
    try:
        user = getattr(request, 'user', None)
        if not user or not getattr(user, 'is_authenticated', False):
            return {'ADMIN_OPEN_REPORTS': 0, 'ADMIN_OPEN_SUPPORT_ENQUIRIES': 0}
        if not getattr(user, 'is_staff', False):
            return {'ADMIN_OPEN_REPORTS': 0, 'ADMIN_OPEN_SUPPORT_ENQUIRIES': 0}
        if UserReport is None:
            open_reports = 0
        else:
            open_reports = UserReport.objects.filter(status=UserReport.STATUS_OPEN).count()

        if SupportEnquiry is None:
            open_enquiries = 0
        else:
            open_enquiries = SupportEnquiry.objects.filter(status=SupportEnquiry.STATUS_OPEN).count()

        return {
            'ADMIN_OPEN_REPORTS': int(open_reports or 0),
            'ADMIN_OPEN_SUPPORT_ENQUIRIES': int(open_enquiries or 0),
        }
    except Exception:
        return {'ADMIN_OPEN_REPORTS': 0, 'ADMIN_OPEN_SUPPORT_ENQUIRIES': 0}


def mobile_ads_config(request):
    """Expose mobile ads config to templates.

    Rendering rules (scroll/keyboard/typing/etc.) are enforced client-side.
    This server-side gate is only for feature flags + user eligibility.
    """
    try:
        enabled = bool(getattr(settings, 'MOBILE_ADS_ENABLED', False))
        user = getattr(request, 'user', None)

        if not enabled:
            allowed = False
        else:
            allowed = True

        # Easy disables (future-safe)
        if allowed and user and getattr(user, 'is_authenticated', False):
            if bool(getattr(settings, 'MOBILE_ADS_DISABLE_FOR_STAFF', True)) and bool(getattr(user, 'is_staff', False)):
                allowed = False
            # Premium hook (no model field required): if it exists, we respect it.
            try:
                if getattr(user, 'is_premium', False):
                    allowed = False
            except Exception:
                pass
            try:
                profile = getattr(user, 'profile', None)
                if profile is not None and bool(getattr(profile, 'is_premium', False)):
                    allowed = False
            except Exception:
                pass

        # If user is anonymous (shouldn't happen on chat), keep it allowed only if flag is on.
        return {
            'MOBILE_ADS_ENABLED': bool(allowed),
            'MOBILE_AD_CHAT_LIST': {
                'title': getattr(settings, 'MOBILE_AD_CHAT_LIST_TITLE', ''),
                'body': getattr(settings, 'MOBILE_AD_CHAT_LIST_BODY', ''),
                'ctaText': getattr(settings, 'MOBILE_AD_CHAT_LIST_CTA_TEXT', ''),
                'ctaUrl': getattr(settings, 'MOBILE_AD_CHAT_LIST_CTA_URL', ''),
            },
            'MOBILE_AD_CHAT_FEED': {
                'title': getattr(settings, 'MOBILE_AD_CHAT_FEED_TITLE', ''),
                'body': getattr(settings, 'MOBILE_AD_CHAT_FEED_BODY', ''),
                'ctaText': getattr(settings, 'MOBILE_AD_CHAT_FEED_CTA_TEXT', ''),
                'ctaUrl': getattr(settings, 'MOBILE_AD_CHAT_FEED_CTA_URL', ''),
            },
        }
    except Exception:
        return {
            'MOBILE_ADS_ENABLED': False,
            'MOBILE_AD_CHAT_LIST': {},
            'MOBILE_AD_CHAT_FEED': {},
        }
