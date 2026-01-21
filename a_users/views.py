from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Profile
from .forms import ProfileForm
from .forms import ReportUserForm
from .forms import ProfilePrivacyForm
from .forms import SupportEnquiryForm
from django.contrib.auth.models import User
from django.http import HttpResponse
from django.http import JsonResponse
from django.urls import reverse
from django.core import signing
from urllib.parse import urlencode
from django.utils.http import url_has_allowed_host_and_scheme

from a_users.models import Follow
from a_users.models import UserReport
from a_users.models import SupportEnquiry
from a_users.badges import VERIFIED_FOLLOWERS_THRESHOLD, get_verified_user_ids

try:
    from a_rtchat.models import Notification
except Exception:  # pragma: no cover
    Notification = None


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
    if request.user.is_authenticated and request.user != profile_user:
        is_following = Follow.objects.filter(follower=request.user, following=profile_user).exists()

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

    show_follow_lists = bool(viewer_verified and (not is_private or is_owner))
    follow_lists_locked_reason = ''

    if not show_follow_lists:
        if not request.user.is_authenticated:
            follow_lists_locked_reason = 'Login and verify your email to view followers/following.'
        elif not viewer_verified:
            follow_lists_locked_reason = 'Verify your email to view followers/following.'
        elif is_private and not is_owner:
            follow_lists_locked_reason = 'This account is private. Only counts are visible.'
        
    return render(request, 'a_users/profile.html', {
        'profile': user_profile,
        'profile_user': profile_user,
        'followers_count': followers_count,
        'following_count': following_count,
        'is_verified_badge': is_verified_badge,
        'is_following': is_following,
        'show_follow_lists': show_follow_lists,
        'follow_lists_locked_reason': follow_lists_locked_reason,
        'is_owner': is_owner,
        'is_private': is_private,
        'show_presence': show_presence,
        'presence_online': visible_online,
    })


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

    return render(request, 'a_users/invite_friends.html', {
        'invite_url': invite_url,
        'points': points,
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
    if target.id == request.user.id:
        messages.error(request, 'You cannot report yourself.')
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
            return redirect('profile-user', username=target.username)

    return render(
        request,
        'a_users/report_user.html',
        {
            'target_user': target,
            'form': form,
        },
    )


@login_required
def profile_edit_view(request):
    profile = get_object_or_404(Profile, user=request.user)
    form = ProfileForm(instance=profile)
    
    if request.method == 'POST':
        form = ProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            return redirect('profile')
            
    return render(request, 'a_users/profile_edit.html', {'form': form, 'profile': profile})

@login_required
def profile_settings_view(request):
    profile = get_object_or_404(Profile, user=request.user)
    form = ProfilePrivacyForm(instance=profile)

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

            messages.success(request, 'Privacy setting updated.')
            return redirect('profile-settings')

    return render(request, 'a_users/profile_settings.html', {
        'privacy_form': form,
        'profile': profile,
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
    if rel.exists():
        rel.delete()
        messages.success(request, f'Unfollowed @{target.username}')
    else:
        Follow.objects.create(follower=request.user, following=target)
        messages.success(request, f'Following @{target.username}')

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

    if is_htmx:
        # Tell HTMX clients to refresh counts + optionally the modal list.
        try:
            followers_count = Follow.objects.filter(following=request.user).count()
            following_count = Follow.objects.filter(follower=request.user).count()
        except Exception:
            followers_count = None
            following_count = None

        resp = HttpResponse(status=204)
        resp['HX-Trigger'] = (
            '{'
            '  "followChanged": {'
            f'    "profile_username": "{request.user.username}",' 
            f'    "followers_count": {followers_count if followers_count is not None else "null"},'
            f'    "following_count": {following_count if following_count is not None else "null"}'
            '  }'
            '}'
        )
        return resp

    return redirect('profile-user', username=username)


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