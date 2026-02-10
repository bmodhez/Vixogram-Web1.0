import json
import base64
import re
import uuid
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

from .models import Profile, Story, StoryView, DEFAULT_AVATAR_DATA_URI
from .forms import ProfileForm
from .forms import ReportUserForm
from .forms import ProfilePrivacyForm
from .forms import SupportEnquiryForm
from .forms import UsernameChangeForm
from .forms import StoryForm

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
    if request.user.is_authenticated and request.user != profile_user:
        is_following = Follow.objects.filter(follower=request.user, following=profile_user).exists()
        try:
            is_follow_requested = FollowRequest.objects.filter(from_user=request.user, to_user=profile_user).exists()
        except Exception:
            is_follow_requested = False

    viewer_verified = _has_verified_email(getattr(request, 'user', None))
    is_owner = bool(request.user.is_authenticated and request.user == profile_user)
    is_private = bool(getattr(user_profile, 'is_private_account', False))

    # Presence visibility
    is_bot = bool(getattr(user_profile, 'is_bot', False))
    is_stealth = bool(getattr(user_profile, 'is_stealth', False))
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
        'followers_count': followers_count,
        'following_count': following_count,
        'is_verified_badge': is_verified_badge,
        'is_following': is_following,
        'is_follow_requested': bool(is_follow_requested),
        'show_follow_lists': show_follow_lists,
        'follow_lists_locked_reason': follow_lists_locked_reason,
        'is_owner': is_owner,
        'is_private': is_private,
        'show_presence': show_presence,
        'presence_online': visible_online,
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
            'presenceWsEnabled': bool(show_presence and (is_owner or not is_stealth)),
        }
    except Exception:
        ctx['profile_config'] = {
            'profileUsername': getattr(profile_user, 'username', ''),
            'isOwner': bool(is_owner),
            'presenceOnline': bool(visible_online),
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

    res = JsonResponse({'ok': True})
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

    max_active = 25
    try:
        if callable(get_story_max_active):
            max_active = int(get_story_max_active() or 25)
    except Exception:
        max_active = 25

    if _active_story_count() >= max_active:
        msg = f'You can put only {max_active} stories.'
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
            if _active_story_count() >= max_active:
                msg = f'You can put only {max_active} stories.'
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

            story = form.save(commit=False)
            story.user = request.user
            story.save()
            messages.success(request, 'Story added. It will auto-expire in 24 hours.')
            if is_htmx and is_modal:
                # Close modal + show toast without page navigation.
                return HttpResponse(
                    """
                    <div></div>
                    <script>
                      try {
                        document.body.dispatchEvent(new CustomEvent('vixo:toast', { detail: { message: 'Story added.', kind: 'success', durationMs: 2500 } }));
                      } catch (e) {}
                      try { document.body.dispatchEvent(new Event('vixo:closeGlobalModal')); } catch (e) {}
                    </script>
                    """.strip()
                )
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

    if not request.user.is_authenticated:
        return False, 'Login and verify your email to view followers/following.'
    if not viewer_verified:
        return False, 'Verify your email to view followers/following.'
    if is_private and not is_owner:
        return False, 'This account is private. Only counts are visible.'
    return True, ''


@login_required
def profile_followers_partial_view(request, username: str):
    profile_user = get_object_or_404(User, username=username)
    allowed, reason = _can_view_follow_lists(request, profile_user)
    if not allowed:
        return render(request, 'a_users/partials/follow_list_modal.html', {
            'profile_user': profile_user,
            'kind': 'followers',
            'is_owner': bool(request.user == profile_user),
            'locked_reason': reason,
            'items': [],
            'total_count': 0,
            'is_full': False,
            'verified_user_ids': set(),
        })

    is_full = str(request.GET.get('full') or '') in {'1', 'true', 'True', 'yes'}

    qs = (
        Follow.objects
        .filter(following=profile_user)
        .select_related('follower', 'follower__profile')
        .order_by('-created')
    )
    total_count = qs.count()
    items = list(qs[:(total_count if is_full else 5)])

    follower_ids = [getattr(rel.follower, 'id', None) for rel in items]
    verified_user_ids = get_verified_user_ids(follower_ids)

    return render(request, 'a_users/partials/follow_list_modal.html', {
        'profile_user': profile_user,
        'kind': 'followers',
        'is_owner': bool(request.user == profile_user),
        'locked_reason': '',
        'items': items,
        'total_count': total_count,
        'is_full': is_full,
        'verified_user_ids': verified_user_ids,
    })


@login_required
def profile_following_partial_view(request, username: str):
    profile_user = get_object_or_404(User, username=username)
    allowed, reason = _can_view_follow_lists(request, profile_user)
    if not allowed:
        return render(request, 'a_users/partials/follow_list_modal.html', {
            'profile_user': profile_user,
            'kind': 'following',
            'is_owner': bool(request.user == profile_user),
            'locked_reason': reason,
            'items': [],
            'total_count': 0,
            'is_full': False,
            'verified_user_ids': set(),
        })

    is_full = str(request.GET.get('full') or '') in {'1', 'true', 'True', 'yes'}

    qs = (
        Follow.objects
        .filter(follower=profile_user)
        .select_related('following', 'following__profile')
        .order_by('-created')
    )
    total_count = qs.count()
    items = list(qs[:(total_count if is_full else 5)])

    following_ids = [getattr(rel.following, 'id', None) for rel in items]
    verified_user_ids = get_verified_user_ids(following_ids)

    return render(request, 'a_users/partials/follow_list_modal.html', {
        'profile_user': profile_user,
        'kind': 'following',
        'is_owner': bool(request.user == profile_user),
        'locked_reason': '',
        'items': items,
        'total_count': total_count,
        'is_full': is_full,
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

    form = ReportUserForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            reason = form.cleaned_data['reason']
            details = (form.cleaned_data.get('details') or '').strip()

            # Avoid duplicate open reports from the same reporter to the same user.
            obj, created = UserReport.objects.get_or_create(
                reporter=request.user,
                reported_user=target,
                status=UserReport.STATUS_OPEN,
                defaults={'reason': reason, 'details': details},
            )
            if not created:
                # Update details/reason if they submit again.
                obj.reason = reason
                obj.details = details
                obj.save(update_fields=['reason', 'details'])

            messages.success(request, f"Report submitted for @{target.username}.")

            if is_modal:
                resp = HttpResponse(status=204)
                resp['HX-Trigger'] = json.dumps({
                    'vixo:closeGlobalModal': True,
                    'vixo:toast': {
                        'message': f"Report submitted for @{target.username}.",
                        'kind': 'success',
                    },
                })
                return resp

            return redirect('profile-user', username=target.username)

    template_name = 'a_users/partials/report_user_modal.html' if is_modal else 'a_users/report_user.html'

    return render(request, template_name, {
        'target_user': target,
        'form': form,
    })


@login_required
def username_availability_view(request):
    """AJAX/JSON: check if a username is available.

    Used by profile edit/settings to show a green tick or red cross.
    """

    desired = (request.GET.get('u') or '').strip()

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
        return JsonResponse({'available': False, 'reason': 'empty'})

    if not form.is_valid():
        err = ''
        try:
            err = form.errors.get('username', [''])[0]
        except Exception:
            err = 'Invalid username.'
        return JsonResponse({'available': False, 'reason': 'invalid', 'message': str(err)})

    return JsonResponse({'available': True})


@login_required
def profile_edit_view(request):
    profile = get_object_or_404(Profile, user=request.user)
    form = ProfileForm(instance=profile)
    username_form = UsernameChangeForm(user=request.user, profile=profile)
    
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
                    return redirect('profile')
                except Exception:
                    messages.error(request, 'Failed to update username. Please try again.')

        else:
            form = ProfileForm(request.POST, request.FILES, instance=profile)
            if form.is_valid():
                try:
                    form.save()
                    return redirect('profile')
                except Exception as exc:
                    try:
                        from cloudinary.exceptions import AuthorizationRequired
                    except Exception:  # pragma: no cover
                        AuthorizationRequired = None

                    try:
                        import logging
                        logging.getLogger(__name__).exception('Profile update failed (avatar/cover save)')
                    except Exception:
                        pass

                    # If Cloudinary account is locked/disabled, show a clearer message.
                    if AuthorizationRequired is not None and isinstance(exc, AuthorizationRequired):
                        messages.error(request, 'Image uploads are currently disabled on the media server. Please enable uploads in Cloudinary or use local media storage.')
                    else:
                        messages.error(request, 'Could not save your profile image right now. Please try a smaller image or try again later.')
            
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
def profile_settings_view(request):
    profile = get_object_or_404(Profile, user=request.user)
    form = ProfilePrivacyForm(instance=profile)
    username_form = UsernameChangeForm(user=request.user, profile=profile)

    is_htmx = str(request.headers.get('HX-Request') or '').lower() == 'true'

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

    return render(request, 'a_users/profile_settings.html', {
        'privacy_form': form,
        'profile': profile,
        'username_form': username_form,
        'username_can_change': username_form.can_change_now()[0],
        'username_next_available_at': username_form.can_change_now()[1],
        'username_cooldown_days': int(getattr(settings, 'USERNAME_CHANGE_COOLDOWN_DAYS', 21) or 21),
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
    qs = (
        FollowRequest.objects
        .filter(to_user=request.user)
        .select_related('from_user', 'from_user__profile')
        .order_by('-created_at')
    )
    items = list(qs[:200])
    pending_count = qs.count()
    return render(request, 'a_users/partials/follow_requests_modal.html', {
        'items': items,
        'pending_count': int(pending_count or 0),
    })


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
        is_full = str(request.GET.get('full') or '') in {'1', 'true', 'True', 'yes'}

        qs = (
            Follow.objects
            .filter(following=request.user)
            .select_related('follower', 'follower__profile')
            .order_by('-created')
        )
        total_count = qs.count()
        items = list(qs[:(total_count if is_full else 5)])

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
            'is_full': is_full,
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