import json
import base64
import os
import re
import uuid
import logging
from datetime import timedelta
from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_POST
from django.db.models import Q
from django.core.cache import cache

from .models import Profile, Story, StorySubmission, StoryView, StoryLike, DEFAULT_AVATAR_DATA_URI
from .forms import ProfileForm
from .forms import ReportUserForm
from .forms import ProfilePrivacyForm
from .forms import SupportEnquiryForm
from .forms import UsernameChangeForm
from .forms import OnboardingAvatarForm
from .forms import OnboardingAboutForm
from .forms import StoryForm
from .forms import ProfilePreferredLocationForm
from .location_preferences import clean_location_name, ensure_local_community_membership

try:
    from .story_policy import can_user_add_story, story_upload_locked_message, get_story_max_active
except Exception:  # pragma: no cover
    can_user_add_story = None
    story_upload_locked_message = None
    get_story_max_active = None

try:
    from a_rtchat.rate_limit import check_rate_limit, get_client_ip, make_key
except Exception:  # pragma: no cover
    check_rate_limit = None
    get_client_ip = None
    make_key = None
from django.contrib.auth.models import User
from django.http import HttpResponse
from django.http import JsonResponse
from django.http import Http404
from django.urls import reverse
from django.core import signing
from django.core.files.base import ContentFile
from urllib.parse import urlencode
from django.utils.http import url_has_allowed_host_and_scheme

import requests

from a_users.models import Follow, FollowRequest
from a_users.models import UserReport
from a_users.models import SupportEnquiry
from a_users.models import Referral
from a_users.badges import VERIFIED_FOLLOWERS_THRESHOLD, get_verified_user_ids

try:
    from a_rtchat.models import Notification
except Exception:  # pragma: no cover
    Notification = None


logger = logging.getLogger(__name__)
AVATAR_MAX_BYTES = 500 * 1024


def _avatar_file_exceeds_limit(uploaded_file) -> bool:
    """Return True when uploaded avatar is larger than 500KB.

    Uses both declared size and chunk-byte counting for safety.
    """
    if uploaded_file is None:
        return False

    try:
        declared_size = int(getattr(uploaded_file, 'size', 0) or 0)
        if declared_size > AVATAR_MAX_BYTES:
            return True
    except Exception:
        pass

    try:
        total = 0
        for chunk in uploaded_file.chunks():
            total += len(chunk)
            if total > AVATAR_MAX_BYTES:
                try:
                    uploaded_file.seek(0)
                except Exception:
                    pass
                return True
        try:
            uploaded_file.seek(0)
        except Exception:
            pass
    except Exception:
        # If we cannot inspect file safely, fail closed for security.
        return True

    return False


@login_required
@require_POST
def save_location_view(request):
    """Save a user's last known location (optional permission)."""
    try:
        payload = json.loads((request.body or b'{}').decode('utf-8'))
    except Exception:
        payload = {}

    lat = payload.get('lat')
    lng = payload.get('lng')

    try:
        lat = float(lat)
        lng = float(lng)
    except Exception:
        return JsonResponse({'ok': False, 'error': 'invalid_coords'}, status=400)

    if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
        return JsonResponse({'ok': False, 'error': 'out_of_range'}, status=400)

    def _reverse_geocode_city_country(lat_f: float, lng_f: float) -> tuple[str, str]:
        """Best-effort reverse geocode.

        Uses OpenStreetMap Nominatim. If it fails (network, rate limit, etc),
        return empty strings.
        """
        try:
            lat_r = round(float(lat_f), 3)
            lng_r = round(float(lng_f), 3)
        except Exception:
            return ('', '')

        cache_key = f"vixo:revgeo:{lat_r}:{lng_r}"
        try:
            cached = cache.get(cache_key)
            if isinstance(cached, dict):
                city = str(cached.get('city') or '').strip()
                country = str(cached.get('country') or '').strip()
                if city or country:
                    return (city, country)
        except Exception:
            pass

        try:
            url = "https://nominatim.openstreetmap.org/reverse"
            params = {
                "format": "jsonv2",
                "lat": str(lat_f),
                "lon": str(lng_f),
                "zoom": "10",
                "addressdetails": "1",
            }
            contact = (getattr(settings, 'CONTACT_EMAIL', '') or '').strip()
            ua = "Vixogram/1.0"
            if contact:
                ua = f"{ua} ({contact})"
            resp = requests.get(url, params=params, headers={"User-Agent": ua}, timeout=4)
            if resp.status_code != 200:
                return ('', '')
            data = resp.json() if resp.content else {}
            address = data.get('address') if isinstance(data, dict) else {}
            if not isinstance(address, dict):
                address = {}

            city = (
                address.get('city')
                or address.get('town')
                or address.get('village')
                or address.get('hamlet')
                or address.get('county')
                or address.get('state_district')
                or address.get('state')
                or ''
            )
            country = address.get('country') or ''
            city = str(city or '').strip()
            country = str(country or '').strip()

            try:
                cache.set(cache_key, {'city': city, 'country': country}, 7 * 24 * 3600)
            except Exception:
                pass

            return (city, country)
        except Exception:
            return ('', '')

    try:
        profile = request.user.profile
        # Use Decimal to avoid float rounding surprises with DecimalField.
        profile.last_location_lat = Decimal(str(lat))
        profile.last_location_lng = Decimal(str(lng))
        profile.last_location_at = timezone.now()
        city, country = _reverse_geocode_city_country(lat, lng)
        profile.last_location_city = city or None
        profile.last_location_country = country or None
        profile.save(update_fields=[
            'last_location_lat',
            'last_location_lng',
            'last_location_at',
            'last_location_city',
            'last_location_country',
        ])
    except Exception:
        return JsonResponse({'ok': False, 'error': 'save_failed'}, status=500)

    return JsonResponse({'ok': True})


def _is_user_globally_online(user) -> bool:
    """Best-effort online check for profile presence.

    We treat a user as globally online if they are currently connected to
    the dedicated ChatGroup('online-status') users_online list.
    """
    try:
        from a_rtchat.models import ChatGroup

        if not user:
            return False
        return ChatGroup.objects.filter(group_name='online-status', users_online=user).exists()
    except Exception:
        return False


def location_suggest_view(request):
    if request.method != 'GET':
        return JsonResponse({'results': []}, status=405)

    q = clean_location_name(request.GET.get('q') or '', max_len=120)
    if len(q) < 2:
        return JsonResponse({'results': []})

    cache_key = f"vixo:locsuggest:v2:{q.lower()}"
    try:
        cached = cache.get(cache_key)
        if isinstance(cached, list):
            return JsonResponse({'results': cached})
    except Exception:
        pass

    results = []
    seen = set()

    try:
        url = 'https://nominatim.openstreetmap.org/search'
        params = {
            'q': q,
            'format': 'jsonv2',
            'addressdetails': '1',
            'limit': '12',
        }
        contact = (getattr(settings, 'CONTACT_EMAIL', '') or '').strip()
        user_agent = 'Vixogram/1.0'
        if contact:
            user_agent = f"{user_agent} ({contact})"

        resp = requests.get(url, params=params, headers={'User-Agent': user_agent}, timeout=4)
        if resp.status_code == 200:
            payload = resp.json() if resp.content else []
        else:
            payload = []
    except Exception:
        payload = []

    for row in payload if isinstance(payload, list) else []:
        if not isinstance(row, dict):
            continue
        address = row.get('address') if isinstance(row.get('address'), dict) else {}

        city = clean_location_name(
            address.get('city')
            or address.get('town')
            or address.get('village')
            or address.get('hamlet')
            or address.get('county')
            or address.get('state_district')
            or ''
        )
        state = clean_location_name(address.get('state') or address.get('state_district') or '')
        country = clean_location_name(address.get('country') or '')

        # Nominatim often returns region/state records without a city key
        # (e.g. "Tamil Nadu"). Allow those as selectable location values.
        if not city and state:
            city = state
            state = ''
        elif city and state and city.lower() == state.lower():
            state = ''

        if not city:
            continue

        label_parts = [part for part in [city, state, country] if part]
        label = ', '.join(label_parts)
        key = (city.lower(), state.lower(), country.lower())
        if key in seen:
            continue
        seen.add(key)
        results.append({
            'label': label,
            'city': city,
            'state': state,
            'country': country,
        })

    try:
        cache.set(cache_key, results, 24 * 3600)
    except Exception:
        pass

    return JsonResponse({'results': results})


def _has_verified_email(user) -> bool:
    try:
        if not getattr(user, 'is_authenticated', False):
            return False
        if getattr(user, 'is_staff', False):
            return True
        qs = getattr(user, 'emailaddress_set', None)
        if qs is None:
            return False
        return qs.filter(verified=True).exists()
    except Exception:
        return False

def profile_view(request, username=None):
    if username:
        # Kisi aur ki profile dekh rahe hain
        profile_user = get_object_or_404(User, username=username)
        user_profile = profile_user.profile
    else:
        # Apni profile dekh rahe hain
        if not request.user.is_authenticated:
            return redirect('account_login')
        profile_user = request.user
        user_profile = request.user.profile

    followers_count = Follow.objects.filter(following=profile_user).count()
    following_count = Follow.objects.filter(follower=profile_user).count()
    is_verified_badge = bool(getattr(profile_user, 'is_superuser', False) or (followers_count >= VERIFIED_FOLLOWERS_THRESHOLD))

    is_following = False
    is_follow_requested = False
    follows_you = False
    if request.user.is_authenticated and request.user != profile_user:
        is_following = Follow.objects.filter(follower=request.user, following=profile_user).exists()
        follows_you = Follow.objects.filter(follower=profile_user, following=request.user).exists()
        try:
            is_follow_requested = FollowRequest.objects.filter(from_user=request.user, to_user=profile_user).exists()
        except Exception:
            is_follow_requested = False

    viewer_verified = _has_verified_email(getattr(request, 'user', None))
    is_owner = bool(request.user.is_authenticated and request.user == profile_user)
    is_private = bool(getattr(user_profile, 'is_private_account', False))
    is_founder_effective = bool(
        getattr(user_profile, 'is_founder_club', False)
        or getattr(profile_user, 'is_superuser', False)
    )

    # Presence visibility
    is_bot = bool(getattr(user_profile, 'is_bot', False))
    is_stealth = bool(getattr(user_profile, 'is_stealth', False))
    is_dnd = bool(getattr(user_profile, 'is_dnd', False))
    show_presence = bool(not is_bot)
    visible_online = False
    try:
        if show_presence:
            # Owner should see themselves as online immediately (page load)
            # even before the websocket updates the global presence list.
            if is_owner and request.user.is_authenticated:
                visible_online = True
            else:
                actually_online = _is_user_globally_online(profile_user)
                # Stealth: show offline to everyone except owner.
                visible_online = bool(actually_online and (is_owner or not is_stealth))
    except Exception:
        visible_online = False

    # Follow lists visibility rules:
    # - Owner: always.
    # - Private accounts: followers can view after request is accepted.
    # - Public accounts: keep the verified-email gate.
    show_follow_lists = bool(is_owner or is_following or (viewer_verified and (not is_private)))
    follow_lists_locked_reason = ''

    if not show_follow_lists:
        if request.user.is_authenticated and is_private and (not is_owner) and (not is_following):
            follow_lists_locked_reason = 'This acc is private. You cannot view following/followers unless the user accepts your request'
        elif not request.user.is_authenticated:
            follow_lists_locked_reason = 'Login and verify your email to view followers/following.'
        elif not viewer_verified:
            follow_lists_locked_reason = 'Verify your email to view followers/following.'
        else:
            follow_lists_locked_reason = 'Followers & Following are locked right now.'
    
    # Stories visibility: private accounts -> only owner or followers.
    has_active_stories = False
    active_story_version = ''
    can_view_stories = bool((not is_private) or is_owner or is_following)
    if can_view_stories:
        try:
            now = timezone.now()
            legacy_cutoff = now - timedelta(hours=int(getattr(Story, 'TTL_HOURS', 24)))
            active_qs = (
                Story.objects
                .filter(user=profile_user)
                .filter(
                    Q(expires_at__gt=now)
                    | Q(expires_at__isnull=True, created_at__gte=legacy_cutoff)
                )
            )
            has_active_stories = active_qs.exists()
            if has_active_stories:
                latest = active_qs.order_by('-created_at').values_list('created_at', flat=True).first()
                if latest:
                    try:
                        active_story_version = latest.isoformat()
                    except Exception:
                        active_story_version = str(latest)
        except Exception:
            has_active_stories = False
            active_story_version = ''
        
    ctx = {
        'profile': user_profile,
        'profile_user': profile_user,
        'is_founder_effective': is_founder_effective,
        'followers_count': followers_count,
        'following_count': following_count,
        'is_verified_badge': is_verified_badge,
        'is_following': is_following,
        'follows_you': bool(follows_you),
        'is_follow_requested': bool(is_follow_requested),
        'show_follow_lists': show_follow_lists,
        'follow_lists_locked_reason': follow_lists_locked_reason,
        'is_owner': is_owner,
        'is_private': is_private,
        'show_presence': show_presence,
        'presence_online': visible_online,
        'presence_is_dnd': bool(is_dnd),
        'has_active_stories': bool(has_active_stories),
        'can_view_stories': bool(can_view_stories),
        'active_story_version': str(active_story_version or ''),
    }

    # JS config for realtime presence (used by static/js/profile.js)
    try:
        ctx['profile_config'] = {
            'profileUsername': getattr(profile_user, 'username', ''),
            'isOwner': bool(is_owner),
            'presenceOnline': bool(visible_online),
            'presenceIsDnd': bool(is_dnd),
            'presenceWsEnabled': bool(show_presence and (is_owner or not is_stealth)),
        }
    except Exception:
        ctx['profile_config'] = {
            'profileUsername': getattr(profile_user, 'username', ''),
            'isOwner': bool(is_owner),
            'presenceOnline': bool(visible_online),
            'presenceIsDnd': bool(is_dnd),
            'presenceWsEnabled': False,
        }

    # If opened from chat (HTMX), render a lightweight modal fragment instead of a full page.
    is_htmx = (request.headers.get('HX-Request') == 'true') or (request.META.get('HTTP_HX_REQUEST') == 'true')
    if is_htmx and request.GET.get('modal') == '1':
        return render(request, 'a_users/partials/profile_modal.html', ctx)

    return render(request, 'a_users/profile.html', ctx)


def user_stories_json_view(request, username: str):
    """Return active stories for a user.

    - Images only.
    - Viewer duration is fixed (10s/story) in JS; we return it here too.
    - Private accounts: only owner or followers can view.
    """
    profile_user = get_object_or_404(User, username=username)
    profile = getattr(profile_user, 'profile', None)

    is_owner = bool(request.user.is_authenticated and request.user == profile_user)
    is_private = bool(getattr(profile, 'is_private_account', False))

    is_admin = False
    try:
        is_admin = bool(request.user.is_authenticated and (getattr(request.user, 'is_staff', False) or getattr(request.user, 'is_superuser', False)))
    except Exception:
        is_admin = False

    is_following = False
    if request.user.is_authenticated and (not is_owner):
        try:
            is_following = Follow.objects.filter(follower=request.user, following=profile_user).exists()
        except Exception:
            is_following = False

    if is_private and not (is_owner or is_following or is_admin):
        return JsonResponse({'detail': 'Private account'}, status=403)

    now = timezone.now()

    def cleanup_expired_for(user_obj):
        """Best-effort cleanup so expired stories don't linger."""
        try:
            cutoff = now - timedelta(hours=getattr(Story, 'TTL_HOURS', 24))
            expired_qs = (
                Story.objects
                .filter(user=user_obj)
                .filter(
                    Q(expires_at__lte=now)
                    | Q(expires_at__isnull=True, created_at__lt=cutoff)
                )
            )
            for s in expired_qs[:200]:
                try:
                    s.delete()
                except Exception:
                    pass
        except Exception:
            pass

    # Auto-delete expired stories (lazy cleanup).
    cleanup_expired_for(profile_user)

    # If expires_at is missing (legacy/edge), treat it as a 24h story.
    legacy_cutoff = now - timedelta(hours=getattr(Story, 'TTL_HOURS', 24))
    qs = (
        Story.objects
        .filter(user=profile_user)
        .filter(
            Q(expires_at__isnull=True, created_at__gte=legacy_cutoff)
            | Q(expires_at__gt=now)
        )
        .order_by('created_at')
    )

    liked_story_ids = set()
    like_counts = {}
    try:
        story_ids = [int(getattr(s, 'id', 0) or 0) for s in qs[:40]]
        story_ids = [sid for sid in story_ids if sid > 0]
        if request.user.is_authenticated and story_ids:
            liked_story_ids = set(
                StoryLike.objects.filter(story_id__in=story_ids, user=request.user).values_list('story_id', flat=True)
            )
        if story_ids:
            from django.db.models import Count

            for row in StoryLike.objects.filter(story_id__in=story_ids).values('story_id').annotate(c=Count('id')):
                like_counts[int(row.get('story_id') or 0)] = int(row.get('c') or 0)
    except Exception:
        liked_story_ids = set()
        like_counts = {}

    stories = []
    for s in qs[:40]:
        try:
            url = s.image.url
        except Exception:
            url = ''
        if not url:
            continue
        stories.append({
            'id': int(s.id),
            'image_url': url,
            'created_at': s.created_at.isoformat() if getattr(s, 'created_at', None) else None,
            'expires_at': s.expires_at.isoformat() if getattr(s, 'expires_at', None) else None,
            'liked_by_me': bool(int(s.id) in liked_story_ids),
            'likes_count': int(like_counts.get(int(s.id), 0)),
        })

    res = JsonResponse({
        'username': profile_user.username,
        'is_owner': bool(is_owner),
        'can_delete': bool(is_owner or is_admin),
        'duration_seconds': int(getattr(Story, 'DURATION_SECONDS', 10)),
        'count': len(stories),
        'stories': stories,
    })
    try:
        res['Cache-Control'] = 'no-store'
    except Exception:
        pass
    return res


@login_required
@require_POST
def story_seen_view(request, story_id: int):
    """Mark a story as seen by the current user (best-effort)."""
    story = get_object_or_404(Story, id=story_id)

    # Don't record self-views.
    try:
        if getattr(story, 'user_id', None) == getattr(request.user, 'id', None):
            return JsonResponse({'ok': True})
    except Exception:
        pass

    owner = getattr(story, 'user', None)
    owner_profile = getattr(owner, 'profile', None) if owner else None

    is_admin = False
    try:
        is_admin = bool(getattr(request.user, 'is_staff', False) or getattr(request.user, 'is_superuser', False))
    except Exception:
        is_admin = False

    is_private = bool(getattr(owner_profile, 'is_private_account', False))
    if is_private and not is_admin:
        # Only followers can view private stories.
        is_following = False
        try:
            is_following = Follow.objects.filter(follower=request.user, following=owner).exists()
        except Exception:
            is_following = False
        if not is_following:
            return JsonResponse({'detail': 'Private account'}, status=403)

    try:
        obj, created = StoryView.objects.get_or_create(story=story, viewer=request.user)
        if not created:
            obj.last_seen = timezone.now()
            obj.save(update_fields=['last_seen'])
    except Exception:
        # Best-effort; don't break story playback.
        pass

    res = JsonResponse({'ok': True})
    try:
        res['Cache-Control'] = 'no-store'
    except Exception:
        pass
    return res


@login_required
@require_POST
def story_like_toggle_view(request, story_id: int):
    """Toggle like for a story by the current user."""
    story = get_object_or_404(Story, id=story_id)

    owner = getattr(story, 'user', None)
    owner_profile = getattr(owner, 'profile', None) if owner else None

    is_admin = False
    try:
        is_admin = bool(getattr(request.user, 'is_staff', False) or getattr(request.user, 'is_superuser', False))
    except Exception:
        is_admin = False

    is_private = bool(getattr(owner_profile, 'is_private_account', False))
    if is_private and not is_admin:
        is_owner = bool(getattr(story, 'user_id', None) == getattr(request.user, 'id', None))
        is_following = False
        if not is_owner:
            try:
                is_following = Follow.objects.filter(follower=request.user, following=owner).exists()
            except Exception:
                is_following = False
        if not (is_owner or is_following):
            return JsonResponse({'detail': 'Private account'}, status=403)

    liked = False
    try:
        obj, created = StoryLike.objects.get_or_create(story=story, user=request.user)
        if created:
            liked = True
        else:
            obj.delete()
            liked = False
    except Exception:
        return JsonResponse({'detail': 'Could not update like'}, status=400)

    try:
        likes_count = int(StoryLike.objects.filter(story=story).count())
    except Exception:
        likes_count = 0

    res = JsonResponse({'ok': True, 'liked': bool(liked), 'likes_count': int(likes_count)})
    try:
        res['Cache-Control'] = 'no-store'
    except Exception:
        pass
    return res


@login_required
def story_viewers_json_view(request, story_id: int):
    """Return the viewers list for a story.

    Only the story owner (or staff/superuser) can fetch this.
    """
    story = get_object_or_404(Story, id=story_id)

    is_admin = False
    try:
        is_admin = bool(getattr(request.user, 'is_staff', False) or getattr(request.user, 'is_superuser', False))
    except Exception:
        is_admin = False

    is_owner = bool(getattr(story, 'user_id', None) == getattr(request.user, 'id', None))
    if not (is_owner or is_admin):
        return JsonResponse({'detail': 'Forbidden'}, status=403)

    # Pagination
    # - Default limit = 50
    # - Cursor is the last item of the previous page: (last_seen, id)
    # Query params:
    #   ?limit=50&cursor=<iso_datetime>&cursor_id=<int>
    try:
        limit = int(request.GET.get('limit') or 50)
    except Exception:
        limit = 50
    limit = max(1, min(100, limit))

    cursor_raw = (request.GET.get('cursor') or '').strip()
    cursor_id_raw = (request.GET.get('cursor_id') or '').strip()

    cursor_dt = None
    cursor_id = None
    if cursor_raw:
        try:
            cursor_dt = parse_datetime(cursor_raw)
            if cursor_dt and timezone.is_naive(cursor_dt):
                cursor_dt = timezone.make_aware(cursor_dt, timezone.get_current_timezone())
        except Exception:
            cursor_dt = None
    if cursor_id_raw:
        try:
            cursor_id = int(cursor_id_raw)
        except Exception:
            cursor_id = None

    liked_viewer_ids = set()
    try:
        liked_viewer_ids = set(StoryLike.objects.filter(story=story).values_list('user_id', flat=True))
    except Exception:
        liked_viewer_ids = set()

    viewers = []
    has_more = False
    next_cursor = None
    next_cursor_id = None

    try:
        qs = (
            StoryView.objects
            .filter(story=story)
            .select_related('viewer', 'viewer__profile')
            .order_by('-last_seen', '-id')
        )

        if cursor_dt is not None:
            # Fetch items strictly older than the cursor.
            if cursor_id is not None:
                qs = qs.filter(Q(last_seen__lt=cursor_dt) | (Q(last_seen=cursor_dt) & Q(id__lt=cursor_id)))
            else:
                qs = qs.filter(last_seen__lt=cursor_dt)

        rows = list(qs[: limit + 1])
        if len(rows) > limit:
            has_more = True
            rows = rows[:limit]

        if rows:
            last = rows[-1]
            try:
                next_cursor = last.last_seen.isoformat() if getattr(last, 'last_seen', None) else None
            except Exception:
                next_cursor = None
            try:
                next_cursor_id = int(last.id)
            except Exception:
                next_cursor_id = None

        for row in rows:
            u = getattr(row, 'viewer', None)
            if not u:
                continue
            p = getattr(u, 'profile', None)
            try:
                avatar = getattr(p, 'avatar', None) if p else None
            except Exception:
                avatar = None
            if not avatar:
                try:
                    avatar = DEFAULT_AVATAR_DATA_URI
                except Exception:
                    avatar = ''

            viewers.append({
                'username': getattr(u, 'username', ''),
                'displayname': getattr(p, 'name', None) if p else None,
                'avatar': avatar,
                'liked': bool(getattr(u, 'id', None) in liked_viewer_ids),
            })
    except Exception:
        viewers = []
        has_more = False
        next_cursor = None
        next_cursor_id = None

    res = JsonResponse({
        'count': len(viewers),
        'viewers': viewers,
        'has_more': bool(has_more),
        'next_cursor': next_cursor,
        'next_cursor_id': next_cursor_id,
        'limit': limit,
    })
    try:
        res['Cache-Control'] = 'no-store'
    except Exception:
        pass
    return res


@login_required
@require_POST
def story_delete_view(request, story_id: int):
    """Delete a story.

    Only the story owner (or staff/superuser) may delete.
    """
    story = get_object_or_404(Story, id=story_id)

    is_admin = False
    try:
        is_admin = bool(getattr(request.user, 'is_staff', False) or getattr(request.user, 'is_superuser', False))
    except Exception:
        is_admin = False

    if story.user_id != getattr(request.user, 'id', None) and not is_admin:
        return JsonResponse({'detail': 'Forbidden'}, status=403)

    try:
        story.delete()
    except Exception:
        return JsonResponse({'detail': 'Failed to delete'}, status=400)

    max_active = 1
    try:
        if callable(get_story_max_active):
            max_active = int(get_story_max_active() or 1)
    except Exception:
        max_active = 1

    active_count = 0
    try:
        now = timezone.now()
        cutoff = now - timedelta(hours=int(getattr(Story, 'TTL_HOURS', 24) or 24))
        active_count = int(
            Story.objects
            .filter(user=request.user)
            .filter(
                Q(expires_at__gt=now)
                | Q(expires_at__isnull=True, created_at__gte=cutoff)
            )
            .count()
        )
    except Exception:
        active_count = 0

    can_add_story = bool(active_count < max_active)
    limit_msg = (
        'Free plan limited to 1 story. Delete your current story to add a new one.'
        if int(max_active or 1) == 1
        else f'You can put only {max_active} stories.'
    )

    res = JsonResponse({
        'ok': True,
        'story_upload': {
            'can_add_story': can_add_story,
            'active_count': int(active_count or 0),
            'max_active': int(max_active or 1),
            'limit_message': str(limit_msg),
        },
    })
    try:
        res['Cache-Control'] = 'no-store'
    except Exception:
        pass
    return res


@login_required
def story_add_view(request):
    """Create a new story for the current user (image-only)."""
    now = timezone.now()

    is_htmx = (request.headers.get('HX-Request') == 'true') or (request.META.get('HTTP_HX_REQUEST') == 'true')
    is_modal = bool(request.GET.get('modal') == '1')

    # Opportunistic cleanup for the current user.
    try:
        cutoff = now - timedelta(hours=getattr(Story, 'TTL_HOURS', 24))
        expired_qs = (
            Story.objects
            .filter(user=request.user)
            .filter(
                Q(expires_at__lte=now)
                | Q(expires_at__isnull=True, created_at__lt=cutoff)
            )
        )
        for s in expired_qs[:200]:
            try:
                s.delete()
            except Exception:
                pass
    except Exception:
        pass

    def _active_story_count() -> int:
        """Active = not expired (or missing expires_at but within TTL window)."""
        try:
            cutoff = now - timedelta(hours=getattr(Story, 'TTL_HOURS', 24))
            return int(
                Story.objects
                .filter(user=request.user)
                .filter(
                    Q(expires_at__gt=now)
                    | Q(expires_at__isnull=True, created_at__gte=cutoff)
                )
                .count()
            )
        except Exception:
            return 0

    max_active = 1
    try:
        if callable(get_story_max_active):
            max_active = int(get_story_max_active() or 1)
    except Exception:
        max_active = 1

    limit_msg = (
        'Only 1 active story is allowed. Uploading a new story will replace your previous one.'
        if int(max_active or 1) == 1
        else f'You can put only {max_active} stories.'
    )

    def _delete_existing_active_stories() -> None:
        """For single-story plans, keep only the newest upload by removing active older stories."""
        try:
            cutoff = now - timedelta(hours=getattr(Story, 'TTL_HOURS', 24))
            active_qs = (
                Story.objects
                .filter(user=request.user)
                .filter(
                    Q(expires_at__gt=now)
                    | Q(expires_at__isnull=True, created_at__gte=cutoff)
                )
            )
            for s in active_qs[:200]:
                try:
                    s.delete()
                except Exception:
                    pass
        except Exception:
            pass

    if int(max_active or 1) > 1 and _active_story_count() >= max_active:
        msg = limit_msg
        if is_htmx and is_modal:
            # User clicked "Add Story" from menu: show popup and close.
            return HttpResponse(
                f"""
                <div></div>
                <script>
                  try {{
                    document.body.dispatchEvent(new CustomEvent('vixo:toast', {{ detail: {{ message: {msg!r}, kind: 'error', durationMs: 3000 }} }}));
                  }} catch (e) {{}}
                  try {{ document.body.dispatchEvent(new Event('vixo:closeGlobalModal')); }} catch (e) {{}}
                </script>
                """.strip()
            )
        messages.error(request, msg)
        return redirect('profile')

    if request.method == 'POST':
        files = request.FILES
        # If client provided a cropped data URL, prefer it over the raw file.
        try:
            cropped = (request.POST.get('cropped_image_data') or '').strip()
            if cropped.startswith('data:image/') and ';base64,' in cropped:
                m = re.match(r'^data:(image/[a-zA-Z0-9.+-]+);base64,(.*)$', cropped)
                if m:
                    mime = (m.group(1) or '').lower()
                    b64 = (m.group(2) or '').strip()
                    raw = base64.b64decode(b64)
                    ext = {
                        'image/jpeg': 'jpg',
                        'image/jpg': 'jpg',
                        'image/png': 'png',
                        'image/webp': 'webp',
                    }.get(mime, 'jpg')
                    f = ContentFile(raw, name=f"story_{uuid.uuid4().hex}.{ext}")
                    files = request.FILES.copy()
                    files['image'] = f
        except Exception:
            files = request.FILES

        form = StoryForm(request.POST, files)
        if form.is_valid():
            if int(max_active or 1) > 1 and _active_story_count() >= max_active:
                msg = limit_msg
                try:
                    form.add_error(None, msg)
                except Exception:
                    pass

                if is_htmx and is_modal:
                    ctx = {
                        'form': form,
                        'duration_seconds': int(getattr(Story, 'DURATION_SECONDS', 10)),
                        'ttl_hours': int(getattr(Story, 'TTL_HOURS', 24)),
                    }
                    resp = render(request, 'a_users/partials/story_add_modal.html', ctx)
                    try:
                        extra = f"""
                        <script>
                          try {{
                            document.body.dispatchEvent(new CustomEvent('vixo:toast', {{ detail: {{ message: {msg!r}, kind: 'error', durationMs: 3000 }} }}));
                          }} catch (e) {{}}
                        </script>
                        """.strip().encode('utf-8')
                    except Exception:
                        extra = b''
                    return HttpResponse(resp.content + extra)

                messages.error(request, msg)
                return redirect('profile')

            uploaded_story = form.cleaned_data.get('image')
            if not uploaded_story:
                msg = 'Please choose an image.'
                if is_htmx and is_modal:
                    ctx = {
                        'form': form,
                        'duration_seconds': int(getattr(Story, 'DURATION_SECONDS', 10)),
                        'ttl_hours': int(getattr(Story, 'TTL_HOURS', 24)),
                    }
                    resp = render(request, 'a_users/partials/story_add_modal.html', ctx)
                    try:
                        extra = f"""
                        <script>
                          try {{
                            document.body.dispatchEvent(new CustomEvent('vixo:toast', {{ detail: {{ message: {msg!r}, kind: 'error', durationMs: 3000 }} }}));
                          }} catch (e) {{}}
                        </script>
                        """.strip().encode('utf-8')
                    except Exception:
                        extra = b''
                    return HttpResponse(resp.content + extra)
                messages.error(request, msg)
                return redirect('profile')

            try:
                pending_dir = os.path.join(settings.BASE_DIR, 'media', 'pending_stories')
                os.makedirs(pending_dir, exist_ok=True)
                ext = os.path.splitext(str(getattr(uploaded_story, 'name', '') or ''))[1].lower() or '.jpg'
                filename = f'story_pending_{request.user.id}_{uuid.uuid4().hex[:10]}{ext}'
                pending_path = os.path.join(pending_dir, filename)

                with open(pending_path, 'wb') as fh:
                    if hasattr(uploaded_story, 'chunks'):
                        for chunk in uploaded_story.chunks():
                            fh.write(chunk)
                    else:
                        fh.write(uploaded_story.read())

                try:
                    if hasattr(uploaded_story, 'seek'):
                        uploaded_story.seek(0)
                except Exception:
                    pass

                StorySubmission.objects.create(
                    user=request.user,
                    pending_local=pending_path,
                    review_status='pending',
                )
            except Exception:
                logger.exception('Story submission queue write failed for user_id=%s', getattr(request.user, 'id', None))
                msg = 'Could not submit story right now. Please try again in a moment.'
                if is_htmx and is_modal:
                    ctx = {
                        'form': form,
                        'duration_seconds': int(getattr(Story, 'DURATION_SECONDS', 10)),
                        'ttl_hours': int(getattr(Story, 'TTL_HOURS', 24)),
                    }
                    resp = render(request, 'a_users/partials/story_add_modal.html', ctx)
                    try:
                        extra = f"""
                        <script>
                          try {{
                            document.body.dispatchEvent(new CustomEvent('vixo:toast', {{ detail: {{ message: {msg!r}, kind: 'error', durationMs: 3200 }} }}));
                          }} catch (e) {{}}
                        </script>
                        """.strip().encode('utf-8')
                    except Exception:
                        extra = b''
                    return HttpResponse(resp.content + extra)
                messages.error(request, msg)
                return redirect('profile')

            if is_htmx and is_modal:
                # Close modal + show toast without page navigation.
                return HttpResponse(
                    """
                    <div></div>
                    <script>
                      try {
                        document.body.dispatchEvent(new CustomEvent('vixo:toast', { detail: { message: 'Story submitted for review.', kind: 'success', durationMs: 2500 } }));
                      } catch (e) {}
                      try { document.body.dispatchEvent(new Event('vixo:closeGlobalModal')); } catch (e) {}
                    </script>
                    """.strip()
                )
            messages.success(request, 'Story submitted for review. It will appear after Vixo Team approval.')
            return redirect('profile')
    else:
        form = StoryForm()

    ctx = {
        'form': form,
        'duration_seconds': int(getattr(Story, 'DURATION_SECONDS', 10)),
        'ttl_hours': int(getattr(Story, 'TTL_HOURS', 24)),

    }

    # HTMX modal: render fragment into global modal root.
    if is_htmx and is_modal:
        return render(request, 'a_users/partials/story_add_modal.html', ctx)

    return render(request, 'a_users/story_add.html', ctx)


@login_required
def profile_config_view(request, username=None):
    """Return JSON config for the profile page (consumed by static JS)."""
    if username:
        profile_user = get_object_or_404(User, username=username)
    else:
        profile_user = request.user

    is_owner = bool(request.user.is_authenticated and request.user == profile_user)
    user_profile = getattr(profile_user, 'profile', None)
    is_bot = bool(getattr(user_profile, 'is_bot', False))
    is_stealth = bool(getattr(user_profile, 'is_stealth', False))
    is_dnd = bool(getattr(user_profile, 'is_dnd', False))
    show_presence = bool(not is_bot)

    visible_online = False
    try:
        if show_presence:
            if is_owner and request.user.is_authenticated:
                visible_online = True
            else:
                actually_online = _is_user_globally_online(profile_user)
                visible_online = bool(actually_online and (is_owner or not is_stealth))
    except Exception:
        visible_online = False

    presence_ws_enabled = bool(show_presence and (is_owner or not is_stealth))

    return JsonResponse({
        'profileUsername': profile_user.username,
        'isOwner': is_owner,
        'showPresence': show_presence,
        'presenceOnline': visible_online,
        'presenceIsDnd': bool(is_dnd),
        'presenceWsEnabled': presence_ws_enabled,
    })


@login_required
def contact_support_view(request):
    topic = (request.GET.get('topic') or '').strip().lower()

    if request.method == 'POST':
        form = SupportEnquiryForm(request.POST)
        if form.is_valid():
            enquiry = form.save(commit=False)
            enquiry.user = request.user
            try:
                enquiry.page = (request.POST.get('page') or request.META.get('HTTP_REFERER') or request.path)[:300]
            except Exception:
                enquiry.page = request.path
            try:
                enquiry.user_agent = (request.META.get('HTTP_USER_AGENT') or '')[:300]
            except Exception:
                enquiry.user_agent = ''
            enquiry.save()
            messages.success(request, 'Sent to support. We will get back to you soon.')
            # After sending, take the user straight back to where they came from
            # (typically the chat screen). Prevent open-redirects by validating host.
            next_url = (request.POST.get('page') or '').strip()
            if next_url and url_has_allowed_host_and_scheme(
                url=next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                return redirect(next_url)
            return redirect('home')
    else:
        if topic == 'premium':
            messages.info(request, 'Premium is not available yet.')
            form = SupportEnquiryForm(initial={
                'subject': 'Premium upgrade',
            })
        else:
            form = SupportEnquiryForm()

    enquiries = []
    try:
        enquiries = list(
            SupportEnquiry.objects.filter(user=request.user).order_by('-created_at')[:8]
        )
    except Exception:
        enquiries = []

    return render(request, 'a_users/contact_support.html', {
        'form': form,
        'enquiries': enquiries,
    })


@login_required
def invite_friends_view(request):
    """Invite page with a signed, shareable link."""
    token = signing.dumps(
        {'u': int(getattr(request.user, 'id', 0))},
        salt='invite-friends',
        compress=True,
    )
    signup_path = reverse('account_signup')
    invite_url = request.build_absolute_uri(f"{signup_path}?{urlencode({'ref': token})}")

    points = 0
    try:
        points = int(getattr(getattr(request.user, 'profile', None), 'referral_points', 0) or 0)
    except Exception:
        points = 0

    verified_invites = 0
    try:
        verified_invites = int(
            Referral.objects.filter(referrer=request.user, awarded_at__isnull=False).count()
        )
    except Exception:
        verified_invites = 0

    required_points = int(getattr(settings, 'FOUNDER_CLUB_REQUIRED_POINTS', 450) or 450)
    required_invites = int(getattr(settings, 'FOUNDER_CLUB_REQUIRED_INVITES', 35) or 35)
    min_age_days = int(getattr(settings, 'FOUNDER_CLUB_MIN_ACCOUNT_AGE_DAYS', 20) or 20)

    now = timezone.now()
    try:
        account_age_days = int((now - request.user.date_joined).days)
    except Exception:
        account_age_days = 0

    profile = getattr(request.user, 'profile', None)
    is_founder = bool(getattr(profile, 'is_founder_club', False))
    reapply_at = getattr(profile, 'founder_club_reapply_available_at', None)
    can_reapply = True
    if reapply_at:
        try:
            can_reapply = bool(now >= reapply_at)
        except Exception:
            can_reapply = True

    meets_points = points >= required_points
    meets_invites = verified_invites >= required_invites
    meets_age = account_age_days >= min_age_days
    can_apply = bool((not is_founder) and can_reapply and meets_points and meets_invites and meets_age)

    return render(request, 'a_users/invite_friends.html', {
        'invite_url': invite_url,
        'points': points,
        'verified_invites': verified_invites,
        'required_points': required_points,
        'required_invites': required_invites,
        'min_account_age_days': min_age_days,
        'account_age_days': account_age_days,
        'is_founder_club': is_founder,
        'founder_reapply_at': reapply_at,
        'founder_can_apply': can_apply,
        'founder_meets_points': meets_points,
        'founder_meets_invites': meets_invites,
        'founder_meets_age': meets_age,
    })


@login_required
def founder_club_apply_view(request):
    """Apply for Founder Club once eligibility is reached."""
    profile = getattr(request.user, 'profile', None)
    if profile is None:
        raise Http404()

    now = timezone.now()
    required_points = int(getattr(settings, 'FOUNDER_CLUB_REQUIRED_POINTS', 450) or 450)
    required_invites = int(getattr(settings, 'FOUNDER_CLUB_REQUIRED_INVITES', 35) or 35)
    min_age_days = int(getattr(settings, 'FOUNDER_CLUB_MIN_ACCOUNT_AGE_DAYS', 20) or 20)

    points = int(getattr(profile, 'referral_points', 0) or 0)
    try:
        verified_invites = int(
            Referral.objects.filter(referrer=request.user, awarded_at__isnull=False).count()
        )
    except Exception:
        verified_invites = 0

    try:
        account_age_days = int((now - request.user.date_joined).days)
    except Exception:
        account_age_days = 0

    meets_points = points >= required_points
    meets_invites = verified_invites >= required_invites
    meets_age = account_age_days >= min_age_days

    reapply_at = getattr(profile, 'founder_club_reapply_available_at', None)
    can_reapply = True
    if reapply_at:
        try:
            can_reapply = bool(now >= reapply_at)
        except Exception:
            can_reapply = True

    eligible = bool(meets_points and meets_invites and meets_age and can_reapply)

    if getattr(profile, 'is_founder_club', False):
        messages.info(request, 'Founder Club is already active on your account.')
        return redirect('invite-friends')

    if request.method == 'POST':
        if not eligible:
            messages.error(request, 'Not eligible for Founder Club yet.')
            return redirect('invite-friends')

        # Grant immediately when the user submits the form.
        today = timezone.localdate()
        profile.is_founder_club = True
        profile.founder_club_granted_at = now
        profile.founder_club_revoked_at = None
        profile.founder_club_reapply_available_at = None
        profile.founder_club_last_checked = today
        profile.save(update_fields=[
            'is_founder_club',
            'founder_club_granted_at',
            'founder_club_revoked_at',
            'founder_club_reapply_available_at',
            'founder_club_last_checked',
        ])

        # Log to support enquiries (best-effort) so staff has an audit trail.
        try:
            SupportEnquiry.objects.create(
                user=request.user,
                subject='Founder Club',
                message=(
                    f"Founder Club granted via invite rewards.\n"
                    f"Points: {points}\n"
                    f"Verified invites: {verified_invites}\n"
                    f"Account age days: {account_age_days}\n"
                ),
                page=request.path,
                user_agent=(request.META.get('HTTP_USER_AGENT') or '')[:300],
            )
        except Exception:
            pass

        messages.success(request, 'Founder Club activated!')
        return redirect('invite-friends')

    return render(request, 'a_users/founder_club_apply.html', {
        'points': points,
        'verified_invites': verified_invites,
        'required_points': required_points,
        'required_invites': required_invites,
        'min_account_age_days': min_age_days,
        'account_age_days': account_age_days,
        'eligible': eligible,
        'reapply_at': reapply_at,
    })


def _can_view_follow_lists(request, profile_user: User) -> tuple[bool, str]:
    viewer_verified = _has_verified_email(getattr(request, 'user', None))
    is_owner = bool(request.user.is_authenticated and request.user == profile_user)
    is_private = bool(getattr(getattr(profile_user, 'profile', None), 'is_private_account', False))
    is_following = False

    if request.user.is_authenticated and request.user != profile_user:
        try:
            is_following = Follow.objects.filter(follower=request.user, following=profile_user).exists()
        except Exception:
            is_following = False

    if not request.user.is_authenticated:
        return False, 'Login and verify your email to view followers/following.'

    # Private account: owner and accepted followers can view lists.
    if is_private:
        if is_owner or is_following:
            return True, ''
        return False, 'This acc is private. You cannot view following/followers unless the user accepts your request'

    # Public account: verified-email gate remains in place.
    if not viewer_verified:
        return False, 'Verify your email to view followers/following.'

    return True, ''


@login_required
def profile_followers_partial_view(request, username: str):
    profile_user = get_object_or_404(User, username=username)
    allowed, reason = _can_view_follow_lists(request, profile_user)
    is_owner = bool(request.user == profile_user)
    search_query = (request.GET.get('q') or '').strip()
    owner_only_notice_threshold = 801
    if not allowed:
        return render(request, 'a_users/partials/follow_list_modal.html', {
            'profile_user': profile_user,
            'kind': 'followers',
            'is_owner': is_owner,
            'locked_reason': reason,
            'items': [],
            'total_count': 0,
            'is_full': False,
            'owner_only_notice': '',
            'search_query': search_query,
            'verified_user_ids': set(),
        })

    # Followers visibility rules:
    # - Owner sees full followers list.
    # - Non-owner gets limited preview only for very large follower lists (801+).
    total_followers_for_profile = Follow.objects.filter(following=profile_user).count()
    should_limit_for_non_owner = (not is_owner) and (total_followers_for_profile >= owner_only_notice_threshold)
    viewer_limit = 15 if should_limit_for_non_owner else None

    qs = (
        Follow.objects
        .filter(following=profile_user)
        .select_related('follower', 'follower__profile')
        .order_by('-created')
    )
    if search_query:
        qs = qs.filter(
            Q(follower__username__icontains=search_query)
            | Q(follower__profile__name__icontains=search_query)
        )
    total_count = qs.count()
    if viewer_limit is None:
        items = list(qs)
        is_full = True
        owner_only_notice = ''
    else:
        items = list(qs[:viewer_limit])
        is_full = False
        owner_only_notice = f'Only {profile_user.username} can see all followers'

    follower_ids = [getattr(rel.follower, 'id', None) for rel in items]
    verified_user_ids = get_verified_user_ids(follower_ids)

    return render(request, 'a_users/partials/follow_list_modal.html', {
        'profile_user': profile_user,
        'kind': 'followers',
        'is_owner': is_owner,
        'locked_reason': '',
        'items': items,
        'total_count': total_count,
        'is_full': is_full,
        'owner_only_notice': owner_only_notice,
        'search_query': search_query,
        'verified_user_ids': verified_user_ids,
    })


@login_required
def profile_following_partial_view(request, username: str):
    profile_user = get_object_or_404(User, username=username)
    allowed, reason = _can_view_follow_lists(request, profile_user)
    is_owner = bool(request.user == profile_user)
    search_query = (request.GET.get('q') or '').strip()
    if not allowed:
        return render(request, 'a_users/partials/follow_list_modal.html', {
            'profile_user': profile_user,
            'kind': 'following',
            'is_owner': is_owner,
            'locked_reason': reason,
            'items': [],
            'total_count': 0,
            'is_full': False,
            'owner_only_notice': '',
            'search_query': search_query,
            'verified_user_ids': set(),
        })

    # Following visibility rule:
    # - Everyone who is allowed to view can see full following list.
    is_full = True

    qs = (
        Follow.objects
        .filter(follower=profile_user)
        .select_related('following', 'following__profile')
        .order_by('-created')
    )
    if search_query:
        qs = qs.filter(
            Q(following__username__icontains=search_query)
            | Q(following__profile__name__icontains=search_query)
        )
    total_count = qs.count()
    items = list(qs)

    following_ids = [getattr(rel.following, 'id', None) for rel in items]
    verified_user_ids = get_verified_user_ids(following_ids)

    return render(request, 'a_users/partials/follow_list_modal.html', {
        'profile_user': profile_user,
        'kind': 'following',
        'is_owner': is_owner,
        'locked_reason': '',
        'items': items,
        'total_count': total_count,
        'is_full': is_full,
        'owner_only_notice': '',
        'search_query': search_query,
        'verified_user_ids': verified_user_ids,
    })


@login_required
def report_user_view(request, username: str):
    target = get_object_or_404(User, username=username)

    is_htmx = (
        str(request.headers.get('HX-Request') or '').lower() == 'true'
        or str(request.META.get('HTTP_HX_REQUEST') or '').lower() == 'true'
    )
    is_modal = bool(is_htmx and request.GET.get('modal') == '1')

    if target.id == request.user.id:
        messages.error(request, 'You cannot report yourself.')

        if is_modal:
            resp = HttpResponse(status=204)
            resp['HX-Trigger'] = json.dumps({
                'vixo:closeGlobalModal': True,
                'vixo:toast': {
                    'message': 'You cannot report yourself.',
                    'kind': 'error',
                },
            })
            return resp

        return redirect('profile')

    if target.is_superuser:
        messages.error(request, 'Superusers cannot be reported.')

        if is_modal:
            resp = HttpResponse(status=204)
            resp['HX-Trigger'] = json.dumps({
                'vixo:closeGlobalModal': True,
                'vixo:toast': {
                    'message': 'Superusers cannot be reported.',
                    'kind': 'error',
                },
            })
            return resp

        return redirect('profile-user', username=target.username)

    form = ReportUserForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            reason = form.cleaned_data['reason']
            details = (form.cleaned_data.get('details') or '').strip()
            success_message = 'Our team will verify and let you know within a short period of time.'

            UserReport.objects.create(
                reporter=request.user,
                reported_user=target,
                reason=reason,
                details=details,
                status=UserReport.STATUS_OPEN,
            )

            if is_modal:
                return render(request, 'a_users/partials/report_user_success_modal.html', {
                    'target_user': target,
                    'success_title': 'Submitted',
                    'success_message': success_message,
                })

            messages.success(request, f"Submitted. {success_message}")

            return redirect('profile-user', username=target.username)

    template_name = 'a_users/partials/report_user_modal.html' if is_modal else 'a_users/report_user.html'

    return render(request, template_name, {
        'target_user': target,
        'form': form,
    })


@login_required
def my_reports_view(request):
    reports = (
        UserReport.objects
        .filter(reporter=request.user)
        .select_related('reported_user', 'handled_by')
        .order_by('-created_at')
    )

    return render(request, 'a_users/my_reports.html', {
        'reports': reports,
    })


@login_required
def username_availability_view(request):
    """AJAX/JSON: check if a username is available.

    Used by profile edit/settings to show a green tick or red cross.
    """

    desired = (request.GET.get('u') or '').strip()
    if desired.startswith('@'):
        desired = desired[1:].strip()

    def _suggest_usernames(seed: str) -> list[str]:
        seed = (seed or '').strip()
        if seed.startswith('@'):
            seed = seed[1:].strip()
        seed = seed.replace(' ', '')
        seed = seed.lower()
        # Keep only allowed set for our UsernameChangeForm policy.
        try:
            import re as _re

            seed = _re.sub(r'[^a-z0-9_]+', '_', seed)
            seed = _re.sub(r'_+', '_', seed).strip('_')
        except Exception:
            pass
        if not seed:
            seed = 'vixo'
        seed = seed[:18]

        out: list[str] = []
        try:
            import random as _random

            for _ in range(30):
                if len(out) >= 5:
                    break
                cand = f"{seed}_{_random.randint(10, 9999)}"
                try:
                    form2 = UsernameChangeForm({'username': cand}, user=request.user, profile=profile)
                    if form2.is_valid():
                        out.append(cand)
                except Exception:
                    continue
        except Exception:
            pass
        return out

    # Basic rate limit (best-effort)
    try:
        if check_rate_limit and make_key and get_client_ip:
            rl = check_rate_limit(
                make_key('username_check', request.user.id, get_client_ip(request)),
                limit=60,
                period_seconds=60,
            )
            if not rl.allowed:
                return JsonResponse({'available': False, 'reason': 'rate_limited'}, status=429)
    except Exception:
        pass

    # Reuse form validation (format + uniqueness)
    profile = None
    try:
        profile = request.user.profile
    except Exception:
        profile = None

    form = UsernameChangeForm({'username': desired}, user=request.user, profile=profile)
    can_change, next_at = form.can_change_now()
    if not can_change:
        msg = 'Cooldown active'
        if next_at:
            msg = f'You can change again after {next_at:%b %d, %Y}.'
        return JsonResponse({'available': False, 'reason': 'cooldown', 'message': msg})

    if not desired:
        return JsonResponse({'available': False, 'reason': 'empty', 'suggestions': _suggest_usernames('vixo')})

    if not form.is_valid():
        err = ''
        try:
            err = form.errors.get('username', [''])[0]
        except Exception:
            err = 'Invalid username.'
        return JsonResponse({'available': False, 'reason': 'invalid', 'message': str(err), 'suggestions': _suggest_usernames(desired)})

    return JsonResponse({'available': True, 'suggestions': []})


@login_required
def onboarding_username_view(request):
    # Keep other permission popups deferred during onboarding.
    try:
        request.session['onboarding_in_progress'] = True
    except Exception:
        pass

    profile = get_object_or_404(Profile, user=request.user)

    # If this session does not require username onboarding, skip.
    try:
        if not bool(request.session.get('onboarding_needs_username')):
            return redirect('onboarding-intro')
    except Exception:
        pass

    username_form = UsernameChangeForm(user=request.user, profile=profile)
    try:
        username_form.fields['username'].widget.attrs.update({
            'placeholder': 'bhavin',
            'class': 'w-full bg-gray-800/60 border border-gray-700 text-gray-100 rounded-xl pl-10 pr-4 py-3 placeholder-gray-400 outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-500/30',
            'autocomplete': 'off',
            'autocapitalize': 'none',
            'spellcheck': 'false',
        })
    except Exception:
        pass

    if request.method == 'POST':
        desired = (request.POST.get('username') or '').strip()
        if desired.startswith('@'):
            desired = desired[1:].strip()

        username_form = UsernameChangeForm({'username': desired}, user=request.user, profile=profile)
        can_change, next_at = username_form.can_change_now()
        if not can_change:
            if next_at:
                messages.error(request, f'You can change your username again after {next_at:%b %d, %Y}.')
            else:
                messages.error(request, 'You cannot change your username right now.')
        elif username_form.is_valid():
            new_username = username_form.cleaned_data['username']
            old_username = request.user.username
            try:
                request.user.username = new_username
                request.user.save(update_fields=['username'])
                profile.username_change_count = int(getattr(profile, 'username_change_count', 0) or 0) + 1
                profile.username_last_changed_at = timezone.now()
                profile.save(update_fields=['username_change_count', 'username_last_changed_at'])
                try:
                    request.session.pop('onboarding_needs_username', None)
                except Exception:
                    pass
                return redirect('onboarding-intro')
            except Exception:
                messages.error(request, 'Failed to update username. Please try again.')

    return render(request, 'a_users/onboarding/username.html', {
        'username_form': username_form,
    })


@login_required
def onboarding_intro_view(request):
    try:
        request.session['onboarding_in_progress'] = True
    except Exception:
        pass

    # Simple interstitial screen before the profile setup steps.
    return render(request, 'a_users/onboarding/intro.html', {})


@login_required
def onboarding_photo_view(request):
    try:
        request.session['onboarding_in_progress'] = True
    except Exception:
        pass

    profile = get_object_or_404(Profile, user=request.user)
    form = OnboardingAvatarForm(instance=profile)

    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip().lower()
        if action == 'skip':
            return redirect('onboarding-about')

        avatar_file = request.FILES.get('image')
        if avatar_file is not None and _avatar_file_exceeds_limit(avatar_file):
            messages.error(request, 'Avatar image must be under 500KB.')
            form = OnboardingAvatarForm(request.POST, request.FILES, instance=profile)
            return render(request, 'a_users/onboarding/photo.html', {
                'form': form,
                'profile': profile,
            })

        form = OnboardingAvatarForm(request.POST, request.FILES, instance=profile)
        if action == 'upload' and not request.FILES.get('image'):
            try:
                form.add_error('image', 'Please select a photo first.')
            except Exception:
                messages.error(request, 'Please select a photo first.')
            return render(request, 'a_users/onboarding/photo.html', {
                'form': form,
                'profile': profile,
            })

        if form.is_valid():
            try:
                uploaded = request.FILES.get('image')
                if uploaded:
                    profile.avatar_review_status = 'pending'
                    profile.avatar_pending_local = ''
                    profile.save(update_fields=['avatar_review_status', 'avatar_pending_local'])

                    temp_dir = os.path.join(settings.BASE_DIR, 'media', 'pending_avatars')
                    os.makedirs(temp_dir, exist_ok=True)
                    ext = os.path.splitext(uploaded.name)[1].lower() or '.jpg'
                    temp_filename = f'pending_{profile.pk}_{uuid.uuid4().hex[:8]}{ext}'
                    temp_path = os.path.join(temp_dir, temp_filename)
                    with open(temp_path, 'wb') as fh:
                        for chunk in uploaded.chunks():
                            fh.write(chunk)

                    Profile.objects.filter(pk=profile.pk).update(
                        avatar_review_status='pending',
                        avatar_pending_local=temp_path,
                    )
                messages.success(
                    request,
                    'Success! Your profile pic has been submitted successfully for review. Please wait for a while for being approved by the Vixo Team.',
                )
                return redirect('onboarding-about')
            except Exception as exc:
                exc_msg = (str(exc) or '').strip().lower()
                if 'upload rejected by vixogram team' in exc_msg:
                    messages.error(request, 'Your profile pic has been removed. This image is not accepted under our Terms & Conditions.')
                elif 'upload is under review' in exc_msg:
                    messages.error(request, 'Your profile pic is under moderation review. Please upload a different image.')
                else:
                    messages.error(request, 'Could not save your photo right now. Please try again.')

    return render(request, 'a_users/onboarding/photo.html', {
        'form': form,
        'profile': profile,
    })


@login_required
def onboarding_about_view(request):
    try:
        request.session['onboarding_in_progress'] = True
    except Exception:
        pass

    profile = get_object_or_404(Profile, user=request.user)
    form = OnboardingAboutForm(instance=profile)

    if request.method == 'POST':
        form = OnboardingAboutForm(request.POST, instance=profile)
        if form.is_valid():
            try:
                form.save()
                # Onboarding complete: allow other popups to show now.
                try:
                    request.session.pop('onboarding_in_progress', None)
                except Exception:
                    pass
                return redirect('home')
            except Exception:
                messages.error(request, 'Could not save your profile right now. Please try again.')

    return render(request, 'a_users/onboarding/about.html', {
        'form': form,
    })


@login_required
def profile_edit_view(request):
    profile = get_object_or_404(Profile, user=request.user)
    form = ProfileForm(instance=profile)
    username_form = UsernameChangeForm(user=request.user, profile=profile)

    def _redirect_profile_with_fresh_token():
        try:
            qs = urlencode({'updated': int(timezone.now().timestamp() * 1000)})
            return redirect(f"{reverse('profile')}?{qs}")
        except Exception:
            return redirect('profile')
    
    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip().lower()

        if action == 'username':
            username_form = UsernameChangeForm(request.POST, user=request.user, profile=profile)
            can_change, next_at = username_form.can_change_now()
            if not can_change:
                if next_at:
                    messages.error(request, f'You can change your username again after {next_at:%b %d, %Y}.')
                else:
                    messages.error(request, 'You cannot change your username right now.')
            elif username_form.is_valid():
                new_username = username_form.cleaned_data['username']
                old_username = request.user.username

                try:
                    request.user.username = new_username
                    request.user.save(update_fields=['username'])
                    profile.username_change_count = int(getattr(profile, 'username_change_count', 0) or 0) + 1
                    profile.username_last_changed_at = timezone.now()
                    profile.save(update_fields=['username_change_count', 'username_last_changed_at'])
                    messages.success(request, f'Username changed from @{old_username} to @{new_username}.')
                    return _redirect_profile_with_fresh_token()
                except Exception:
                    messages.error(request, 'Failed to update username. Please try again.')

        else:
            form = ProfileForm(request.POST, request.FILES, instance=profile)
            avatar_file = request.FILES.get('image')
            if avatar_file is not None and _avatar_file_exceeds_limit(avatar_file):
                can_change, next_at = username_form.can_change_now()
                messages.error(request, 'Avatar image must be under 500KB.')
                return render(request, 'a_users/profile_edit.html', {
                    'form': form,
                    'profile': profile,
                    'username_form': username_form,
                    'username_can_change': can_change,
                    'username_next_available_at': next_at,
                    'username_cooldown_days': int(getattr(settings, 'USERNAME_CHANGE_COOLDOWN_DAYS', 21) or 21),
                })

            if form.is_valid():
                has_new_avatar = bool(request.FILES.get('image'))
                has_new_cover = bool(request.FILES.get('cover_image'))

                if has_new_avatar or has_new_cover:
                    # Save text fields but keep current media unchanged until admin approval.
                    avatar_file = request.FILES.get('image')
                    cover_file = request.FILES.get('cover_image')
                    approved_image_name = (
                        Profile.objects
                        .filter(pk=profile.pk)
                        .values_list('image', flat=True)
                        .first()
                    )
                    approved_cover_name = (
                        Profile.objects
                        .filter(pk=profile.pk)
                        .values_list('cover_image', flat=True)
                        .first()
                    )
                    instance = form.save(commit=False)
                    if approved_image_name:
                        instance.image.name = str(approved_image_name)
                    else:
                        instance.image = None
                    if approved_cover_name:
                        instance.cover_image.name = str(approved_cover_name)
                    else:
                        instance.cover_image = None
                    instance.save()

                    update_kwargs = {}

                    if avatar_file is not None:
                        avatar_dir = os.path.join(settings.BASE_DIR, 'media', 'pending_avatars')
                        os.makedirs(avatar_dir, exist_ok=True)
                        avatar_ext = os.path.splitext(avatar_file.name)[1].lower() or '.jpg'
                        avatar_filename = f'pending_{profile.pk}_{uuid.uuid4().hex[:8]}{avatar_ext}'
                        avatar_path = os.path.join(avatar_dir, avatar_filename)
                        with open(avatar_path, 'wb') as fh:
                            for chunk in avatar_file.chunks():
                                fh.write(chunk)
                        update_kwargs['avatar_review_status'] = 'pending'
                        update_kwargs['avatar_pending_local'] = avatar_path

                    if cover_file is not None:
                        cover_dir = os.path.join(settings.BASE_DIR, 'media', 'pending_covers')
                        os.makedirs(cover_dir, exist_ok=True)
                        cover_ext = os.path.splitext(cover_file.name)[1].lower() or '.jpg'
                        cover_filename = f'pending_cover_{profile.pk}_{uuid.uuid4().hex[:8]}{cover_ext}'
                        cover_path = os.path.join(cover_dir, cover_filename)
                        with open(cover_path, 'wb') as fh:
                            for chunk in cover_file.chunks():
                                fh.write(chunk)
                        update_kwargs['cover_review_status'] = 'pending'
                        update_kwargs['cover_pending_local'] = cover_path

                    if update_kwargs:
                        Profile.objects.filter(pk=profile.pk).update(**update_kwargs)

                    if has_new_avatar and has_new_cover:
                        messages.success(request, 'Success! Your profile pic and banner photo have been submitted for review by the Vixo Team.')
                    elif has_new_cover:
                        messages.success(request, 'Success! Your banner photo has been submitted successfully for review. Please wait for approval by the Vixo Team.')
                    else:
                        messages.success(
                            request,
                            'Success! Your profile pic has been submitted successfully for review. Please wait for a while for being approved by the Vixo Team.',
                        )
                    return redirect('profile-edit')

                else:
                    # No new avatar — save everything normally.
                    try:
                        form.save()
                        messages.success(request, 'Profile updated successfully.')
                        return _redirect_profile_with_fresh_token()
                    except Exception as exc:
                        try:
                            from cloudinary.exceptions import AuthorizationRequired
                        except Exception:  # pragma: no cover
                            AuthorizationRequired = None

                        logging.getLogger(__name__).exception('Profile update failed (cover/bio save)')

                        exc_msg = (str(exc) or '').strip().lower()
                        if AuthorizationRequired is not None and isinstance(exc, AuthorizationRequired):
                            messages.error(request, 'Image uploads are currently disabled on the media server. Please enable uploads in Cloudinary or use local media storage.')
                        elif 'upload rejected by vixogram team' in exc_msg:
                            messages.error(request, 'Your profile pic has been removed. This image is not accepted under our Terms & Conditions.')
                        elif 'upload is under review' in exc_msg:
                            messages.error(request, 'Your profile pic is under moderation review. Please upload a different image.')
                        else:
                            messages.error(request, 'This photo violates our community guidelines.\nPlease upload a different photo.')
            
    # Cooldown info for template
    can_change, next_at = username_form.can_change_now()
    cooldown_days = int(getattr(settings, 'USERNAME_CHANGE_COOLDOWN_DAYS', 21) or 21)

    return render(request, 'a_users/profile_edit.html', {
        'form': form,
        'profile': profile,
        'username_form': username_form,
        'username_can_change': can_change,
        'username_next_available_at': next_at,
        'username_cooldown_days': cooldown_days,
    })

@login_required
def avatar_review_status_view(request):
    """Poll endpoint: returns the current avatar_review_status for the logged-in user's profile.

    Once a terminal state (approved / rejected) is read it is reset to 'none'
    so subsequent polls don't keep delivering stale results.
    """
    profile = get_object_or_404(Profile, user=request.user)
    status = (getattr(profile, 'avatar_review_status', '') or 'none').strip()

    if status in ('approved', 'rejected'):
        Profile.objects.filter(pk=profile.pk).update(avatar_review_status='none')

    return JsonResponse({'status': status})


@login_required
def profile_settings_view(request):
    profile = get_object_or_404(Profile, user=request.user)
    form = ProfilePrivacyForm(instance=profile)
    username_form = UsernameChangeForm(user=request.user, profile=profile)
    location_form = ProfilePreferredLocationForm(
        instance=profile,
        initial={'location_query': clean_location_name(getattr(profile, 'preferred_location_city', '') or '')},
    )
    glow_choices = [
        (value, label)
        for value, label in getattr(Profile, 'NAME_GLOW_CHOICES', ())
    ]
    can_use_founder_ui = bool(getattr(profile, 'is_founder_club', False) or getattr(request.user, 'is_superuser', False))

    is_htmx = str(request.headers.get('HX-Request') or '').lower() == 'true'

    try:
        location_cooldown_hours = int(getattr(settings, 'PREFERRED_LOCATION_CHANGE_COOLDOWN_HOURS', 24) or 24)
    except Exception:
        location_cooldown_hours = 24

    def _location_change_state() -> tuple[bool, timezone.datetime | None]:
        last = getattr(profile, 'preferred_location_last_changed_at', None)
        if not last:
            return True, None
        next_at = last + timedelta(hours=location_cooldown_hours)
        now = timezone.now()
        return (now >= next_at), next_at

    if request.method == 'POST' and (request.POST.get('action') or '').strip() == 'privacy':
        old_stealth = bool(getattr(profile, 'is_stealth', False))
        form = ProfilePrivacyForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()

            # If stealth changed, try to update any viewers on profile pages.
            try:
                profile.refresh_from_db(fields=['is_stealth'])
                new_stealth = bool(getattr(profile, 'is_stealth', False))
                if new_stealth != old_stealth:
                    from asgiref.sync import async_to_sync
                    from channels.layers import get_channel_layer

                    channel_layer = get_channel_layer()

                    # Force all profile-presence sockets to re-check stealth rules.
                    # (ProfilePresenceConsumer listens on the same group.)
                    async_to_sync(channel_layer.group_send)(
                        'online-status',
                        {'type': 'online_status_handler'},
                    )
            except Exception:
                pass

            # Re-render partial for HTMX autosave; otherwise redirect.
            if is_htmx:
                try:
                    profile.refresh_from_db(fields=['is_private_account', 'is_stealth', 'is_dnd'])
                except Exception:
                    pass

                resp = render(request, 'a_users/partials/profile_privacy_section.html', {
                    'privacy_form': ProfilePrivacyForm(instance=profile),
                    'profile': profile,
                    'user': request.user,
                })
                resp['HX-Trigger'] = json.dumps({
                    'vixo:toast': {
                        'message': 'Settings updated.',
                        'kind': 'success',
                    },
                })
                return resp

            messages.success(request, 'Privacy setting updated.')
            return redirect('profile-settings')

    if request.method == 'POST' and (request.POST.get('action') or '').strip().lower() == 'username':
        username_form = UsernameChangeForm(request.POST, user=request.user, profile=profile)
        can_change, next_at = username_form.can_change_now()
        if not can_change:
            if next_at:
                messages.error(request, f'You can change your username again after {next_at:%b %d, %Y}.')
            else:
                messages.error(request, 'You cannot change your username right now.')
            return redirect('profile-settings')

        if username_form.is_valid():
            new_username = username_form.cleaned_data['username']
            old_username = request.user.username

            try:
                request.user.username = new_username
                request.user.save(update_fields=['username'])
                profile.username_change_count = int(getattr(profile, 'username_change_count', 0) or 0) + 1
                profile.username_last_changed_at = timezone.now()
                profile.save(update_fields=['username_change_count', 'username_last_changed_at'])
                messages.success(request, f'Username changed from @{old_username} to @{new_username}.')
            except Exception:
                messages.error(request, 'Failed to update username. Please try again.')
            return redirect('profile-settings')

    if request.method == 'POST' and (request.POST.get('action') or '').strip().lower() == 'glow':
        if not can_use_founder_ui:
            messages.error(request, 'Glow colors are available only for Founder Club members.')
            return redirect('profile-settings')

        selected = str(request.POST.get('name_glow_color') or '').strip().lower()
        allowed_values = {v for v, _ in getattr(Profile, 'NAME_GLOW_CHOICES', ())}
        if selected not in allowed_values:
            selected = getattr(Profile, 'NAME_GLOW_NONE', 'none')

        try:
            profile.name_glow_color = selected
            profile.save(update_fields=['name_glow_color'])
            messages.success(request, 'Glow color updated.')
        except Exception:
            messages.error(request, 'Could not update glow color right now.')
        return redirect('profile-settings')

    if request.method == 'POST' and (request.POST.get('action') or '').strip().lower() == 'preferred_location':
        can_change_location, next_location_at = _location_change_state()
        if not can_change_location:
            if next_location_at:
                messages.error(request, f'You can update preferred location again after {next_location_at:%b %d, %Y %I:%M %p}.')
            else:
                messages.error(request, 'Preferred location update is on cooldown.')
            return redirect('profile-settings')

        old_country = str(getattr(profile, 'preferred_location_country', '') or '').strip()
        old_state = str(getattr(profile, 'preferred_location_state', '') or '').strip()
        old_city = str(getattr(profile, 'preferred_location_city', '') or '').strip()

        location_form = ProfilePreferredLocationForm(request.POST, instance=profile)
        if location_form.is_valid():
            try:
                profile = location_form.save(commit=False)
                new_country = str(getattr(profile, 'preferred_location_country', '') or '').strip()
                new_state = str(getattr(profile, 'preferred_location_state', '') or '').strip()
                new_city = str(getattr(profile, 'preferred_location_city', '') or '').strip()

                changed = (old_country != new_country) or (old_state != new_state) or (old_city != new_city)
                if changed:
                    profile.preferred_location_last_changed_at = timezone.now()

                profile.save()
                ensure_local_community_membership(
                    request.user,
                    country=str(getattr(profile, 'preferred_location_country', '') or ''),
                    state=str(getattr(profile, 'preferred_location_state', '') or ''),
                    city=str(getattr(profile, 'preferred_location_city', '') or ''),
                )
                if changed:
                    messages.success(request, 'Preferred location updated.')
                else:
                    messages.info(request, 'Preferred location is already up to date.')
            except Exception:
                messages.error(request, 'Could not update preferred location right now.')
            return redirect('profile-settings')
        messages.error(request, 'Please select a valid city.')

    location_can_change, location_next_available_at = _location_change_state()

    mfa_enabled = bool(getattr(settings, 'ALLAUTH_MFA_ENABLED', False))
    mfa_settings_url = '/accounts/2fa/'
    if mfa_enabled:
        try:
            mfa_settings_url = reverse('mfa_index')
        except Exception:
            mfa_settings_url = '/accounts/2fa/'

    return render(request, 'a_users/profile_settings.html', {
        'privacy_form': form,
        'profile': profile,
        'can_use_founder_ui': can_use_founder_ui,
        'glow_choices': glow_choices,
        'location_form': location_form,
        'username_form': username_form,
        'username_can_change': username_form.can_change_now()[0],
        'username_next_available_at': username_form.can_change_now()[1],
        'username_cooldown_days': int(getattr(settings, 'USERNAME_CHANGE_COOLDOWN_DAYS', 21) or 21),
        'location_can_change': location_can_change,
        'location_next_available_at': location_next_available_at,
        'location_cooldown_hours': location_cooldown_hours,
        'mfa_enabled': mfa_enabled,
        'mfa_settings_url': mfa_settings_url,
    })


@login_required
def follow_toggle_view(request, username: str):
    if request.method != 'POST':
        return redirect('profile-user', username=username)

    is_htmx = str(request.headers.get('HX-Request') or '').lower() == 'true'

    target = get_object_or_404(User, username=username)
    if target == request.user:
        return redirect('profile')

    rel = Follow.objects.filter(follower=request.user, following=target)
    req_qs = FollowRequest.objects.filter(from_user=request.user, to_user=target)

    toast_message = None
    is_private = bool(getattr(getattr(target, 'profile', None), 'is_private_account', False))

    if rel.exists():
        rel.delete()
        toast_message = f'Unfollowed @{target.username}'
        if not is_htmx:
            messages.success(request, toast_message)
    else:
        if is_private:
            # Private account: create/cancel a follow request instead of following immediately.
            if req_qs.exists():
                req_qs.delete()
                toast_message = f'Follow request cancelled for @{target.username}'
            else:
                FollowRequest.objects.create(from_user=request.user, to_user=target)
                toast_message = f'Requested to follow @{target.username}'

            if not is_htmx:
                messages.success(request, toast_message)

            # Realtime badge update for the target user (best-effort)
            try:
                from asgiref.sync import async_to_sync
                from channels.layers import get_channel_layer

                pending_count = FollowRequest.objects.filter(to_user=target).count()
                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    f"notify_user_{target.id}",
                    {
                        'type': 'follow_request_notify_handler',
                        'from_username': request.user.username,
                        'pending_count': int(pending_count or 0),
                    },
                )
            except Exception:
                pass
        else:
            Follow.objects.create(follower=request.user, following=target)
            toast_message = f'Following @{target.username}'
            if not is_htmx:
                messages.success(request, toast_message)

            # Optional in-app notification: only if user is offline (best-effort)
            try:
                if Notification is not None:
                    from a_rtchat.notifications import should_persist_notification

                    should_store = should_persist_notification(user_id=target.id)

                    if should_store:
                        Notification.objects.create(
                            user=target,
                            from_user=request.user,
                            type='follow',
                            preview=f"@{request.user.username} followed you",
                            url=f"/profile/u/{request.user.username}/",
                        )

                        # Realtime toast/badge via per-user notify WS
                        try:
                            from asgiref.sync import async_to_sync
                            from channels.layers import get_channel_layer

                            channel_layer = get_channel_layer()
                            async_to_sync(channel_layer.group_send)(
                                f"notify_user_{target.id}",
                                {
                                    'type': 'follow_notify_handler',
                                    'from_username': request.user.username,
                                    'url': f"/profile/u/{request.user.username}/",
                                    'preview': f"@{request.user.username} followed you",
                                },
                            )
                        except Exception:
                            pass
            except Exception:
                pass

    if is_htmx and request.GET.get('modal') == '1':
        # If the follow action happened inside the profile modal, re-render the modal
        # so the follow/unfollow button updates without leaving the chat page.
        resp = profile_view(request, username=username)
        try:
            triggers = {
                'vixo:toast': {
                    'message': toast_message or '',
                    'kind': 'success',
                    'durationMs': 3500,
                }
            }
            resp['HX-Trigger'] = json.dumps(triggers)
        except Exception:
            pass
        return resp

    if is_htmx:
        # Tell HTMX clients to refresh counts + optionally the modal list.
        try:
            followers_count = Follow.objects.filter(following=request.user).count()
            following_count = Follow.objects.filter(follower=request.user).count()
        except Exception:
            followers_count = None
            following_count = None

        resp = HttpResponse(status=204)
        try:
            resp['HX-Trigger'] = json.dumps({
                'followChanged': {
                    'profile_username': request.user.username,
                    'followers_count': followers_count,
                    'following_count': following_count,
                },
                'vixo:toast': {
                    'message': toast_message or '',
                    'kind': 'success',
                    'durationMs': 3500,
                }
            })
        except Exception:
            pass
        return resp

    return redirect('profile-user', username=username)


@login_required
def follow_requests_modal_view(request):
    page_size = 10
    try:
        offset = max(0, int(request.GET.get('offset') or 0))
    except Exception:
        offset = 0

    qs = (
        FollowRequest.objects
        .filter(to_user=request.user)
        .select_related('from_user', 'from_user__profile')
        .order_by('-created_at')
    )
    items = list(qs[offset:offset + page_size + 1])
    has_more = len(items) > page_size
    if has_more:
        items = items[:page_size]

    pending_count = qs.count()

    context = {
        'items': items,
        'pending_count': int(pending_count or 0),
        'offset': offset,
        'next_offset': offset + len(items),
        'has_more': has_more,
    }

    is_partial = str(request.GET.get('partial') or '').lower() in {'1', 'true', 'yes'}
    template_name = 'a_users/partials/follow_requests_items.html' if is_partial else 'a_users/partials/follow_requests_modal.html'

    resp = render(request, template_name, context)
    try:
        is_htmx = str(request.headers.get('HX-Request') or '').lower() == 'true'
        if is_htmx and not is_partial:
            resp['HX-Trigger'] = json.dumps({
                'followRequestsChanged': {
                    'pending_count': int(pending_count or 0),
                }
            })
    except Exception:
        pass
    return resp


@login_required
def follow_request_decide_view(request, req_id: int, action: str):
    if request.method != 'POST':
        return redirect('home')

    action = (action or '').strip().lower()
    fr = get_object_or_404(FollowRequest, id=req_id, to_user=request.user)

    toast_message = ''
    if action == 'accept':
        Follow.objects.get_or_create(follower=fr.from_user, following=request.user)
        fr.delete()
        toast_message = f"Accepted @{fr.from_user.username}"
    elif action == 'reject':
        fr.delete()
        toast_message = f"Rejected @{fr.from_user.username}"
    else:
        toast_message = 'Invalid action.'

    pending_count = FollowRequest.objects.filter(to_user=request.user).count()

    # Re-render the modal so the list updates without leaving the page.
    resp = follow_requests_modal_view(request)
    try:
        resp['HX-Trigger'] = json.dumps({
            'followRequestsChanged': {
                'pending_count': int(pending_count or 0),
            },
            'vixo:toast': {
                'message': toast_message,
                'kind': 'success' if action in {'accept', 'reject'} else 'error',
                'durationMs': 3000,
            }
        })
    except Exception:
        pass
    return resp


@login_required
def remove_follower_view(request, username: str):
    """Remove a user from the current user's followers list."""
    if request.method != 'POST':
        return redirect('profile')

    is_htmx = str(request.headers.get('HX-Request') or '').lower() == 'true'

    target = get_object_or_404(User, username=username)
    if target == request.user:
        if is_htmx:
            return HttpResponse(status=204)
        return redirect('profile')

    Follow.objects.filter(follower=target, following=request.user).delete()
    toast_message = f'Removed @{target.username} from followers'

    if is_htmx:
        search_query = (request.GET.get('q') or '').strip()
        qs = (
            Follow.objects
            .filter(following=request.user)
            .select_related('follower', 'follower__profile')
            .order_by('-created')
        )
        if search_query:
            qs = qs.filter(
                Q(follower__username__icontains=search_query)
                | Q(follower__profile__name__icontains=search_query)
            )
        total_count = qs.count()
        items = list(qs)

        follower_ids = [getattr(rel.follower, 'id', None) for rel in items]
        verified_user_ids = get_verified_user_ids(follower_ids)

        try:
            followers_count = total_count
            following_count = Follow.objects.filter(follower=request.user).count()
        except Exception:
            followers_count = None
            following_count = None

        resp = render(request, 'a_users/partials/follow_list_modal.html', {
            'profile_user': request.user,
            'kind': 'followers',
            'is_owner': True,
            'locked_reason': '',
            'items': items,
            'total_count': total_count,
            'is_full': True,
            'owner_only_notice': '',
            'search_query': search_query,
            'verified_user_ids': verified_user_ids,
        })
        try:
            resp['HX-Trigger'] = json.dumps({
                'followChanged': {
                    'profile_username': request.user.username,
                    'followers_count': followers_count,
                    'following_count': following_count,
                },
                'vixo:toast': {
                    'message': toast_message,
                    'kind': 'success',
                    'durationMs': 3500,
                }
            })
        except Exception:
            pass
        return resp

    messages.success(request, toast_message)
    return redirect('profile')


@login_required
def notifications_view(request):
    # User requested: no separate notifications page.
    return redirect('home')


@login_required
def notifications_dropdown_view(request):
    if Notification is None:
        return HttpResponse('', status=200)

    qs = Notification.objects.filter(user=request.user)
    notifications = list(
        qs.select_related('from_user')
        .order_by('-created')[:12]
    )
    try:
        unread_count = int(qs.filter(is_read=False).count() or 0)
    except Exception:
        unread_count = 0
    return render(request, 'a_users/partials/notifications_dropdown.html', {
        'notifications': notifications,
        'unread_count': unread_count,
    })


@login_required
def notifications_mark_all_read_view(request):
    if request.method != 'POST':
        return HttpResponse(status=405)

    is_htmx = str(request.headers.get('HX-Request') or '').lower() == 'true'

    if Notification is not None:
        try:
            Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        except Exception:
            pass

    if not is_htmx or Notification is None:
        return HttpResponse(status=204)

    qs = Notification.objects.filter(user=request.user)
    notifications = list(
        qs.select_related('from_user')
        .order_by('-created')[:12]
    )
    return render(
        request,
        'a_users/partials/notifications_dropdown.html',
        {
            'notifications': notifications,
            'unread_count': 0,
        },
    )


@login_required
def notifications_mark_read_view(request, notif_id: int):
    if request.method != 'POST':
        return HttpResponse(status=405)

    if Notification is None:
        return HttpResponse(status=204)

    try:
        Notification.objects.filter(user=request.user, id=notif_id).update(is_read=True)
    except Exception:
        pass
    return HttpResponse(status=204)


@login_required
def notifications_clear_all_view(request):
    if request.method != 'POST':
        return HttpResponse(status=405)

    is_htmx = str(request.headers.get('HX-Request') or '').lower() == 'true'

    if Notification is not None:
        try:
            Notification.objects.filter(user=request.user).delete()
        except Exception:
            pass

    if not is_htmx or Notification is None:
        return HttpResponse(status=204)

    return render(
        request,
        'a_users/partials/notifications_dropdown.html',
        {
            'notifications': [],
            'unread_count': 0,
        },
    )