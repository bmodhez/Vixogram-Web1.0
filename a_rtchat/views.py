import csv
import json
import time
from datetime import timedelta
from urllib.parse import urlparse

from django.contrib.auth import get_user_model
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.contrib.auth.decorators import login_required
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.http import HttpResponse, Http404
from django.http import JsonResponse
from django.utils import timezone
from django.contrib import messages
from django.core.cache import cache
from django.core.paginator import Paginator
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.conf import settings
from django.urls import reverse
from django.db import transaction
from django.db.models import Q
from django.db.models import Count
from django.db.models.functions import TruncDate, TruncHour
from django.utils.http import url_has_allowed_host_and_scheme

try:
    from a_users.location_ip import maybe_set_profile_city_from_ip
except Exception:  # pragma: no cover
    maybe_set_profile_city_from_ip = None
from a_users.badges import get_verified_user_ids
from a_users.models import Profile
from a_users.models import FCMToken
from a_users.models import UserReport
from a_users.models import SupportEnquiry
from a_users.models import BetaFeature
from .models import *
from .forms import *
from .agora import build_rtc_token
from .moderation import moderate_message
from .channels_utils import chatroom_channel_group_name
from .mentions import extract_mention_usernames, resolve_mentioned_users
from a_rtchat.link_policy import contains_link
from .room_policy import room_allows_links, room_allows_uploads, is_free_promotion_room, is_meme_central_room
from .challenges import (
    get_active_challenge,
    check_message as check_challenge_message,
    end_if_expired as challenge_end_if_expired,
    end_challenge as challenge_end,
    challenge_public_state,
    get_win_loss_totals,
)
from .auto_badges import attach_auto_badges
from .natasha_bot import trigger_natasha_reply_after_commit, NATASHA_USERNAME

# Use the active user model throughout this module.
User = get_user_model()


def _parse_gif_message(body: str) -> str | None:
    """Return a validated GIF url from a '[GIF] <url>' message, else None."""
    text = (body or '').strip()
    if not text.startswith('[GIF]'):
        return None
    url = text[len('[GIF]'):].strip()
    if not url:
        return None

    try:
        parsed = urlparse(url)
    except Exception:
        return None

    if parsed.scheme not in ('http', 'https'):
        return None

    host = (parsed.netloc or '').lower()
    if not host:
        return None

    allowed_hosts = ('giphy.com', 'giphyusercontent.com')
    if host in allowed_hosts:
        return url
    if any(host.endswith('.' + h) for h in allowed_hosts):
        return url
    return None


def _log_blocked_message_event(
    *,
    user,
    chat_group,
    scope: str,
    status_code: int,
    retry_after: int = 0,
    auto_muted_seconds: int = 0,
    text: str = '',
    meta: dict | None = None,
) -> None:
    """Best-effort analytics log for blocked/spam-filtered chat attempts."""
    try:
        if not user or not getattr(user, 'id', None):
            return
        BlockedMessageEvent.objects.create(
            user=user,
            room=chat_group,
            scope=(scope or 'other')[:32],
            status_code=int(status_code or 0),
            retry_after=max(0, int(retry_after or 0)),
            auto_muted_seconds=max(0, int(auto_muted_seconds or 0)),
            text=(text or '')[:2000],
            meta=(meta or {}),
        )
    except Exception:
        return


@login_required
def push_register(request):
    """Register an FCM token for the current user."""
    if request.method != 'POST':
        raise Http404()

    token = ''
    try:
        if request.content_type and 'application/json' in request.content_type:
            payload = json.loads((request.body or b'{}').decode('utf-8'))
            token = (payload.get('token') or '').strip()
        else:
            token = (request.POST.get('token') or '').strip()
    except Exception:
        token = (request.POST.get('token') or '').strip()

    if not token or len(token) > 256:
        return JsonResponse({'ok': False, 'error': 'invalid_token'}, status=400)

    ua = (request.META.get('HTTP_USER_AGENT') or '')[:255]
    obj, _created = FCMToken.objects.update_or_create(
        token=token,
        defaults={'user': request.user, 'user_agent': ua},
    )
    # If token existed but belonged to another user, move it.
    if obj.user_id != request.user.id:
        obj.user = request.user
        obj.user_agent = ua
        obj.save(update_fields=['user', 'user_agent', 'updated', 'last_seen'])

    return JsonResponse({'ok': True})

@login_required
def push_unregister(request):
    if request.method != 'POST':
        raise Http404()
    token = (request.POST.get('token') or '').strip()
    if token:
        FCMToken.objects.filter(user=request.user, token=token).delete()
    return JsonResponse({'ok': True})
from .rate_limit import (
    check_rate_limit,
    get_muted_seconds,
    set_muted,
    is_fast_long_message,
    is_same_emoji_spam,
    is_duplicate_message,
    make_key,
    get_client_ip,
    record_abuse_violation,
)


def _celery_broker_configured() -> bool:
    try:
        env_broker = (os.environ.get('CELERY_BROKER_URL') or '').strip()
        settings_broker = (getattr(settings, 'CELERY_BROKER_URL', None) or '').strip()
        return bool(env_broker or settings_broker)
    except Exception:
        return False


CHAT_UPLOAD_LIMIT_PER_ROOM = getattr(settings, 'CHAT_UPLOAD_LIMIT_PER_ROOM', 15)
CHAT_UPLOAD_MAX_BYTES = getattr(settings, 'CHAT_UPLOAD_MAX_BYTES', 10 * 1024 * 1024)
CHAT_REACTION_EMOJIS = getattr(settings, 'CHAT_REACTION_EMOJIS', ['👍', '❤️', '😂', '😮', '😢', '🙏'])
PRIVATE_ROOM_MEMBER_LIMIT = int(getattr(settings, 'PRIVATE_ROOM_MEMBER_LIMIT', 10))
CODE_ROOM_WAITING_ACTIVE_SECONDS = int(getattr(settings, 'CODE_ROOM_WAITING_ACTIVE_SECONDS', 10))


def _code_room_waiting_cutoff():
    # Requests are considered "active" only while the waiting page is still polling.
    # This makes a requester disappear from the admin list shortly after they leave/back.
    return timezone.now() - timedelta(seconds=max(5, CODE_ROOM_WAITING_ACTIVE_SECONDS))


def _uploads_used_today(chat_group, user) -> int:
    """Count uploads sent today by a user in a room.

    This enforces a daily cap (instead of lifetime cap) for private room uploads.
    """
    try:
        today = timezone.localdate()
    except Exception:
        today = timezone.now().date()
    return (
        chat_group.chat_messages
        .filter(author=user, created__date=today)
        .exclude(file__isnull=True)
        .exclude(file='')
        .count()
    )


def _attach_reaction_pills(messages, user):
    """Attach `reaction_pills` attribute to each message for template rendering."""
    if not messages:
        return
    message_ids = [m.id for m in messages if getattr(m, 'id', None)]
    if not message_ids:
        return

    counts = {}
    for row in (
        MessageReaction.objects.filter(message_id__in=message_ids, emoji__in=CHAT_REACTION_EMOJIS)
        .values('message_id', 'emoji')
        # Enforce counts as "number of users" per emoji; this also protects against any legacy
        # duplicate reactions where a user may have reacted with multiple emojis.
        .annotate(count=Count('user_id', distinct=True))
    ):
        counts[(row['message_id'], row['emoji'])] = int(row['count'] or 0)

    reacted = set(
        MessageReaction.objects.filter(message_id__in=message_ids, user=user, emoji__in=CHAT_REACTION_EMOJIS)
        .values_list('message_id', 'emoji')
    )

    for m in messages:
        pills = []
        for emoji in CHAT_REACTION_EMOJIS:
            c = counts.get((m.id, emoji), 0)
            if c:
                pills.append({'emoji': emoji, 'count': c, 'reacted': (m.id, emoji) in reacted})
        m.reaction_pills = pills


def _attach_one_time_view_flags(messages, user):
    """Attach `one_time_viewed_by_me` attribute for template rendering.

    This avoids N+1 queries when deciding whether to show the open button vs
    an expired placeholder.
    """
    if not messages or not getattr(user, 'id', None):
        return
    message_ids = [
        m.id
        for m in messages
        if getattr(m, 'id', None)
        and getattr(m, 'one_time_view_seconds', None)
        and getattr(m, 'file', None)
    ]
    if not message_ids:
        return

    try:
        viewed = set(
            OneTimeMessageView.objects.filter(user_id=user.id, message_id__in=message_ids)
            .values_list('message_id', flat=True)
        )
    except Exception:
        viewed = set()

    for m in messages:
        try:
            m.one_time_viewed_by_me = m.id in viewed
        except Exception:
            m.one_time_viewed_by_me = False


def _is_chat_blocked(user) -> bool:
    """Chat-blocked users can read chats but cannot send messages or use private chats.

    Staff users are never considered chat-blocked.
    """
    try:
        if getattr(user, 'is_staff', False):
            return False
        return bool(user.profile.chat_blocked)
    except Exception:
        return False


def _get_chat_banned_until(user):
    """Return ban-until datetime if the user is chat-banned, else None.

    Chat-banned users cannot read or write chats.
    Staff users are never considered chat-banned.
    """
    try:
        if getattr(user, 'is_staff', False):
            return None
        prof = getattr(user, 'profile', None)
        if prof is None:
            return None
        return getattr(prof, 'chat_banned_until', None)
    except Exception:
        return None


def _is_chat_banned(user) -> bool:
    """Return True if user is currently chat-banned.

    If the ban has expired, clear it (best-effort) so it auto-unbans.
    """
    until = _get_chat_banned_until(user)
    if not until:
        return False
    try:
        now = timezone.now()
        if until <= now:
            try:
                Profile.objects.filter(user_id=getattr(user, 'id', None)).update(chat_banned_until=None)
            except Exception:
                pass
            return False
        return True
    except Exception:
        return False


def _has_verified_email(user) -> bool:
    """Return True if the user has a verified email (django-allauth).

    Staff users are treated as verified.
    """
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


def _requires_verified_email_for_chat(user) -> bool:
    """Allow a small number of messages for unverified users, then require verification."""
    try:
        if not getattr(user, 'is_authenticated', False):
            return True
        if getattr(user, 'is_staff', False):
            return False
        if _has_verified_email(user):
            return False

        limit = int(getattr(settings, 'UNVERIFIED_CHAT_MESSAGE_LIMIT', 3))
        sent = GroupMessage.objects.filter(author=user).count()
        return sent >= limit
    except Exception:
        # Fail closed: don't allow sends if unsure.
        return True


@login_required
def chat_verify_status(request):
    """Return whether the user is verified for chat (used by verify-gate refresh)."""
    if request.method != 'GET':
        return JsonResponse({'error': 'method_not_allowed'}, status=405)

    verified = _has_verified_email(request.user)
    requires = _requires_verified_email_for_chat(request.user)
    return JsonResponse(
        {
            'verified': bool(verified),
            'requires_verification': bool(requires),
            'reason': 'Verification not yet done. Please verify your email and try again.' if requires else '',
        }
    )


def _groupchat_display_name(room) -> str:
    return (getattr(room, 'groupchat_name', None) or getattr(room, 'group_name', '') or '').strip()


def _build_groupchat_sections(groupchats):
    """Split group chats into UI sections.

    Matching is done by substring so existing emoji variants still group correctly.
    """
    sections_spec = [
        (
            '✨ Social & Fun',
            ['Backbenchers', 'Vibe Check', 'Meme Central', 'Late Night Owls'],
        ),
        (
            '🤝 Professional & Indian Vibes',
            ['Job & Internships', 'Growth Mindset'],
        ),
        (
            '🚀 Tech & Coding',
            ['Code & Coffee', 'Bug Hunters', 'FullStack Circle', 'Showcase Your Work'],
        ),
    ]

    bases_in_order = []
    for _, bases in sections_spec:
        bases_in_order.extend(bases)
    base_to_rank = {b.lower(): i for i, b in enumerate(bases_in_order)}

    assigned = set()
    out_sections = []
    for title, bases in sections_spec:
        items = []
        for room in groupchats:
            if room.pk in assigned:
                continue
            name = _groupchat_display_name(room).lower()
            matched_base = None
            for base in bases:
                if base.lower() in name:
                    matched_base = base
                    break
            if matched_base:
                assigned.add(room.pk)
                items.append((base_to_rank.get(matched_base.lower(), 10_000), room))

        items.sort(key=lambda t: t[0])
        out_sections.append({'title': title, 'rooms': [r for _, r in items]})

    remaining = [r for r in groupchats if r.pk not in assigned]
    remaining.sort(key=lambda r: _groupchat_display_name(r).lower())
    return out_sections, remaining


@login_required
def mention_user_search(request):
    """Return a small list of users for @mention autocomplete.

    Query param: q (without @)
    Response: { results: [{username, display, avatar}] }
    """
    q = (request.GET.get('q') or '').strip()
    if q.startswith('@'):
        q = q[1:]

    q = q[:32]
    # Keep the query conservative to avoid weird regex/LIKE behavior.
    allowed = []
    for ch in q:
        if ch.isalnum() or ch in {'_', '.', '-'}:
            allowed.append(ch)
    q = ''.join(allowed)

    if not q:
        return JsonResponse({'results': []})

    qs = (
        User.objects
        .filter(is_active=True)
        .filter(Q(username__istartswith=q) | Q(profile__displayname__istartswith=q))
        .select_related('profile')
        .order_by('username')
    )[:8]

    results = []
    for u in qs:
        try:
            profile = getattr(u, 'profile', None)
        except Exception:
            profile = None
        display = (getattr(profile, 'name', None) or u.username)
        try:
            avatar = getattr(profile, 'avatar', '') if profile else ''
        except Exception:
            avatar = ''
        results.append({'username': u.username, 'display': display, 'avatar': avatar})

    return JsonResponse({'results': results})

@login_required
def chat_view(request, chatroom_name='public-chat'):
    if _is_chat_banned(request.user):
        return render(request, '403.html', status=403)

    # Only auto-create the global public chat. All other rooms must already exist.
    if chatroom_name == 'public-chat':
        chat_group, created = ChatGroup.objects.get_or_create(group_name=chatroom_name)
    else:
        try:
            chat_group = ChatGroup.objects.get(group_name=chatroom_name)
        except ChatGroup.DoesNotExist:
            return render(
                request,
                'a_rtchat/chatroom_closed.html',
                {'chatroom_name': chatroom_name},
                status=404,
            )
    
    # UI: render only a small slice initially to avoid freezing the browser
    # when a room has a long history. Retention is handled separately via
    # settings.CHAT_MAX_MESSAGES_PER_ROOM.
    initial_limit = int(getattr(settings, 'CHAT_INITIAL_MESSAGES', 60))
    if initial_limit <= 0:
        initial_limit = 60
    # Hard cap for safety.
    initial_limit = max(10, min(initial_limit, 200))

    # Fetch latest by id (fast, stable chronological order) then reverse.
    latest_messages = list(chat_group.chat_messages.order_by('-id')[:initial_limit])
    latest_messages.reverse()
    chat_messages = latest_messages

    has_older_messages = False
    try:
        if chat_messages:
            oldest_id = int(getattr(chat_messages[0], 'id', 0) or 0)
            if oldest_id:
                has_older_messages = chat_group.chat_messages.filter(id__lt=oldest_id).exists()
    except Exception:
        has_older_messages = False

    _attach_reaction_pills(chat_messages, request.user)
    _attach_one_time_view_flags(chat_messages, request.user)
    form = ChatmessageCreateForm()
    # UX: public/group chats use a more standard placeholder.
    try:
        if not getattr(chat_group, 'is_private', False):
            form.fields['body'].widget.attrs['placeholder'] = 'Type a message…'
    except Exception:
        pass

    chat_blocked = _is_chat_blocked(request.user)
    chat_muted_seconds = get_muted_seconds(getattr(request.user, 'id', 0))
    
    other_user = None
    if chat_group.is_private:
        if chat_blocked:
            messages.error(request, 'You are blocked from private chats.')
            return redirect('chatroom', 'public-chat')
        if request.user not in chat_group.members.all():
            # Private code rooms: allow a waiting state for users who joined via code
            # but haven't been admitted by the room admin yet.
            if getattr(chat_group, 'is_code_room', False):
                pending = CodeRoomJoinRequest.objects.filter(
                    room=chat_group,
                    user=request.user,
                    admitted_at__isnull=True,
                ).exists()
                if pending:
                    return render(
                        request,
                        'a_rtchat/code_room_waiting.html',
                        {
                            'chat_group': chat_group,
                            'chatroom_name': chatroom_name,
                            'status_url': reverse('code-room-waiting-status', args=[chatroom_name]),
                            'redirect_url': reverse('chatroom', args=[chatroom_name]),
                        },
                    )
            raise Http404()
        for member in chat_group.members.all():
            if member != request.user:
                other_user = member
                break

    other_last_read_id = 0
    if other_user and getattr(chat_group, 'is_private', False):
        try:
            from .models import ChatReadState

            other_last_read_id = int(
                ChatReadState.objects.filter(user=other_user, group=chat_group)
                .values_list('last_read_message_id', flat=True)
                .first()
                or 0
            )
        except Exception:
            other_last_read_id = 0

    verified_user_ids = set()
    try:
        author_ids = {getattr(m, 'author_id', None) for m in (chat_messages or [])}
        author_ids = {x for x in author_ids if x}
        author_ids.add(getattr(request.user, 'id', None))
        if other_user:
            author_ids.add(getattr(other_user, 'id', None))
        verified_user_ids = get_verified_user_ids(author_ids)
    except Exception:
        verified_user_ids = set()
            
    if chat_group.groupchat_name:
        if request.user not in chat_group.members.all():
            if chat_blocked:
                # Let blocked users read, but do not auto-join as a member.
                pass
            else:
                # Only require verified email if Allauth is configured to make it mandatory.
                # Otherwise, allow users to join/open group chats without being forced into email verification.
                email_verification = str(getattr(settings, 'ACCOUNT_EMAIL_VERIFICATION', 'optional')).lower()
                if email_verification == 'mandatory':
                    email_qs = request.user.emailaddress_set.all()
                    if email_qs.filter(verified=True).exists():
                        chat_group.members.add(request.user)
                    else:
                        messages.warning(request, 'Verify your email to join this group chat.')
                        return redirect('profile-settings')
                else:
                    chat_group.members.add(request.user)

    links_allowed = room_allows_links(chat_group)
    uploads_allowed = room_allows_uploads(chat_group)
    gifs_allowed = not is_free_promotion_room(chat_group)

    uploads_used = 0
    uploads_remaining = None
    if uploads_allowed:
        uploads_used = _uploads_used_today(chat_group, request.user)
        uploads_remaining = max(0, CHAT_UPLOAD_LIMIT_PER_ROOM - uploads_used)
    
    if request.htmx:
        if chat_blocked:
            return HttpResponse('', status=403)

        # Unverified users can send a limited number of messages, then must verify.
        if _requires_verified_email_for_chat(request.user):
            messages.warning(request, 'Verify your email to continue chatting.')
            resp = HttpResponse('', status=200)
            resp.headers['HX-Trigger'] = json.dumps({
                'verify_required': {
                    'reason': 'Verify your email to continue chatting.',
                },
            })
            return resp

        if chat_muted_seconds > 0:
            _log_blocked_message_event(
                user=request.user,
                chat_group=chat_group,
                scope='muted',
                status_code=429,
                retry_after=int(chat_muted_seconds or 0),
            )
            resp = HttpResponse('', status=429)
            resp.headers['Retry-After'] = str(chat_muted_seconds)
            return resp

        # File upload (optional caption) via the same Send button.
        # The template shows the file picker only for private code rooms, but we enforce it here too.
        if request.FILES and 'file' in request.FILES:
            if not uploads_allowed:
                raise Http404()
            if request.user not in chat_group.members.all():
                raise Http404()

            rl = check_rate_limit(
                make_key('chat_upload', chatroom_name, request.user.id),
                limit=int(getattr(settings, 'CHAT_UPLOAD_RATE_LIMIT', 3)),
                period_seconds=int(getattr(settings, 'CHAT_UPLOAD_RATE_PERIOD', 60)),
            )
            if not rl.allowed:
                _, muted2 = record_abuse_violation(
                    scope='chat_upload',
                    user_id=request.user.id,
                    room=chatroom_name,
                    window_seconds=int(getattr(settings, 'CHAT_ABUSE_WINDOW', 600)),
                    threshold=int(getattr(settings, 'CHAT_ABUSE_STRIKE_THRESHOLD', 5)),
                    mute_seconds=int(getattr(settings, 'CHAT_ABUSE_MUTE_SECONDS', 60)),
                )
                _log_blocked_message_event(
                    user=request.user,
                    chat_group=chat_group,
                    scope='chat_upload',
                    status_code=429,
                    retry_after=int(muted2 or rl.retry_after),
                    auto_muted_seconds=int(muted2 or 0),
                    text=(caption or ''),
                )
                resp = HttpResponse('<div class="text-xs text-red-400">Too many uploads. Please wait.</div>', status=429)
                resp.headers['Retry-After'] = str(muted2 or rl.retry_after)
                return resp

            upload = request.FILES['file']
            caption = (request.POST.get('caption') or '').strip()
            if caption:
                caption = caption[:300]

            raw_one_time = (request.POST.get('one_time_seconds') or '').strip()
            one_time_seconds = None
            if raw_one_time:
                try:
                    s = int(raw_one_time)
                except Exception:
                    s = 0
                if s in (3, 8, 15):
                    if not getattr(chat_group, 'is_private', False):
                        return HttpResponse('<div class="text-xs text-red-400">One-time view is only available in private chats.</div>', status=400)
                    one_time_seconds = s

            if getattr(upload, 'size', 0) > CHAT_UPLOAD_MAX_BYTES:
                return HttpResponse('<div class="text-xs text-red-400">File is too large.</div>', status=413)

            content_type = (getattr(upload, 'content_type', '') or '').lower()
            if not (content_type.startswith('image/') or content_type.startswith('video/')):
                return HttpResponse('<div class="text-xs text-red-400">Only photos/videos are allowed.</div>', status=400)

            if one_time_seconds and not content_type.startswith('image/'):
                return HttpResponse('<div class="text-xs text-red-400">One-time view is only supported for photos.</div>', status=400)

            uploads_used = _uploads_used_today(chat_group, request.user)
            if uploads_used >= CHAT_UPLOAD_LIMIT_PER_ROOM:
                return HttpResponse(
                    f'<div class="text-xs text-red-400">Daily upload limit reached ({CHAT_UPLOAD_LIMIT_PER_ROOM}/{CHAT_UPLOAD_LIMIT_PER_ROOM}).</div>',
                    status=400,
                )

            # Meme Central: enforce a per-message cooldown.
            if is_meme_central_room(chat_group):
                cd = check_rate_limit(
                    make_key('chat_cd', chat_group.group_name, request.user.id),
                    limit=1,
                    period_seconds=3,
                )
                if not cd.allowed:
                    _log_blocked_message_event(
                        user=request.user,
                        chat_group=chat_group,
                        scope='chat_cooldown',
                        status_code=429,
                        retry_after=int(cd.retry_after),
                        text=(caption or ''),
                        meta={
                            'cooldown_seconds': 3,
                            'via': 'upload',
                        },
                    )
                    resp = HttpResponse('<div class="text-xs text-red-400">Please wait 3 seconds between messages.</div>', status=429)
                    resp.headers['Retry-After'] = str(cd.retry_after)
                    return resp

            # Free Promotion: enforce a strict 60-second cooldown between sends.
            if is_free_promotion_room(chat_group):
                cd = check_rate_limit(
                    make_key('chat_cd', chat_group.group_name, request.user.id),
                    limit=1,
                    period_seconds=60,
                )
                if not cd.allowed:
                    _log_blocked_message_event(
                        user=request.user,
                        chat_group=chat_group,
                        scope='chat_cooldown',
                        status_code=429,
                        retry_after=int(cd.retry_after),
                        text=(caption or ''),
                        meta={
                            'cooldown_seconds': 60,
                            'via': 'upload',
                        },
                    )
                    resp = HttpResponse('<div class="text-xs text-red-400">Please wait 60 seconds between messages.</div>', status=429)
                    resp.headers['Retry-After'] = str(cd.retry_after)
                    return resp

            message = GroupMessage.objects.create(
                file=upload,
                file_caption=caption or None,
                one_time_view_seconds=one_time_seconds,
                author=request.user,
                group=chat_group,
            )

            # Best-effort: if user didn't allow GPS location, store approximate city/country
            # based on IP after their first message/send.
            try:
                if maybe_set_profile_city_from_ip is not None:
                    maybe_set_profile_city_from_ip(user=request.user, request=request)
            except Exception:
                pass

            # Retention: keep only the newest messages per room (best-effort).
            # Public/group rooms and private rooms can use different caps.
            try:
                from a_rtchat.retention import trim_chat_group_messages

                is_private = bool(getattr(chat_group, 'is_private', False))
                if is_private:
                    keep_last = int(getattr(settings, 'PRIVATE_CHAT_MAX_MESSAGES_PER_ROOM', 1000))
                else:
                    keep_last = int(getattr(settings, 'CHAT_MAX_MESSAGES_PER_ROOM', 300))

                trim_chat_group_messages(
                    chat_group_id=chat_group.id,
                    keep_last=max(1, keep_last),
                )
            except Exception:
                pass

            # Recompute counters after saving the upload so the UI can update without refresh.
            uploads_used = _uploads_used_today(chat_group, request.user)
            uploads_remaining = max(0, CHAT_UPLOAD_LIMIT_PER_ROOM - uploads_used)

            channel_layer = get_channel_layer()

            # Mention notifications from caption (best-effort)
            try:
                usernames = extract_mention_usernames(caption or '')
                if usernames:
                    mentioned = resolve_mentioned_users(usernames)
                    member_ids = None
                    if getattr(chat_group, 'group_name', '') != 'public-chat':
                        member_ids = set(chat_group.members.values_list('id', flat=True))
                    preview = (caption or message.filename or '')[:140]
                    for u in mentioned:
                        if not getattr(u, 'id', None) or u.id == request.user.id:
                            continue
                        if member_ids is not None and u.id not in member_ids:
                            continue

                        # DND: don't send notifications/push/calls to this user.
                        try:
                            from a_rtchat.notifications import should_send_realtime_notification

                            if not should_send_realtime_notification(user_id=u.id):
                                continue
                        except Exception:
                            pass

                        # Persist only if user is not online in this chat.
                        try:
                            from a_rtchat.notifications import should_persist_notification

                            if should_persist_notification(user_id=u.id, chatroom_name=chat_group.group_name) or bool(getattr(chat_group, 'is_private', False)):
                                Notification.objects.create(
                                    user=u,
                                    from_user=request.user,
                                    type='mention',
                                    chatroom_name=chat_group.group_name,
                                    message_id=message.id,
                                    preview=preview,
                                    url=f"/chat/room/{chat_group.group_name}#msg-{message.id}",
                                )
                        except Exception:
                            pass

                        async_to_sync(channel_layer.group_send)(
                            f"notify_user_{u.id}",
                            {
                                'type': 'mention_notify_handler',
                                'from_username': request.user.username,
                                'chatroom_name': chat_group.group_name,
                                'message_id': message.id,
                                'preview': preview,
                            },
                        )

                        # Optional: push notification via FCM (offline / background)
                        try:
                            from a_users.tasks import send_mention_push_task

                            # If Celery broker isn't configured (common in local/dev),
                            # don't enqueue tasks in-request (can block for seconds).
                            if _celery_broker_configured():
                                send_mention_push_task.delay(
                                    u.id,
                                    from_username=request.user.username,
                                    chatroom_name=chat_group.group_name,
                                    preview=preview,
                                )
                        except Exception:
                            pass
            except Exception:
                pass

            # Reply notification (caption upload doesn't support reply_to)

            # Broadcast to others; sender will render via HTMX response.
            async_to_sync(channel_layer.group_send)(
                chatroom_channel_group_name(chat_group),
                {
                    'type': 'message_handler',
                    'message_id': message.id,
                    'skip_sender': True,
                    'author_id': request.user.id,
                },
            )

            _attach_reaction_pills([message], request.user)
            attach_auto_badges([message], chat_group)
            verified_user_ids = get_verified_user_ids([getattr(request.user, 'id', None)])
            html = render(request, 'a_rtchat/chat_message.html', {
                'message': message,
                'user': request.user,
                'chat_group': chat_group,
                'reaction_emojis': CHAT_REACTION_EMOJIS,
                'other_last_read_id': other_last_read_id,
                'verified_user_ids': verified_user_ids,
            }).content.decode('utf-8')

            resp = HttpResponse(html, status=200)
            trigger = {
                'chatFileUploaded': True,
                'uploadCountUpdated': {
                    'used': uploads_used,
                    'limit': CHAT_UPLOAD_LIMIT_PER_ROOM,
                    'remaining': uploads_remaining,
                },
            }
            # If the user just hit the unverified message limit, lock the composer immediately.
            try:
                if _requires_verified_email_for_chat(request.user):
                    trigger['verify_required'] = {'reason': 'Verify your email to continue chatting.'}
            except Exception:
                pass
            resp.headers['HX-Trigger-After-Swap'] = json.dumps(trigger)
            return resp

        # Room-wide flood protection (applies to everyone in the room).
        room_rl = check_rate_limit(
            make_key('room_msg', chat_group.group_name),
            limit=int(getattr(settings, 'ROOM_MSG_RATE_LIMIT', 30)),
            period_seconds=int(getattr(settings, 'ROOM_MSG_RATE_PERIOD', 10)),
        )
        if not room_rl.allowed:
            record_abuse_violation(
                scope='room_flood',
                user_id=request.user.id,
                room=chat_group.group_name,
                window_seconds=int(getattr(settings, 'CHAT_ABUSE_WINDOW', 600)),
                threshold=int(getattr(settings, 'CHAT_ABUSE_STRIKE_THRESHOLD', 5)),
                mute_seconds=int(getattr(settings, 'CHAT_ABUSE_MUTE_SECONDS', 60)),
            )
            _log_blocked_message_event(
                user=request.user,
                chat_group=chat_group,
                scope='room_flood',
                status_code=429,
                retry_after=int(room_rl.retry_after),
            )
            resp = HttpResponse('', status=429)
            resp.headers['Retry-After'] = str(room_rl.retry_after)
            return resp

        # Duplicate message detection (same message spam).
        raw_body = (request.POST.get('body') or '').strip()

        # Commands: scoreboard (sender-only)
        # !sc -> your wins total
        # !sc @username -> other user's wins total
        try:
            parts = raw_body.split()
            if parts and parts[0].lower() == '!sc':
                target_user = request.user
                if len(parts) >= 2:
                    raw = (parts[1] or '').strip()
                    if raw.startswith('@'):
                        raw = raw[1:]
                    raw = raw.strip()
                    if raw:
                        user_model = get_user_model()
                        target_user = user_model.objects.filter(username__iexact=raw).only('id', 'username').first()
                        if not target_user:
                            html = render_to_string('a_rtchat/partials/challenge_event.html', {
                                'title': 'Score',
                                'body': f"User '@{raw}' not found.",
                            })
                            return HttpResponse(html, status=200)
                    else:
                        html = render_to_string('a_rtchat/partials/challenge_event.html', {
                            'title': 'Score',
                            'body': 'Usage: !sc  OR  !sc @username',
                        })
                        return HttpResponse(html, status=200)

                totals = get_win_loss_totals(getattr(target_user, 'id', 0), private_only=True)
                wins = int(totals.get('wins') or 0)
                losses = int(totals.get('losses') or 0)
                completed = int(totals.get('completed') or 0)
                name = getattr(target_user, 'username', 'User')
                html = render_to_string('a_rtchat/partials/challenge_event.html', {
                    'title': 'Score',
                    'body': f"@{name} • Wins: {wins} • Losses: {losses} • Completed: {completed}",
                })
                return HttpResponse(html, status=200)
        except Exception:
            pass

        # Challenges: enforce rules in HTMX/HTTP send path too (private chats only).
        # This prevents bypassing rules when websockets are unavailable.
        try:
            if getattr(chat_group, 'is_private', False) and raw_body:
                active = get_active_challenge(chat_group)
                if active:
                    # Lazily end expired challenges.
                    if challenge_end_if_expired(active):
                        try:
                            active.refresh_from_db()
                        except Exception:
                            pass

                        if getattr(active, 'status', '') != ChatChallenge.STATUS_ACTIVE:
                            meta = dict(getattr(active, 'meta', None) or {})
                            if not meta.get('ended_notified'):
                                meta['ended_notified'] = True
                                active.meta = meta
                                active.save(update_fields=['meta'])

                                winners = meta.get('winners') or []
                                losers = meta.get('losers') or []
                                html = render_to_string('a_rtchat/partials/challenge_event.html', {
                                    'title': 'Challenge ended',
                                    'body': f"Winners: {len(winners)} • Losers: {len(losers)}",
                                })
                                channel_layer = get_channel_layer()
                                async_to_sync(channel_layer.group_send)(
                                    chatroom_channel_group_name(chat_group),
                                    {
                                        'type': 'challenge_event_handler',
                                        'html': html,
                                        'state': challenge_public_state(active),
                                    },
                                )
                    else:
                        res = check_challenge_message(active, getattr(request.user, 'id', 0), raw_body)
                        if not res.allowed:
                            try:
                                display_name = request.user.profile.name
                            except Exception:
                                display_name = getattr(request.user, 'username', '') or 'User'

                            html = render_to_string('a_rtchat/partials/challenge_event.html', {
                                'title': 'Rule broken ❌',
                                'body': f"{display_name} lost: {res.reason}",
                            })
                            channel_layer = get_channel_layer()
                            async_to_sync(channel_layer.group_send)(
                                chatroom_channel_group_name(chat_group),
                                {
                                    'type': 'challenge_event_handler',
                                    'html': html,
                                    'state': challenge_public_state(active),
                                },
                            )

                            # If everyone lost, end early.
                            try:
                                member_ids = list(chat_group.members.values_list('id', flat=True))
                                losers = set((active.meta or {}).get('losers') or [])
                                if member_ids and losers.issuperset(set(member_ids)):
                                    ended = challenge_end(active)
                                    meta = dict(getattr(ended, 'meta', None) or {})
                                    if not meta.get('ended_notified'):
                                        meta['ended_notified'] = True
                                        ended.meta = meta
                                        ended.save(update_fields=['meta'])

                                        winners2 = meta.get('winners') or []
                                        losers2 = meta.get('losers') or []
                                        end_html = render_to_string('a_rtchat/partials/challenge_event.html', {
                                            'title': 'Challenge ended',
                                            'body': f"Winners: {len(winners2)} • Losers: {len(losers2)}",
                                        })
                                        async_to_sync(channel_layer.group_send)(
                                            chatroom_channel_group_name(chat_group),
                                            {
                                                'type': 'challenge_event_handler',
                                                'html': end_html,
                                                'state': challenge_public_state(ended),
                                            },
                                        )
                            except Exception:
                                pass

                            return HttpResponse('', status=400)

                        if res.ended:
                            try:
                                active.refresh_from_db()
                            except Exception:
                                pass

                            if getattr(active, 'status', '') != ChatChallenge.STATUS_ACTIVE:
                                meta = dict(getattr(active, 'meta', None) or {})
                                if not meta.get('ended_notified'):
                                    meta['ended_notified'] = True
                                    active.meta = meta
                                    active.save(update_fields=['meta'])

                                    winners3 = meta.get('winners') or []
                                    losers3 = meta.get('losers') or []
                                    end_html = render_to_string('a_rtchat/partials/challenge_event.html', {
                                        'title': 'Challenge ended',
                                        'body': f"Winners: {len(winners3)} • Losers: {len(losers3)}",
                                    })
                                    channel_layer = get_channel_layer()
                                    async_to_sync(channel_layer.group_send)(
                                        chatroom_channel_group_name(chat_group),
                                        {
                                            'type': 'challenge_event_handler',
                                            'html': end_html,
                                            'state': challenge_public_state(active),
                                        },
                                    )
        except Exception:
            pass

        gifs_allowed = not is_free_promotion_room(chat_group)
        gif_url = _parse_gif_message(raw_body or '')

        # If it *looks* like a GIF message but doesn't validate, block it.
        if raw_body and raw_body.strip().startswith('[GIF]'):
            if not gifs_allowed:
                resp = HttpResponse('', status=400)
                resp.headers['HX-Trigger'] = json.dumps({'linksNotAllowed': {'reason': 'GIFs are not allowed in this room.'}})
                return resp
            if not gif_url:
                resp = HttpResponse('', status=400)
                resp.headers['HX-Trigger'] = json.dumps({'linksNotAllowed': {'reason': 'Invalid GIF. Only Giphy GIFs are supported.'}})
                return resp

        # Links are only allowed in private chats (GIF is a special exception; not in Free Promotion).
        if raw_body and contains_link(raw_body) and not links_allowed:
            if not (gif_url and gifs_allowed):
                resp = HttpResponse('', status=400)
                resp.headers['HX-Trigger'] = json.dumps({'linksNotAllowed': {'reason': 'Links are only allowed in private chats.'}})
                return resp

        if raw_body:
            is_dup, dup_retry = is_duplicate_message(
                chat_group.group_name,
                request.user.id,
                raw_body,
                ttl_seconds=int(getattr(settings, 'DUPLICATE_MSG_TTL', 15)),
            )
            if is_dup:
                record_abuse_violation(
                    scope='dup_msg',
                    user_id=request.user.id,
                    room=chat_group.group_name,
                    window_seconds=int(getattr(settings, 'CHAT_ABUSE_WINDOW', 600)),
                    threshold=int(getattr(settings, 'CHAT_ABUSE_STRIKE_THRESHOLD', 5)),
                    mute_seconds=int(getattr(settings, 'CHAT_ABUSE_MUTE_SECONDS', 60)),
                    weight=2,
                )
                _log_blocked_message_event(
                    user=request.user,
                    chat_group=chat_group,
                    scope='dup_msg',
                    status_code=429,
                    retry_after=int(dup_retry),
                    text=raw_body,
                )
                resp = HttpResponse('', status=429)
                resp.headers['Retry-After'] = str(dup_retry)
                return resp

            # Same emoji spam (e.g., 🤡🤡🤡🤡)
            is_emoji_spam, emoji_retry = is_same_emoji_spam(
                raw_body,
                min_repeats=int(getattr(settings, 'EMOJI_SPAM_MIN_REPEATS', 4)),
                ttl_seconds=int(getattr(settings, 'EMOJI_SPAM_TTL', 15)),
            )
            if is_emoji_spam:
                _, muted3 = record_abuse_violation(
                    scope='emoji_spam',
                    user_id=request.user.id,
                    room=chat_group.group_name,
                    window_seconds=int(getattr(settings, 'CHAT_ABUSE_WINDOW', 600)),
                    threshold=int(getattr(settings, 'CHAT_ABUSE_STRIKE_THRESHOLD', 5)),
                    mute_seconds=int(getattr(settings, 'CHAT_ABUSE_MUTE_SECONDS', 60)),
                    weight=2,
                )
                _log_blocked_message_event(
                    user=request.user,
                    chat_group=chat_group,
                    scope='emoji_spam',
                    status_code=429,
                    retry_after=int(muted3 or emoji_retry),
                    auto_muted_seconds=int(muted3 or 0),
                    text=raw_body,
                )
                resp = HttpResponse('', status=429)
                resp.headers['Retry-After'] = str(muted3 or emoji_retry)
                return resp

            # Bot-like typing speed / copy-paste heuristic (client-reported typed_ms).
            typed_ms_raw = (request.POST.get('typed_ms') or '').strip()
            try:
                typed_ms = int(typed_ms_raw) if typed_ms_raw else None
            except ValueError:
                typed_ms = None

            long_len = int(getattr(settings, 'PASTE_LONG_MSG_LEN', 60))
            paste_ms = int(getattr(settings, 'PASTE_TYPED_MS_MAX', 400))
            cps_threshold = int(getattr(settings, 'TYPING_CPS_THRESHOLD', 25))

            if typed_ms is not None and typed_ms >= 0:
                seconds = max(0.001, typed_ms / 1000.0)
                cps = len(raw_body) / seconds
                if (len(raw_body) >= long_len and typed_ms <= paste_ms) or (len(raw_body) >= 20 and cps >= cps_threshold):
                    _, muted4 = record_abuse_violation(
                        scope='typing_speed',
                        user_id=request.user.id,
                        room=chat_group.group_name,
                        window_seconds=int(getattr(settings, 'CHAT_ABUSE_WINDOW', 600)),
                        threshold=int(getattr(settings, 'CHAT_ABUSE_STRIKE_THRESHOLD', 5)),
                        mute_seconds=int(getattr(settings, 'CHAT_ABUSE_MUTE_SECONDS', 60)),
                        weight=2,
                    )
                    _log_blocked_message_event(
                        user=request.user,
                        chat_group=chat_group,
                        scope='typing_speed',
                        status_code=429,
                        retry_after=int(muted4 or int(getattr(settings, 'SPEED_SPAM_TTL', 10))),
                        auto_muted_seconds=int(muted4 or 0),
                        text=raw_body,
                        meta={
                            'typed_ms': int(typed_ms),
                            'cps': float(cps),
                        },
                    )
                    resp = HttpResponse('', status=429)
                    resp.headers['Retry-After'] = str(muted4 or int(getattr(settings, 'SPEED_SPAM_TTL', 10)))
                    return resp

            # Server-side fast long message heuristic (works even if JS metadata is missing).
            is_fast, fast_retry = is_fast_long_message(
                chat_group.group_name,
                request.user.id,
                message_length=len(raw_body),
                long_length_threshold=int(getattr(settings, 'FAST_LONG_MSG_LEN', 80)),
                min_interval_seconds=int(getattr(settings, 'FAST_LONG_MSG_MIN_INTERVAL', 1)),
            )
            if is_fast:
                _, muted5 = record_abuse_violation(
                    scope='fast_long_msg',
                    user_id=request.user.id,
                    room=chat_group.group_name,
                    window_seconds=int(getattr(settings, 'CHAT_ABUSE_WINDOW', 600)),
                    threshold=int(getattr(settings, 'CHAT_ABUSE_STRIKE_THRESHOLD', 5)),
                    mute_seconds=int(getattr(settings, 'CHAT_ABUSE_MUTE_SECONDS', 60)),
                )
                _log_blocked_message_event(
                    user=request.user,
                    chat_group=chat_group,
                    scope='fast_long_msg',
                    status_code=429,
                    retry_after=int(muted5 or fast_retry),
                    auto_muted_seconds=int(muted5 or 0),
                    text=raw_body,
                )
                resp = HttpResponse('', status=429)
                resp.headers['Retry-After'] = str(muted5 or fast_retry)
                return resp

        # Rate limit message sends (HTMX path).
        # Burst spam: 5 messages within 3 seconds -> 10 seconds cooldown.
        burst_limit = int(getattr(settings, 'CHAT_BURST_MSG_LIMIT', 5))
        burst_period = int(getattr(settings, 'CHAT_BURST_MSG_PERIOD', 3))
        burst_cooldown = int(getattr(settings, 'CHAT_BURST_COOLDOWN_SECONDS', 10))
        burst_key = make_key('chat_burst', chat_group.group_name, request.user.id)
        burst = check_rate_limit(burst_key, limit=burst_limit, period_seconds=burst_period)
        burst_count = int(getattr(burst, 'count', 0) or 0)
        burst_should_purge = burst_count >= max(1, int(burst_limit))
        if burst_should_purge:
            # Cooldown is a simple short mute; doesn't count as a "strike".
            try:
                set_muted(request.user.id, burst_cooldown)
            except Exception:
                pass

        if not burst_should_purge:
            rl_limit = int(getattr(settings, 'CHAT_MSG_RATE_LIMIT', 8))
            rl_period = int(getattr(settings, 'CHAT_MSG_RATE_PERIOD', 10))
            rl_key = make_key('chat_msg', chat_group.group_name, request.user.id)
            rl = check_rate_limit(rl_key, limit=rl_limit, period_seconds=rl_period)
            if not rl.allowed:
                # Repeated violations -> auto-mute/cooldown
                ua_missing = 1 if not (request.META.get('HTTP_USER_AGENT') or '').strip() else 0
                weight = 2 if ua_missing else 1
                _, muted = record_abuse_violation(
                    scope='chat_send',
                    user_id=request.user.id,
                    room=chat_group.group_name,
                    window_seconds=int(getattr(settings, 'CHAT_ABUSE_WINDOW', 600)),
                    threshold=int(getattr(settings, 'CHAT_ABUSE_STRIKE_THRESHOLD', 5)),
                    mute_seconds=int(getattr(settings, 'CHAT_ABUSE_MUTE_SECONDS', 60)),
                    weight=weight,
                )
                resp = HttpResponse('', status=429)
                resp.headers['Retry-After'] = str(muted or rl.retry_after)
                _log_blocked_message_event(
                    user=request.user,
                    chat_group=chat_group,
                    scope='chat_send',
                    status_code=429,
                    retry_after=int(muted or rl.retry_after),
                    auto_muted_seconds=int(muted or 0),
                    text=(request.POST.get('body') or ''),
                    meta={
                        'ua_missing': int(ua_missing),
                    },
                )
                return resp

        # AI moderation (Gemini): run after cheap anti-spam checks but before saving.
        # Default is OFF for performance unless explicitly enabled.
        pending_moderation = None
        if raw_body and int(getattr(settings, 'AI_MODERATION_ENABLED', 0)):
            last_user_msgs = list(
                chat_group.chat_messages.filter(author=request.user)
                .exclude(body__isnull=True)
                .exclude(body='')
                .order_by('-created')
                .values_list('body', flat=True)[:3]
            )
            last_room_msgs = list(
                chat_group.chat_messages
                .exclude(body__isnull=True)
                .exclude(body='')
                .order_by('-created')
                .values_list('body', flat=True)[:3]
            )

            ctx = {
                'room': chat_group.group_name,
                'is_private': bool(getattr(chat_group, 'is_private', False)),
                'user_id': request.user.id,
                'username': request.user.username,
                'typed_ms': typed_ms,
                'ip': get_client_ip(request),
                'recent_user_messages': list(reversed(last_user_msgs)),
                'recent_room_messages': list(reversed(last_room_msgs)),
            }
            decision = moderate_message(text=raw_body, context=ctx)

            # Decide action
            min_block_sev = int(getattr(settings, 'AI_BLOCK_MIN_SEVERITY', 3))
            min_flag_sev = int(getattr(settings, 'AI_FLAG_MIN_SEVERITY', 1))
            action = decision.action
            if decision.severity >= min_block_sev:
                action = 'block'
            elif decision.severity >= min_flag_sev and action == 'allow' and decision.categories:
                action = 'flag'

            log_all = bool(int(getattr(settings, 'AI_LOG_ALL', 0)))
            # For allow/flag we prefer to attach the moderation record to the saved message.
            if log_all or action == 'flag':
                pending_moderation = (decision, action)

            if action == 'block':
                ModerationEvent.objects.create(
                    user=request.user,
                    room=chat_group,
                    message=None,
                    text=raw_body[:2000],
                    action='block',
                    categories=decision.categories,
                    severity=decision.severity,
                    confidence=decision.confidence,
                    reason=decision.reason,
                    source='gemini',
                    meta={
                        'model_action': decision.action,
                        'suggested_mute_seconds': decision.suggested_mute_seconds,
                    },
                )

                # Repeat offender tracking: severity adds weight.
                weight = 1 + int(decision.severity >= 2)
                _, auto_muted = record_abuse_violation(
                    scope='ai_block',
                    user_id=request.user.id,
                    room=chat_group.group_name,
                    window_seconds=int(getattr(settings, 'AI_ABUSE_WINDOW', 24 * 60 * 60)),
                    threshold=int(getattr(settings, 'AI_STRIKE_THRESHOLD', 3)),
                    mute_seconds=int(getattr(settings, 'AI_AUTO_MUTE_SECONDS', 5 * 60)),
                    weight=weight,
                )
                suggested = int(decision.suggested_mute_seconds or 0)
                if suggested > 0:
                    set_muted(request.user.id, suggested)
                    auto_muted = max(auto_muted, suggested)

                resp = HttpResponse('', status=429 if auto_muted else 403)
                if auto_muted:
                    resp.headers['Retry-After'] = str(auto_muted)
                # HTMX event for UI feedback
                reason = (decision.reason or 'Message blocked by moderation.')
                resp.headers['HX-Trigger'] = json.dumps({'moderationBlocked': {'reason': reason}})

                _log_blocked_message_event(
                    user=request.user,
                    chat_group=chat_group,
                    scope='ai_block',
                    status_code=int(getattr(resp, 'status_code', 0) or 0),
                    retry_after=int(auto_muted or 0),
                    auto_muted_seconds=int(auto_muted or 0),
                    text=raw_body,
                    meta={
                        'categories': list(decision.categories or []),
                        'severity': int(decision.severity or 0),
                        'confidence': float(decision.confidence or 0.0),
                    },
                )
                return resp

            if action == 'flag':
                # Flagging does not block, but increases strike weight slightly.
                record_abuse_violation(
                    scope='ai_flag',
                    user_id=request.user.id,
                    room=chat_group.group_name,
                    window_seconds=int(getattr(settings, 'AI_ABUSE_WINDOW', 24 * 60 * 60)),
                    threshold=int(getattr(settings, 'AI_STRIKE_THRESHOLD', 3)),
                    mute_seconds=int(getattr(settings, 'AI_AUTO_MUTE_SECONDS', 5 * 60)),
                    weight=1,
                )

        form = ChatmessageCreateForm(request.POST)
        if form.is_valid(): # Fix: Added brackets ()
            message = form.save(commit=False)
            message.author = request.user
            message.group = chat_group

            # Meme Central: enforce a per-message cooldown.
            if is_meme_central_room(chat_group):
                cd = check_rate_limit(
                    make_key('chat_cd', chat_group.group_name, request.user.id),
                    limit=1,
                    period_seconds=3,
                )
                if not cd.allowed:
                    _log_blocked_message_event(
                        user=request.user,
                        chat_group=chat_group,
                        scope='chat_cooldown',
                        status_code=429,
                        retry_after=int(cd.retry_after),
                        text=(raw_body or ''),
                        meta={
                            'cooldown_seconds': 3,
                            'via': 'message',
                        },
                    )
                    resp = HttpResponse('', status=429)
                    resp.headers['Retry-After'] = str(cd.retry_after)
                    return resp

            # Free Promotion: enforce a strict 60-second cooldown between sends.
            if is_free_promotion_room(chat_group):
                cd = check_rate_limit(
                    make_key('chat_cd', chat_group.group_name, request.user.id),
                    limit=1,
                    period_seconds=60,
                )
                if not cd.allowed:
                    _log_blocked_message_event(
                        user=request.user,
                        chat_group=chat_group,
                        scope='chat_cooldown',
                        status_code=429,
                        retry_after=int(cd.retry_after),
                        text=(raw_body or ''),
                        meta={
                            'cooldown_seconds': 60,
                            'via': 'message',
                        },
                    )
                    resp = HttpResponse('', status=429)
                    resp.headers['Retry-After'] = str(cd.retry_after)
                    return resp

            reply_to_id = (request.POST.get('reply_to_id') or '').strip()
            if reply_to_id:
                try:
                    reply_to_pk = int(reply_to_id)
                except ValueError:
                    reply_to_pk = None
                if reply_to_pk:
                    reply_to = GroupMessage.objects.filter(pk=reply_to_pk, group=chat_group).first()
                    if reply_to:
                        message.reply_to = reply_to
            message.save()

            if burst_should_purge:
                deleted_ids = []
                try:
                    cutoff = timezone.now() - timedelta(seconds=max(1, int(burst_period)))
                    deleted_ids = list(
                        GroupMessage.objects
                        .filter(group=chat_group, author=request.user, created__gte=cutoff)
                        .order_by('-created')
                        .values_list('id', flat=True)[:50]
                    )
                    if deleted_ids:
                        GroupMessage.objects.filter(id__in=deleted_ids, group=chat_group, author=request.user).delete()

                        # Realtime: remove from all connected clients (including sender).
                        try:
                            channel_layer = get_channel_layer()
                            for mid in deleted_ids:
                                async_to_sync(channel_layer.group_send)(
                                    chatroom_channel_group_name(chat_group),
                                    {
                                        'type': 'message_delete_handler',
                                        'message_id': int(mid),
                                    },
                                )
                        except Exception:
                            pass
                except Exception:
                    deleted_ids = []

                _log_blocked_message_event(
                    user=request.user,
                    chat_group=chat_group,
                    scope='chat_send',
                    status_code=429,
                    retry_after=int(burst_cooldown),
                    auto_muted_seconds=int(burst_cooldown),
                    text=(raw_body or ''),
                    meta={
                        'reason': 'burst',
                        'limit': int(burst_limit),
                        'period_seconds': int(burst_period),
                        'cooldown_seconds': int(burst_cooldown),
                        'count': int(burst_count),
                        'deleted_count': int(len(deleted_ids or [])),
                    },
                )

                resp = HttpResponse('', status=429)
                resp.headers['Retry-After'] = str(burst_cooldown)
                return resp

            # Retention: keep only the newest messages per room (best-effort).
            # Public/group rooms and private rooms can use different caps.
            try:
                from a_rtchat.retention import trim_chat_group_messages

                is_private = bool(getattr(chat_group, 'is_private', False))
                if is_private:
                    keep_last = int(getattr(settings, 'PRIVATE_CHAT_MAX_MESSAGES_PER_ROOM', 1000))
                else:
                    keep_last = int(getattr(settings, 'CHAT_MAX_MESSAGES_PER_ROOM', 300))

                trim_chat_group_messages(
                    chat_group_id=chat_group.id,
                    keep_last=max(1, keep_last),
                )
            except Exception:
                pass

            # Public chat bot (Natasha): reply occasionally, async.
            try:
                if (getattr(chat_group, 'group_name', '') == 'public-chat'
                        and getattr(request.user, 'username', '') != NATASHA_USERNAME):
                    trigger_natasha_reply_after_commit(chat_group.id, message.id)
            except Exception:
                pass

            channel_layer = get_channel_layer()

            # Mention notifications (best-effort)
            try:
                usernames = extract_mention_usernames(raw_body or '')
                if usernames:
                    mentioned = resolve_mentioned_users(usernames)
                    member_ids = None
                    if getattr(chat_group, 'group_name', '') != 'public-chat':
                        member_ids = set(chat_group.members.values_list('id', flat=True))

                    preview = (raw_body or '')[:140]
                    for u in mentioned:
                        if not getattr(u, 'id', None) or u.id == request.user.id:
                            continue
                        if member_ids is not None and u.id not in member_ids:
                            continue

                        # DND: don't send notifications/push/calls to this user.
                        try:
                            from a_rtchat.notifications import should_send_realtime_notification

                            if not should_send_realtime_notification(user_id=u.id):
                                continue
                        except Exception:
                            pass

                        # Persist notification only if user is offline (not connected in any chat WS).
                        try:
                            from a_rtchat.notifications import should_persist_notification

                            if should_persist_notification(user_id=u.id, chatroom_name=chat_group.group_name) or bool(getattr(chat_group, 'is_private', False)):
                                Notification.objects.create(
                                    user=u,
                                    from_user=request.user,
                                    type='mention',
                                    chatroom_name=chat_group.group_name,
                                    message_id=message.id,
                                    preview=preview,
                                    url=f"/chat/room/{chat_group.group_name}#msg-{message.id}",
                                )
                        except Exception:
                            pass

                        async_to_sync(channel_layer.group_send)(
                            f"notify_user_{u.id}",
                            {
                                'type': 'mention_notify_handler',
                                'from_username': request.user.username,
                                'chatroom_name': chat_group.group_name,
                                'message_id': message.id,
                                'preview': preview,
                            },
                        )

                        # Optional: push notification via FCM (offline / background)
                        try:
                            from a_users.tasks import send_mention_push_task

                            if _celery_broker_configured():
                                send_mention_push_task.delay(
                                    u.id,
                                    from_username=request.user.username,
                                    chatroom_name=chat_group.group_name,
                                    preview=preview,
                                )
                        except Exception:
                            pass
            except Exception:
                pass

            # Reply notification (best-effort)
            try:
                reply_to = getattr(message, 'reply_to', None)
                if reply_to and getattr(reply_to, 'author_id', None) and reply_to.author_id != request.user.id:
                    target_id = int(reply_to.author_id)
                    preview = (raw_body or '')[:140]

                    allow_realtime = True
                    try:
                        from a_rtchat.notifications import should_send_realtime_notification

                        allow_realtime = bool(should_send_realtime_notification(user_id=target_id))
                    except Exception:
                        allow_realtime = True

                    try:
                        from a_rtchat.notifications import should_persist_notification

                        if should_persist_notification(user_id=target_id, chatroom_name=chat_group.group_name) or bool(getattr(chat_group, 'is_private', False)):
                            Notification.objects.create(
                                user_id=target_id,
                                from_user=request.user,
                                type='reply',
                                chatroom_name=chat_group.group_name,
                                message_id=message.id,
                                preview=preview,
                                url=f"/chat/room/{chat_group.group_name}#msg-{message.id}",
                            )
                    except Exception:
                        pass

                    if allow_realtime:
                        async_to_sync(channel_layer.group_send)(
                            f"notify_user_{target_id}",
                            {
                                'type': 'reply_notify_handler',
                                'from_username': request.user.username,
                                'chatroom_name': chat_group.group_name,
                                'message_id': message.id,
                                'preview': preview,
                            },
                        )
            except Exception:
                pass

            if pending_moderation:
                decision, action = pending_moderation
                ModerationEvent.objects.create(
                    user=request.user,
                    room=chat_group,
                    message=message,
                    text=raw_body[:2000],
                    action=action,
                    categories=decision.categories,
                    severity=decision.severity,
                    confidence=decision.confidence,
                    reason=decision.reason,
                    source='gemini',
                    meta={
                        'model_action': decision.action,
                        'suggested_mute_seconds': decision.suggested_mute_seconds,
                        'linked': True,
                    },
                )

            # Broadcast to websocket listeners (including sender) so the message appears instantly
            channel_layer = get_channel_layer()

            # Broadcast to others; sender will render via HTMX response.
            async_to_sync(channel_layer.group_send)(
                chatroom_channel_group_name(chat_group),
                {
                    'type': 'message_handler',
                    'message_id': message.id,
                    'skip_sender': True,
                    'author_id': request.user.id,
                },
            )

            _attach_reaction_pills([message], request.user)
            attach_auto_badges([message], chat_group)
            verified_user_ids = get_verified_user_ids([getattr(request.user, 'id', None)])
            html = render(request, 'a_rtchat/chat_message.html', {
                'message': message,
                'user': request.user,
                'chat_group': chat_group,
                'reaction_emojis': CHAT_REACTION_EMOJIS,
                'other_last_read_id': other_last_read_id,
                'verified_user_ids': verified_user_ids,
            }).content.decode('utf-8')

            resp = HttpResponse(html, status=200)
            # If the user just hit the unverified message limit, lock the composer immediately.
            try:
                if _requires_verified_email_for_chat(request.user):
                    resp.headers['HX-Trigger-After-Swap'] = json.dumps({
                        'verify_required': {
                            'reason': 'Verify your email to continue chatting.',
                        },
                    })
            except Exception:
                pass
            return resp

        # Invalid (e.g., empty/whitespace) message -> do nothing
        return HttpResponse('', status=204)
    
    sidebar_groupchats_qs = (
        ChatGroup.objects
        .filter(groupchat_name__isnull=False)
        .exclude(group_name='online-status')
        .order_by('groupchat_name')
    )
    sidebar_groupchats = list(sidebar_groupchats_qs)
    sidebar_groupchat_sections, sidebar_groupchats_remaining = _build_groupchat_sections(sidebar_groupchats)

    needs_email_verification_for_chat = False
    try:
        needs_email_verification_for_chat = _requires_verified_email_for_chat(request.user)
    except Exception:
        needs_email_verification_for_chat = False

    context = {
        'chat_messages' : chat_messages, 
        'has_older_messages': has_older_messages,
        'form' : form,
        'other_user' : other_user,
        'other_last_read_id': other_last_read_id,
        'chatroom_name' : chatroom_name,
        'chat_group' : chat_group,
        'chat_group_members': [],
        'verified_user_ids': verified_user_ids,
        'chat_blocked': chat_blocked,
        'chat_muted_seconds': chat_muted_seconds,
        'needs_email_verification_for_chat': needs_email_verification_for_chat,
        # Show all group chats so admin-created rooms appear in UI even before the user joins.
        'sidebar_groupchats': sidebar_groupchats,
        'sidebar_groupchat_sections': sidebar_groupchat_sections,
        'sidebar_groupchats_remaining': sidebar_groupchats_remaining,
        'sidebar_privatechats': [] if chat_blocked else request.user.chat_groups.filter(is_private=True, is_code_room=False).exclude(group_name='online-status'),
        'sidebar_code_rooms': [] if chat_blocked else request.user.chat_groups.filter(is_private=True, is_code_room=True).exclude(group_name='online-status'),
        'private_room_create_form': PrivateRoomCreateForm(),
        'room_code_join_form': RoomCodeJoinForm(),
        'uploads_used': uploads_used,
        'uploads_remaining': uploads_remaining,
        'upload_limit': CHAT_UPLOAD_LIMIT_PER_ROOM,
        'links_allowed': links_allowed,
        'uploads_allowed': uploads_allowed,
        'reaction_emojis': CHAT_REACTION_EMOJIS,
    }

    # Members list for UI (prefetch profile to avoid N+1 in templates)
    try:
        context['chat_group_members'] = list(chat_group.members.select_related('profile').all())
    except Exception:
        context['chat_group_members'] = []

    # Waiting list count for admin/staff (code rooms only)
    try:
        if getattr(chat_group, 'is_private', False) and getattr(chat_group, 'is_code_room', False) and (
            request.user == getattr(chat_group, 'admin', None) or request.user.is_staff
        ):
            cutoff = _code_room_waiting_cutoff()
            context['code_room_waiting_count'] = CodeRoomJoinRequest.objects.filter(
                room=chat_group,
                admitted_at__isnull=True,
                last_seen_at__gte=cutoff,
            ).count()
        else:
            context['code_room_waiting_count'] = 0
    except Exception:
        context['code_room_waiting_count'] = 0

    # Dynamic badges under username (computed per author in the loaded message set)
    try:
        attach_auto_badges(chat_messages, chat_group)
    except Exception:
        pass

    # Embed chat JS config directly in the page so chat features work even if
    # external CDNs fail or the separate /chat/config fetch is blocked.
    try:
        me_profile = getattr(request.user, 'profile', None)
    except Exception:
        me_profile = None
    try:
        other_profile = getattr(other_user, 'profile', None) if other_user else None
    except Exception:
        other_profile = None

    def _safe_avatar(profile_obj):
        try:
            return getattr(profile_obj, 'avatar', '') if profile_obj else ''
        except Exception:
            return ''

    try:
        me_display = (getattr(me_profile, 'name', None) or request.user.username)
    except Exception:
        me_display = request.user.username

    other_display = ''
    if other_user:
        try:
            other_display = (getattr(other_profile, 'name', None) or other_user.username)
        except Exception:
            other_display = other_user.username

    context['chat_config'] = {
        'chatroomName': chatroom_name,
        'currentUserId': getattr(request.user, 'id', 0) or 0,
        'currentUsername': request.user.username,
        'otherLastReadId': int(other_last_read_id or 0),
        'pollUrl': reverse('chat-poll', args=[chatroom_name]),
        'olderUrl': reverse('chat-older', args=[chatroom_name]),
        'inviteUrl': reverse('chat-call-invite', args=[chatroom_name]),
        'tokenUrl': reverse('agora-token', args=[chatroom_name]),
        'presenceUrl': reverse('chat-call-presence', args=[chatroom_name]),
        'callEventUrl': reverse('chat-call-event', args=[chatroom_name]),
        'messageEditUrlTemplate': reverse('message-edit', args=[0]),
        'messageDeleteUrlTemplate': reverse('message-delete', args=[0]),
        'messageReactUrlTemplate': reverse('message-react', args=[0]),
        'mentionSearchUrl': reverse('mention-search'),
        'chatMutedSeconds': int(chat_muted_seconds or 0),
        'otherUsername': other_user.username if other_user else '',
        'meDisplayName': me_display,
        'meAvatarUrl': _safe_avatar(me_profile),
        'otherDisplayName': other_display,
        'otherAvatarUrl': _safe_avatar(other_profile),
        'linksAllowed': bool(links_allowed),
        'gifsAllowed': bool(gifs_allowed),
        'giphyApiKey': 'mA2NToNf2QW36bSdNgOVfdmUj7w6W7sz',
        'giphyLimit': 30,
        'chatBlocked': bool(chat_blocked),
    }

    context['gifs_allowed'] = bool(gifs_allowed)
    
    return render(request, 'a_rtchat/chat.html', context)


@login_required
def chat_config_view(request, chatroom_name):
    """Return JSON config for the chat UI (consumed by static JS)."""
    if _is_chat_banned(request.user):
        return JsonResponse({'error': 'banned'}, status=403)

    # Only auto-create the global public chat. All other rooms must already exist.
    if chatroom_name == 'public-chat':
        chat_group, _created = ChatGroup.objects.get_or_create(group_name=chatroom_name)
    else:
        try:
            chat_group = ChatGroup.objects.get(group_name=chatroom_name)
        except ChatGroup.DoesNotExist:
            return JsonResponse({'error': 'chatroom_closed'}, status=404)

    chat_blocked = _is_chat_blocked(request.user)
    chat_muted_seconds = get_muted_seconds(getattr(request.user, 'id', 0))

    other_user = None
    if getattr(chat_group, 'is_private', False):
        if chat_blocked:
            return JsonResponse({'error': 'blocked'}, status=403)
        if request.user not in chat_group.members.all():
            raise Http404()
        for member in chat_group.members.all():
            if member != request.user:
                other_user = member
                break

    other_last_read_id = 0
    if other_user and getattr(chat_group, 'is_private', False):
        try:
            from .models import ChatReadState

            other_last_read_id = int(
                ChatReadState.objects.filter(user=other_user, group=chat_group)
                .values_list('last_read_message_id', flat=True)
                .first()
                or 0
            )
        except Exception:
            other_last_read_id = 0

    # Group chat auto-join behavior (match chat_view)
    if getattr(chat_group, 'groupchat_name', None):
        if request.user not in chat_group.members.all() and not chat_blocked:
            email_verification = str(getattr(settings, 'ACCOUNT_EMAIL_VERIFICATION', 'optional')).lower()
            if email_verification == 'mandatory':
                email_qs = request.user.emailaddress_set.all()
                if email_qs.filter(verified=True).exists():
                    chat_group.members.add(request.user)
                else:
                    return JsonResponse({'error': 'verify_email_required'}, status=403)
            else:
                chat_group.members.add(request.user)

    links_allowed = room_allows_links(chat_group)
    gifs_allowed = not is_free_promotion_room(chat_group)

    def _safe_profile(user):
        try:
            return getattr(user, 'profile', None)
        except Exception:
            return None

    me_profile = _safe_profile(request.user)
    other_profile = _safe_profile(other_user) if other_user else None

    me_display = (getattr(me_profile, 'name', None) or request.user.username)
    other_display = ''
    if other_user:
        other_display = (getattr(other_profile, 'name', None) or other_user.username)

    def _safe_avatar(profile_obj):
        try:
            return getattr(profile_obj, 'avatar', '') if profile_obj else ''
        except Exception:
            return ''

    data = {
        'chatroomName': chatroom_name,
        'currentUserId': getattr(request.user, 'id', 0) or 0,
        'currentUsername': request.user.username,
        'otherLastReadId': other_last_read_id,
        'pollUrl': reverse('chat-poll', args=[chatroom_name]),
        'olderUrl': reverse('chat-older', args=[chatroom_name]),
        'inviteUrl': reverse('chat-call-invite', args=[chatroom_name]),
        'tokenUrl': reverse('agora-token', args=[chatroom_name]),
        'presenceUrl': reverse('chat-call-presence', args=[chatroom_name]),
        'callEventUrl': reverse('chat-call-event', args=[chatroom_name]),
        'messageEditUrlTemplate': reverse('message-edit', args=[0]),
        'messageDeleteUrlTemplate': reverse('message-delete', args=[0]),
        'messageReactUrlTemplate': reverse('message-react', args=[0]),
        'mentionSearchUrl': reverse('mention-search'),
        'chatMutedSeconds': int(chat_muted_seconds or 0),
        'otherUsername': other_user.username if other_user else '',
        'meDisplayName': me_display,
        'meAvatarUrl': _safe_avatar(me_profile),
        'otherDisplayName': other_display,
        'otherAvatarUrl': _safe_avatar(other_profile),
        'linksAllowed': bool(links_allowed),
        'gifsAllowed': bool(gifs_allowed),
        'giphyApiKey': 'mA2NToNf2QW36bSdNgOVfdmUj7w6W7sz',
        'giphyLimit': 30,
    }
    return JsonResponse(data)


@login_required
def chat_older_view(request, chatroom_name):
    """Return older messages before a given id (paged history fetch)."""
    if _is_chat_banned(request.user):
        return JsonResponse(
            {'messages_html': '', 'oldest_id': request.GET.get('before'), 'has_more': False},
            status=403,
        )

    if chatroom_name == 'public-chat':
        chat_group, _created = ChatGroup.objects.get_or_create(group_name=chatroom_name)
    else:
        chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name)

    # Permission checks (same intent as chat_view/chat_poll_view)
    if _is_chat_blocked(request.user) and getattr(chat_group, 'is_private', False):
        raise Http404()
    if chat_group.is_private and request.user not in chat_group.members.all():
        raise Http404()
    if chat_group.groupchat_name and request.user not in chat_group.members.all():
        if _is_chat_blocked(request.user):
            pass
        else:
            email_verification = str(getattr(settings, 'ACCOUNT_EMAIL_VERIFICATION', 'optional')).lower()
            if email_verification == 'mandatory':
                if request.user.emailaddress_set.filter(verified=True).exists():
                    chat_group.members.add(request.user)
                else:
                    return JsonResponse({'messages_html': '', 'oldest_id': request.GET.get('before'), 'has_more': False}, status=403)
            else:
                chat_group.members.add(request.user)

    # Rate limit history fetches (reuse poll limits by default).
    rl = check_rate_limit(
        make_key('chat_older', chat_group.group_name, request.user.id),
        limit=int(getattr(settings, 'CHAT_POLL_RATE_LIMIT', 240)),
        period_seconds=int(getattr(settings, 'CHAT_POLL_RATE_PERIOD', 60)),
    )
    if not rl.allowed:
        try:
            before_id = int(request.GET.get('before', '0'))
        except ValueError:
            before_id = 0
        return JsonResponse({'messages_html': '', 'oldest_id': before_id, 'has_more': True})

    try:
        before_id = int(request.GET.get('before', '0'))
    except ValueError:
        before_id = 0
    if before_id <= 0:
        return JsonResponse({'messages_html': '', 'oldest_id': before_id, 'has_more': False})

    page_size = int(getattr(settings, 'CHAT_HISTORY_PAGE_SIZE', 50))
    if page_size <= 0:
        page_size = 50
    page_size = max(10, min(page_size, 200))

    qs = chat_group.chat_messages.filter(id__lt=before_id).order_by('-id')
    batch = list(qs[:page_size])
    if not batch:
        return JsonResponse({'messages_html': '', 'oldest_id': before_id, 'has_more': False})

    batch.reverse()
    _attach_reaction_pills(batch, request.user)
    _attach_one_time_view_flags(batch, request.user)

    verified_user_ids = set()
    try:
        author_ids = {getattr(m, 'author_id', None) for m in (batch or [])}
        author_ids = {x for x in author_ids if x}
        author_ids.add(getattr(request.user, 'id', None))
        verified_user_ids = get_verified_user_ids(author_ids)
    except Exception:
        verified_user_ids = set()

    parts = []
    prev = None
    for message in batch:
        parts.append(
            render(
                request,
                'a_rtchat/chat_message.html',
                {
                    'message': message,
                    'user': request.user,
                    'chat_group': chat_group,
                    'reaction_emojis': CHAT_REACTION_EMOJIS,
                    'verified_user_ids': verified_user_ids,
                    'prev_message': prev,
                },
            ).content.decode('utf-8')
        )
        prev = message

    oldest_id = int(getattr(batch[0], 'id', 0) or 0)
    has_more = False
    try:
        if oldest_id:
            has_more = chat_group.chat_messages.filter(id__lt=oldest_id).exists()
    except Exception:
        has_more = False

    return JsonResponse({'messages_html': ''.join(parts), 'oldest_id': oldest_id, 'has_more': has_more})


@login_required
def call_config_view(request, chatroom_name):
    """Return JSON config for the call UI (consumed by static JS)."""
    chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name)

    if _is_chat_blocked(request.user):
        raise Http404()
    if not getattr(chat_group, 'is_private', False):
        raise Http404()
    if request.user not in chat_group.members.all():
        raise Http404()

    call_type = (request.GET.get('type') or 'voice').lower()
    if call_type not in {'voice', 'video'}:
        call_type = 'voice'

    role = (request.GET.get('role') or 'caller').lower()
    if role not in {'caller', 'callee'}:
        role = 'caller'

    member_usernames = list(chat_group.members.values_list('username', flat=True))

    return JsonResponse({
        'callType': call_type,
        'channel': chatroom_name,
        'callRole': role,
        'currentUsername': request.user.username,
        'tokenUrl': reverse('agora-token', args=[chatroom_name]),
        'presenceUrl': reverse('chat-call-presence', args=[chatroom_name]),
        'callEventUrl': reverse('chat-call-event', args=[chatroom_name]),
        'backUrl': reverse('chatroom', args=[chatroom_name]),
        'memberUsernames': member_usernames,
    })


@login_required
def create_private_room(request):
    if request.method != 'POST':
        return redirect('home')

    if _is_chat_blocked(request.user):
        messages.error(request, 'You are blocked from creating private rooms.')
        return redirect('home')

    # Without verified email, allow creating only a small number of private rooms.
    # This reduces abuse while still letting new users try the feature.
    try:
        limit = int(getattr(settings, 'UNVERIFIED_PRIVATE_ROOM_CREATE_LIMIT', 2))
    except Exception:
        limit = 2

    if limit > 0 and (not _has_verified_email(request.user)):
        created_count = ChatGroup.objects.filter(
            admin=request.user,
            is_private=True,
            is_code_room=True,
        ).count()
        if created_count >= limit:
            # Return JSON error for AJAX (no page redirect), or fallback redirect for non-AJAX.
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.GET.get('_ajax') == '1':
                return JsonResponse({
                    'ok': False,
                    'error': f'Please verify your email to create more than {limit} private rooms.'
                }, status=403)
            messages.error(request, f'Please verify your email to create more than {limit} private rooms.')
            return redirect('home')

    rl = check_rate_limit(
        make_key('private_room_create', request.user.id, get_client_ip(request)),
        limit=int(getattr(settings, 'PRIVATE_ROOM_CREATE_RATE_LIMIT', 5)),
        period_seconds=int(getattr(settings, 'PRIVATE_ROOM_CREATE_RATE_PERIOD', 300)),
    )
    if not rl.allowed:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.GET.get('_ajax') == '1':
            return JsonResponse({
                'ok': False,
                'error': 'Too many attempts. Please wait and try again.'
            }, status=429)
        messages.error(request, 'Too many attempts. Please wait and try again.')
        return redirect('home')

    form = PrivateRoomCreateForm(request.POST)
    if not form.is_valid():
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.GET.get('_ajax') == '1':
            return JsonResponse({
                'ok': False,
                'error': 'Invalid room details'
            }, status=400)
        messages.error(request, 'Invalid room details')
        return redirect('home')

    name = (form.cleaned_data.get('name') or '').strip()
    room = ChatGroup.objects.create(
        is_private=True,
        is_code_room=True,
        code_room_name=name or None,
        admin=request.user,
    )
    room.members.add(request.user)

    # Return JSON response for AJAX requests (no Django messages), or redirect for regular form submit.
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.GET.get('_ajax') == '1'
    if is_ajax:
        return JsonResponse({
            'ok': True,
            'redirect_url': f"{reverse('chatroom', args=[room.group_name])}?created=1"
        })

    messages.success(request, f'Private room created. Share code: {room.room_code}')
    return redirect(f"{reverse('chatroom', args=[room.group_name])}?created=1")


@login_required
def join_private_room_by_code(request):
    if request.method != 'POST':
        return redirect('home')

    if _is_chat_blocked(request.user):
        messages.error(request, 'You are blocked from joining private rooms.')
        return redirect('home')

    rl = check_rate_limit(
        make_key('private_room_join', request.user.id, get_client_ip(request)),
        limit=int(getattr(settings, 'PRIVATE_ROOM_JOIN_RATE_LIMIT', 10)),
        period_seconds=int(getattr(settings, 'PRIVATE_ROOM_JOIN_RATE_PERIOD', 300)),
    )
    if not rl.allowed:
        messages.error(request, 'Too many attempts. Please wait and try again.')
        return redirect('home')

    form = RoomCodeJoinForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Enter a valid room code')
        return redirect('home')

    code = (form.cleaned_data.get('code') or '').strip().upper()
    room = ChatGroup.objects.filter(is_code_room=True, room_code=code).first()
    if not room:
        messages.error(request, 'Room code is invalid')
        return redirect('home')

    # Hard cap: private code rooms can have at most N members.
    # If exceeded, show a popup/toast via Django messages.
    with transaction.atomic():
        locked_room = ChatGroup.objects.select_for_update().filter(pk=room.pk).first()
        if not locked_room:
            messages.error(request, 'Room code is invalid')
            return redirect('home')

        if locked_room.members.filter(pk=request.user.pk).exists():
            return redirect('chatroom', locked_room.group_name)

        if locked_room.members.count() >= PRIVATE_ROOM_MEMBER_LIMIT:
            messages.error(request, 'User limit reached')
            return redirect('home')

        # Place user into waiting list until admitted by admin/staff.
        CodeRoomJoinRequest.objects.update_or_create(
            room=locked_room,
            user=request.user,
            defaults={
                'admitted_at': None,
                'admitted_by': None,
                'last_seen_at': timezone.now(),
            },
        )

    return redirect('chatroom', room.group_name)


@login_required
def code_room_waiting_list(request, chatroom_name):
    chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name)

    if not getattr(chat_group, 'is_private', False) or not getattr(chat_group, 'is_code_room', False):
        raise Http404()

    if request.user != chat_group.admin and not request.user.is_staff:
        raise Http404()

    cutoff = _code_room_waiting_cutoff()
    qs = (
        CodeRoomJoinRequest.objects.filter(room=chat_group, admitted_at__isnull=True, last_seen_at__gte=cutoff)
        .select_related('user')
        .order_by('created_at')
    )

    pending = []
    for jr in qs:
        u = jr.user
        try:
            profile = getattr(u, 'profile', None)
        except Exception:
            profile = None
        try:
            display = (getattr(profile, 'name', None) or u.username)
        except Exception:
            display = u.username
        try:
            avatar = getattr(profile, 'avatar', '') if profile else ''
        except Exception:
            avatar = ''

        pending.append({
            'id': u.id,
            'username': u.username,
            'display': display,
            'avatar': avatar,
        })

    return JsonResponse({'ok': True, 'count': len(pending), 'pending': pending})


@login_required
def code_room_waiting_admit(request, chatroom_name):
    chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name)

    if request.method != 'POST':
        raise Http404()

    if not getattr(chat_group, 'is_private', False) or not getattr(chat_group, 'is_code_room', False):
        raise Http404()

    if request.user != chat_group.admin and not request.user.is_staff:
        raise Http404()

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        payload = {}

    user_id = payload.get('user_id') or request.POST.get('user_id')
    try:
        user_id = int(user_id)
    except Exception:
        return JsonResponse({'ok': False, 'error': 'invalid_user'}, status=400)

    with transaction.atomic():
        locked_room = ChatGroup.objects.select_for_update().filter(pk=chat_group.pk).first()
        if not locked_room:
            raise Http404()

        jr = CodeRoomJoinRequest.objects.select_for_update().filter(room=locked_room, user_id=user_id).first()
        if not jr or not jr.is_pending:
            return JsonResponse({'ok': False, 'error': 'not_pending'}, status=404)

        if locked_room.members.filter(pk=user_id).exists():
            jr.mark_admitted(by_user=request.user)
            return JsonResponse({'ok': True, 'already_member': True})

        if locked_room.members.count() >= PRIVATE_ROOM_MEMBER_LIMIT:
            return JsonResponse({'ok': False, 'error': 'member_limit'}, status=400)

        locked_room.members.add(user_id)
        jr.mark_admitted(by_user=request.user)

    return JsonResponse({'ok': True})


@login_required
def code_room_waiting_status(request, chatroom_name):
    chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name)

    if not getattr(chat_group, 'is_private', False) or not getattr(chat_group, 'is_code_room', False):
        raise Http404()

    if chat_group.members.filter(pk=request.user.pk).exists():
        return JsonResponse({'ok': True, 'status': 'admitted', 'redirect': reverse('chatroom', args=[chatroom_name])})

    pending_qs = CodeRoomJoinRequest.objects.filter(
        room=chat_group,
        user=request.user,
        admitted_at__isnull=True,
    )
    pending = pending_qs.exists()

    if pending:
        # Mark presence so admins only see active requesters.
        try:
            pending_qs.update(last_seen_at=timezone.now())
        except Exception:
            pass
        return JsonResponse({'ok': True, 'status': 'pending'})

    return JsonResponse({'ok': True, 'status': 'not_found'})


@login_required
def private_room_rename(request, chatroom_name):
    """Rename a private *code room* (not 1:1 DMs).

    Only the room admin or staff can rename. Accepts either form-encoded POST
    (`name`) or JSON body (`{"name": "..."}`). Returns JSON.
    """
    chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name)

    if request.method != 'POST':
        raise Http404()

    if not getattr(chat_group, 'is_private', False) or not getattr(chat_group, 'is_code_room', False):
        raise Http404()

    if request.user != chat_group.admin and not request.user.is_staff:
        raise Http404()

    if request.user not in chat_group.members.all() and not request.user.is_staff:
        raise Http404()

    name = (request.POST.get('name') or '').strip()
    if not name:
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
            name = (payload.get('name') or '').strip()
        except Exception:
            name = ''

    # Normalize + enforce max length.
    # UI limits this to 35 chars; keep server-side consistent.
    name = (name or '').strip()
    if len(name) > 35:
        name = name[:35]

    chat_group.code_room_name = name or None
    chat_group.save(update_fields=['code_room_name'])

    return JsonResponse({
        'ok': True,
        'group': chat_group.group_name,
        'name': chat_group.code_room_name or '',
        'display': chat_group.code_room_name or chat_group.room_code or chat_group.group_name,
    })

@login_required
def get_or_create_chatroom(request, username):
    if _is_chat_banned(request.user):
        return render(request, '403.html', status=403)

    if _is_chat_blocked(request.user):
        messages.error(request, 'You are blocked from private chats.')
        return redirect('home')
    username = (username or '').strip()
    if not username:
        raise Http404()
    if request.user.username == username:
        return redirect('home')

    try:
        other_user = User.objects.get(username=username)
    except User.DoesNotExist:
        raise Http404()
    my_chatrooms = request.user.chat_groups.filter(is_private=True)
    
    chatroom = None
    if my_chatrooms.exists():
        for room in my_chatrooms:
            if other_user in room.members.all():
                chatroom = room
                break
                
    if not chatroom:
        chatroom = ChatGroup.objects.create(is_private = True)
        chatroom.members.add(other_user, request.user)
        
    return redirect('chatroom', chatroom.group_name)

@login_required
def create_groupchat(request):
    if not request.user.is_staff:
        raise Http404()
    form = NewGroupForm()
    if request.method == 'POST':
        rl = check_rate_limit(
            make_key('groupchat_create', request.user.id, get_client_ip(request)),
            limit=int(getattr(settings, 'GROUPCHAT_CREATE_RATE_LIMIT', 10)),
            period_seconds=int(getattr(settings, 'GROUPCHAT_CREATE_RATE_PERIOD', 600)),
        )
        if not rl.allowed:
            messages.error(request, 'Too many attempts. Please wait and try again.')
            return redirect('new-groupchat')

        form = NewGroupForm(request.POST)
        if form.is_valid():
            new_groupchat = form.save(commit=False)
            new_groupchat.admin = request.user
            new_groupchat.save()
            new_groupchat.members.add(request.user)
            return redirect('chatroom', new_groupchat.group_name)
    
    return render(request, 'a_rtchat/create_groupchat.html', {'form': form})

@login_required
def chatroom_edit_view(request, chatroom_name):
    chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name)
    if request.user != chat_group.admin and not request.user.is_staff:
        raise Http404()
    
    form = ChatRoomEditForm(instance=chat_group) 
    if request.method == 'POST':
        form = ChatRoomEditForm(request.POST, instance=chat_group)
        if form.is_valid():
            form.save()
            remove_members = request.POST.getlist('remove_members')
            for member_id in remove_members:
                member = User.objects.get(id=member_id)
                chat_group.members.remove(member)  
            return redirect('chatroom', chatroom_name) 
    
    return render(request, 'a_rtchat/chatroom_edit.html', {'form': form, 'chat_group': chat_group}) 

@login_required
def chatroom_delete_view(request, chatroom_name):
    chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name)
    if request.user != chat_group.admin and not request.user.is_staff:
        raise Http404()
    
    if request.method == "POST":
        chat_group.delete()
        messages.success(request, 'Chatroom deleted')
        return redirect('home')
    
    return render(request, 'a_rtchat/chatroom_delete.html', {'chat_group':chat_group})


@login_required
def chatroom_close_view(request, chatroom_name):
    """Hard-delete a room and all of its data (messages/files) from the DB."""
    chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name)
    if request.user != chat_group.admin and not request.user.is_staff:
        raise Http404()

    if request.method != 'POST':
        raise Http404()

    chat_group.delete()
    messages.success(request, 'Room closed and deleted')
    return redirect('home')

@login_required
def chatroom_leave_view(request, chatroom_name):
    chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name)
    if request.user not in chat_group.members.all():
        raise Http404()
    
    if request.method == "POST":
        chat_group.members.remove(request.user)
        messages.success(request, 'You left the Chat')
        return redirect('home')


@login_required
@require_POST
def chatroom_member_remove_view(request, chatroom_name, user_id):
    """Remove a member from a private room (admin/staff only)."""
    chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name)

    # Only private rooms support member management.
    if not getattr(chat_group, 'is_private', False):
        raise Http404()

    if request.user != getattr(chat_group, 'admin', None) and not request.user.is_staff:
        raise Http404()

    try:
        member = get_user_model().objects.get(id=int(user_id))
    except Exception:
        return JsonResponse({'ok': False, 'error': 'user_not_found'}, status=404)

    # Safety: can't remove yourself via this control.
    if member == request.user:
        return JsonResponse({'ok': False, 'error': 'cannot_remove_self'}, status=400)

    # Safety: don't allow removing the room admin.
    if member == getattr(chat_group, 'admin', None):
        return JsonResponse({'ok': False, 'error': 'cannot_remove_admin'}, status=400)

    # Must be a current member.
    try:
        if member not in chat_group.members.all():
            return JsonResponse({'ok': False, 'error': 'not_a_member'}, status=400)
    except Exception:
        return JsonResponse({'ok': False, 'error': 'not_a_member'}, status=400)

    try:
        chat_group.members.remove(member)
    except Exception:
        return JsonResponse({'ok': False, 'error': 'remove_failed'}, status=500)

    return JsonResponse({'ok': True, 'removedUserId': int(member.id)})

@login_required
def chat_file_upload(request, chatroom_name):
    chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name)

    if _is_chat_banned(request.user):
        return HttpResponse('<div class="text-xs text-red-400">You are banned from chat.</div>', status=403)

    if _is_chat_blocked(request.user):
        return HttpResponse('<div class="text-xs text-red-400">You are blocked from uploading files.</div>', status=403)

    muted = get_muted_seconds(getattr(request.user, 'id', 0))
    if muted > 0:
        resp = HttpResponse('<div class="text-xs text-red-400">You are on cooldown. Please wait.</div>', status=429)
        resp.headers['Retry-After'] = str(muted)
        return resp

    rl = check_rate_limit(
        make_key('chat_upload', chatroom_name, request.user.id),
        limit=int(getattr(settings, 'CHAT_UPLOAD_RATE_LIMIT', 3)),
        period_seconds=int(getattr(settings, 'CHAT_UPLOAD_RATE_PERIOD', 60)),
    )
    if not rl.allowed:
        _, muted2 = record_abuse_violation(
            scope='chat_upload',
            user_id=request.user.id,
            room=chatroom_name,
            window_seconds=int(getattr(settings, 'CHAT_ABUSE_WINDOW', 600)),
            threshold=int(getattr(settings, 'CHAT_ABUSE_STRIKE_THRESHOLD', 5)),
            mute_seconds=int(getattr(settings, 'CHAT_ABUSE_MUTE_SECONDS', 60)),
        )
        resp = HttpResponse('<div class="text-xs text-red-400">Too many uploads. Please wait.</div>', status=429)
        resp.headers['Retry-After'] = str(muted2 or rl.retry_after)
        return resp

    if request.method != 'POST':
        raise Http404()

    # Unverified users can send a limited number of messages, then must verify.
    # Return an HTMX trigger (no refresh) so the client can show an overlay + blur.
    try:
        if _requires_verified_email_for_chat(request.user):
            messages.warning(request, 'Verify your email to continue chatting.')
            resp = HttpResponse('', status=200)
            resp.headers['HX-Trigger'] = json.dumps({
                'verify_required': {
                    'reason': 'Verify your email to continue chatting.',
                },
            })
            return resp
    except Exception:
        pass

    # Uploads allowed ONLY in private code rooms (plus Showcase exception).
    if not room_allows_uploads(chat_group):
        raise Http404()

    if request.user not in chat_group.members.all():
        raise Http404()

    # If HTMX isn't present for some reason, still allow a normal POST fallback.
    is_htmx = bool(getattr(request, 'htmx', False))

    if not request.FILES or 'file' not in request.FILES:
        if is_htmx:
            return HttpResponse(
                '<div class="text-xs text-red-400">Please choose a file first.</div>',
                status=400,
            )
        return redirect('chatroom', chatroom_name)

    upload = request.FILES['file']

    caption = (request.POST.get('caption') or '').strip()
    if caption:
        caption = caption[:300]

    raw_one_time = (request.POST.get('one_time_seconds') or '').strip()
    one_time_seconds = None
    if raw_one_time:
        try:
            s = int(raw_one_time)
        except Exception:
            s = 0
        if s in (3, 8, 15):
            if not getattr(chat_group, 'is_private', False):
                return HttpResponse(
                    '<div class="text-xs text-red-400">One-time view is only available in private chats.</div>',
                    status=400,
                )
            one_time_seconds = s

    # Enforce max file size
    if getattr(upload, 'size', 0) > CHAT_UPLOAD_MAX_BYTES:
        return HttpResponse(
            '<div class="text-xs text-red-400">File is too large.</div>',
            status=413,
        )

    # Enforce content type: images/videos only
    content_type = (getattr(upload, 'content_type', '') or '').lower()
    if not (content_type.startswith('image/') or content_type.startswith('video/')):
        return HttpResponse(
            '<div class="text-xs text-red-400">Only photos/videos are allowed.</div>',
            status=400,
        )

    if one_time_seconds and not content_type.startswith('image/'):
        return HttpResponse(
            '<div class="text-xs text-red-400">One-time view is only supported for photos.</div>',
            status=400,
        )

    # Enforce per-user per-room upload limit
    uploads_used = _uploads_used_today(chat_group, request.user)
    if uploads_used >= CHAT_UPLOAD_LIMIT_PER_ROOM:
        return HttpResponse(
            f'<div class="text-xs text-red-400">Daily upload limit reached ({CHAT_UPLOAD_LIMIT_PER_ROOM}/{CHAT_UPLOAD_LIMIT_PER_ROOM}).</div>',
            status=400,
        )

    message = GroupMessage.objects.create(
        file=upload,
        file_caption=caption or None,
        one_time_view_seconds=one_time_seconds,
        author=request.user,
        group=chat_group,
    )

    # Best-effort: if user didn't allow GPS location, store approximate city/country from IP.
    try:
        if maybe_set_profile_city_from_ip is not None:
            maybe_set_profile_city_from_ip(user=request.user, request=request)
    except Exception:
        pass

    # Retention: keep only the newest messages per room (best-effort).
    # Public/group rooms and private rooms can use different caps.
    try:
        from a_rtchat.retention import trim_chat_group_messages

        is_private = bool(getattr(chat_group, 'is_private', False))
        if is_private:
            keep_last = int(getattr(settings, 'PRIVATE_CHAT_MAX_MESSAGES_PER_ROOM', 1000))
        else:
            keep_last = int(getattr(settings, 'CHAT_MAX_MESSAGES_PER_ROOM', 300))

        trim_chat_group_messages(
            chat_group_id=chat_group.id,
            keep_last=max(1, keep_last),
        )
    except Exception:
        pass

    channel_layer = get_channel_layer()
    event = {
        'type': 'message_handler',
        'message_id': message.id,
        # Sender will render via HTMX response; avoid duplicate bubble via websocket.
        'skip_sender': True,
        'author_id': request.user.id,
    }
    async_to_sync(channel_layer.group_send)(chatroom_channel_group_name(chat_group), event)

    # HTMX: return the rendered message HTML so the sender sees it immediately
    # even if websockets are unavailable.
    if is_htmx:
        _attach_reaction_pills([message], request.user)
        _attach_one_time_view_flags([message], request.user)
        verified_user_ids = get_verified_user_ids([getattr(request.user, 'id', None)])
        html = render(request, 'a_rtchat/chat_message.html', {
            'message': message,
            'user': request.user,
            'chat_group': chat_group,
            'reaction_emojis': CHAT_REACTION_EMOJIS,
            'other_last_read_id': 0,
            'verified_user_ids': verified_user_ids,
        }).content.decode('utf-8')
        response = HttpResponse(html, status=200)
        # Fire after swap so client-side reset doesn't interfere with the DOM insertion.
        trigger = {'chatFileUploaded': True}
        try:
            if _requires_verified_email_for_chat(request.user):
                trigger['verify_required'] = {'reason': 'Verify your email to continue chatting.'}
        except Exception:
            pass
        response.headers['HX-Trigger-After-Swap'] = json.dumps(trigger)
        return response

    return redirect('chatroom', chatroom_name)


@login_required
def message_one_time_open(request, message_id):
    """Recipient opens a one-time image.

    Per-viewer behavior: each viewer can open once (ever). The client handles the
    countdown/hide; server enforces the one-open rule.
    """
    if _is_chat_banned(request.user):
        return HttpResponse('', status=403)

    if request.method != 'POST':
        raise Http404()

    message = get_object_or_404(GroupMessage.objects.select_related('group', 'author'), pk=message_id)
    chat_group = message.group

    if not getattr(chat_group, 'is_private', False):
        raise Http404()
    if request.user == message.author:
        return JsonResponse({'ok': False, 'error': 'sender_cannot_open'}, status=403)
    if request.user not in chat_group.members.all():
        raise Http404()

    if not message.one_time_view_seconds:
        return JsonResponse({'ok': False, 'error': 'not_one_time'}, status=400)
    if not message.file or not message.is_image:
        return JsonResponse({'ok': False, 'error': 'not_image'}, status=400)

    # Already opened by this viewer?
    if OneTimeMessageView.objects.filter(message=message, user=request.user).exists():
        return JsonResponse({'ok': False, 'error': 'already_viewed'}, status=410)

    # First open: create a per-view record.
    try:
        OneTimeMessageView.objects.create(message=message, user=request.user)
    except Exception:
        # In case of race (double click), treat as already viewed.
        return JsonResponse({'ok': False, 'error': 'already_viewed'}, status=410)

    # Notify the room so the sender can see "seen" state (best-effort).
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        from .channels_utils import chatroom_channel_group_name

        viewer_name = ''
        try:
            viewer_name = (getattr(getattr(request.user, 'profile', None), 'name', '') or '').strip()
        except Exception:
            viewer_name = ''
        if not viewer_name:
            viewer_name = (getattr(request.user, 'username', '') or '').strip()

        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            chatroom_channel_group_name(chat_group),
            {
                'type': 'one_time_seen_handler',
                'message_id': message.id,
                'author_id': message.author_id,
                'viewer_id': getattr(request.user, 'id', None),
                'viewer_name': viewer_name,
            },
        )
    except Exception:
        pass

    seconds = int(message.one_time_view_seconds or 0)
    expires_at = timezone.now() + timedelta(seconds=max(0, seconds))
    return JsonResponse({'ok': True, 'seconds': seconds, 'expires_at': int(expires_at.timestamp())})


@login_required
def message_info_view(request, message_id: int):
    """Show 'Info' (read-by) for a message in private chats."""
    if _is_chat_banned(request.user):
        return HttpResponse('', status=403)

    message = get_object_or_404(GroupMessage.objects.select_related('group', 'author'), pk=message_id)
    chat_group = message.group

    # Default avatar fallback (covers missing profile/image cases)
    try:
        from a_users.models import DEFAULT_AVATAR_DATA_URI
        default_avatar = DEFAULT_AVATAR_DATA_URI
    except Exception:
        default_avatar = ''

    if not getattr(chat_group, 'is_private', False):
        raise Http404()
    if request.user not in chat_group.members.all():
        raise Http404()
    if request.user != message.author and not getattr(request.user, 'is_staff', False):
        return HttpResponse('', status=403)

    readers = []
    try:
        readers = list(
            ChatReadState.objects.filter(group=chat_group, last_read_message_id__gte=message.id)
            .exclude(user_id=message.author_id)
            .select_related('user', 'user__profile')
            .order_by('-updated')
        )
    except Exception:
        readers = []

    return render(
        request,
        'a_rtchat/partials/message_info_modal.html',
        {
            'message': message,
            'chat_group': chat_group,
            'read_states': readers,
            'default_avatar': default_avatar,
        },
    )


@login_required
def chat_poll_view(request, chatroom_name):
    """Return new messages after a given message id (used as a realtime fallback)."""
    if _is_chat_banned(request.user):
        return JsonResponse({'messages_html': '', 'last_id': request.GET.get('after')}, status=403)

    if chatroom_name == 'public-chat':
        chat_group, created = ChatGroup.objects.get_or_create(group_name=chatroom_name)
    else:
        chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name)

    # Permission checks (same intent as chat_view)
    if _is_chat_blocked(request.user) and getattr(chat_group, 'is_private', False):
        raise Http404()
    if chat_group.is_private and request.user not in chat_group.members.all():
        raise Http404()
    if chat_group.groupchat_name and request.user not in chat_group.members.all():
        if _is_chat_blocked(request.user):
            # Let blocked users read but don't auto-join.
            pass
        else:
            email_verification = str(getattr(settings, 'ACCOUNT_EMAIL_VERIFICATION', 'optional')).lower()
            if email_verification == 'mandatory':
                if request.user.emailaddress_set.filter(verified=True).exists():
                    chat_group.members.add(request.user)
                else:
                    return JsonResponse({'messages_html': '', 'last_id': request.GET.get('after')}, status=403)
            else:
                chat_group.members.add(request.user)

    # Rate limit polling (best-effort, avoid flooding). If limited, return an empty response.
    rl = check_rate_limit(
        make_key('chat_poll', chat_group.group_name, request.user.id),
        limit=int(getattr(settings, 'CHAT_POLL_RATE_LIMIT', 240)),
        period_seconds=int(getattr(settings, 'CHAT_POLL_RATE_PERIOD', 60)),
    )
    if not rl.allowed:
        record_abuse_violation(
            scope='chat_poll',
            user_id=request.user.id,
            room=chat_group.group_name,
            window_seconds=int(getattr(settings, 'CHAT_ABUSE_WINDOW', 600)),
            threshold=int(getattr(settings, 'CHAT_ABUSE_STRIKE_THRESHOLD', 5)),
            mute_seconds=int(getattr(settings, 'CHAT_ABUSE_MUTE_SECONDS', 60)),
        )
        try:
            after_id = int(request.GET.get('after', '0'))
        except ValueError:
            after_id = 0
        online_count = chat_group.users_online.count()
        return JsonResponse({'messages_html': '', 'last_id': after_id, 'online_count': online_count})

    try:
        after_id = int(request.GET.get('after', '0'))
    except ValueError:
        after_id = 0

    online_count = chat_group.users_online.count()

    new_messages_qs = chat_group.chat_messages.filter(id__gt=after_id).order_by('created', 'id')
    new_messages = list(new_messages_qs[:50])
    if not new_messages:
        return JsonResponse({'messages_html': '', 'last_id': after_id, 'online_count': online_count})

    _attach_reaction_pills(new_messages, request.user)
    _attach_one_time_view_flags(new_messages, request.user)

    verified_user_ids = set()
    try:
        author_ids = {getattr(m, 'author_id', None) for m in (new_messages or [])}
        author_ids = {x for x in author_ids if x}
        author_ids.add(getattr(request.user, 'id', None))
        verified_user_ids = get_verified_user_ids(author_ids)
    except Exception:
        verified_user_ids = set()

    # Render a batch of messages using the same bubble template
    parts = []
    for message in new_messages:
        parts.append(render(request, 'a_rtchat/chat_message.html', {
            'message': message,
            'user': request.user,
            'chat_group': chat_group,
            'reaction_emojis': CHAT_REACTION_EMOJIS,
            'verified_user_ids': verified_user_ids,
        }).content.decode('utf-8'))

    last_id = new_messages[-1].id
    return JsonResponse({'messages_html': ''.join(parts), 'last_id': last_id, 'online_count': online_count})


@login_required
def message_edit_view(request, message_id: int):
    if _is_chat_banned(request.user):
        return HttpResponse('', status=403)

    if request.method != 'POST':
        raise Http404()

    if _is_chat_blocked(request.user):
        return HttpResponse('', status=403)

    rl = check_rate_limit(
        make_key('msg_edit', request.user.id),
        limit=int(getattr(settings, 'CHAT_EDIT_RATE_LIMIT', 30)),
        period_seconds=int(getattr(settings, 'CHAT_EDIT_RATE_PERIOD', 60)),
    )
    if not rl.allowed:
        resp = HttpResponse('', status=429)
        resp.headers['Retry-After'] = str(rl.retry_after)
        return resp

    message = get_object_or_404(GroupMessage, pk=message_id)
    chat_group = message.group

    if message.author_id != request.user.id:
        raise Http404()

    # Permission checks (match chatroom access rules)
    if getattr(chat_group, 'is_private', False) and request.user not in chat_group.members.all():
        raise Http404()
    if chat_group.groupchat_name and request.user not in chat_group.members.all():
        raise Http404()

    # GIF messages are not editable (only delete).
    if (message.body or '').strip().startswith('[GIF]'):
        return JsonResponse({'error': 'GIF messages cannot be edited.'}, status=403)

    body = (request.POST.get('body') or '').strip()
    if not body:
        return JsonResponse({'error': 'Message cannot be empty'}, status=400)

    gifs_allowed = not is_free_promotion_room(chat_group)
    gif_url = _parse_gif_message(body)

    if body.startswith('[GIF]'):
        if not gifs_allowed:
            return JsonResponse({'error': 'GIFs are not allowed in this room.'}, status=400)
        if not gif_url:
            return JsonResponse({'error': 'Invalid GIF. Only Giphy GIFs are supported.'}, status=400)

    # Links are only allowed in private chats (GIF is a special exception).
    if contains_link(body) and not room_allows_links(chat_group):
        if not (gif_url and gifs_allowed):
            return JsonResponse({'error': 'Links are only allowed in private chats.'}, status=400)

    if body != (message.body or ''):
        message.body = body
        message.edited_at = timezone.now()
        message.save(update_fields=['body', 'edited_at'])
    else:
        return HttpResponse('', status=204)

    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        chatroom_channel_group_name(chat_group),
        {
            'type': 'message_update_handler',
            'message_id': message.id,
        },
    )
    return HttpResponse('', status=204)


@login_required
def message_delete_view(request, message_id: int):
    if _is_chat_banned(request.user):
        return HttpResponse('', status=403)

    if request.method != 'POST':
        raise Http404()

    if _is_chat_blocked(request.user):
        return HttpResponse('', status=403)

    rl = check_rate_limit(
        make_key('msg_delete', request.user.id),
        limit=int(getattr(settings, 'CHAT_DELETE_RATE_LIMIT', 20)),
        period_seconds=int(getattr(settings, 'CHAT_DELETE_RATE_PERIOD', 60)),
    )
    if not rl.allowed:
        resp = HttpResponse('', status=429)
        resp.headers['Retry-After'] = str(rl.retry_after)
        return resp

    message = get_object_or_404(GroupMessage, pk=message_id)
    chat_group = message.group

    if message.author_id != request.user.id and not request.user.is_staff:
        raise Http404()

    if getattr(chat_group, 'is_private', False) and request.user not in chat_group.members.all():
        raise Http404()
    if chat_group.groupchat_name and request.user not in chat_group.members.all():
        raise Http404()

    deleted_id = message.id
    message.delete()

    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        chatroom_channel_group_name(chat_group),
        {
            'type': 'message_delete_handler',
            'message_id': deleted_id,
        },
    )
    return HttpResponse('', status=204)


@login_required
def message_react_toggle(request, message_id: int):
    if _is_chat_banned(request.user):
        return HttpResponse('', status=403)

    if request.method != 'POST':
        raise Http404()

    if _is_chat_blocked(request.user):
        return HttpResponse('', status=403)

    emoji = (request.POST.get('emoji') or '').strip()
    if emoji not in CHAT_REACTION_EMOJIS:
        return JsonResponse({'error': 'Invalid emoji'}, status=400)

    message = get_object_or_404(GroupMessage, pk=message_id)
    chat_group = message.group

    if getattr(chat_group, 'is_private', False) and request.user not in chat_group.members.all():
        raise Http404()
    if chat_group.groupchat_name and request.user not in chat_group.members.all():
        raise Http404()

    # Only allow one reaction per user per message.
    # - If user taps the same emoji again: remove (toggle off)
    # - If user picks a different emoji: replace previous reaction with the new emoji
    qs = MessageReaction.objects.filter(message=message, user=request.user)
    if qs.filter(emoji=emoji).exists():
        qs.filter(emoji=emoji).delete()
    else:
        qs.delete()
        MessageReaction.objects.create(message=message, user=request.user, emoji=emoji)

    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        chatroom_channel_group_name(chat_group),
        {
            'type': 'reactions_handler',
            'message_id': message.id,
        },
    )

    return HttpResponse('', status=204)


@login_required
def admin_users_view(request):
    if not request.user.is_staff:
        raise Http404()

    q = (request.GET.get('q') or '').strip()
    users = User.objects.all().order_by('username')
    if q:
        users = users.filter(
            Q(username__icontains=q)
            | Q(email__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
        )

    # Keep a hard cap to avoid an accidentally expensive staff page.
    users = users[:200]

    paginator = Paginator(users, 11)
    page_obj = paginator.get_page(request.GET.get('page') or 1)

    user_ids = [u.id for u in page_obj.object_list]
    existing = set(Profile.objects.filter(user_id__in=user_ids).values_list('user_id', flat=True))
    missing = [Profile(user_id=uid) for uid in user_ids if uid not in existing]
    if missing:
        Profile.objects.bulk_create(missing, ignore_conflicts=True)

    # Attach recent devices (best-effort) for staff visibility.
    try:
        from a_users.models import UserDevice

        device_rows = (
            UserDevice.objects
            .filter(user_id__in=user_ids)
            .order_by('user_id', '-last_seen')
            .only('user_id', 'device_label', 'user_agent', 'last_seen')
        )
        devices_by_user: dict[int, list[UserDevice]] = {}
        for d in device_rows:
            lst = devices_by_user.setdefault(int(d.user_id), [])
            if len(lst) < 3:
                lst.append(d)

        for u in page_obj.object_list:
            setattr(u, 'recent_devices', devices_by_user.get(int(u.id), []))
    except Exception:
        for u in page_obj.object_list:
            setattr(u, 'recent_devices', [])

    return render(request, 'a_rtchat/admin_users.html', {
        'q': q,
        'page_obj': page_obj,
        'paginator': paginator,
        'is_paginated': page_obj.has_other_pages(),
        'now': timezone.now(),
    })


@login_required
def admin_users_export_view(request):
    if not request.user.is_staff:
        raise Http404()

    q = (request.GET.get('q') or '').strip()
    users = User.objects.all().order_by('username')
    if q:
        users = users.filter(
            Q(username__icontains=q)
            | Q(email__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
        )

    limit = int(getattr(settings, 'ADMIN_USERS_EXPORT_LIMIT', 50000))
    users = users[: max(1, limit)]

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="users.csv"'
    response['Cache-Control'] = 'no-store'

    # Excel compatibility for UTF-8.
    response.write('\ufeff')

    writer = csv.writer(response)
    writer.writerow(['username', 'email'])
    for username, email in users.values_list('username', 'email').iterator(chunk_size=2000):
        writer.writerow([username or '', email or ''])
    return response


@login_required
def admin_beta_features_view(request):
    if not request.user.is_staff:
        raise Http404()

    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip().lower()

        if action == 'create':
            slug = (request.POST.get('slug') or '').strip().lower()
            title = (request.POST.get('title') or '').strip()
            description = (request.POST.get('description') or '').strip()
            requires_founder_club = bool(request.POST.get('requires_founder_club'))

            if not slug or not title:
                messages.error(request, 'Slug and title are required')
                return redirect('admin-beta-features')

            obj, created = BetaFeature.objects.get_or_create(
                slug=slug,
                defaults={
                    'title': title,
                    'description': description,
                    'requires_founder_club': requires_founder_club,
                },
            )
            if created:
                messages.success(request, f'Created beta feature: {slug}')
            else:
                messages.error(request, f'Beta feature already exists: {slug}')
            return redirect('admin-beta-features')

        if action in {'toggle_enabled', 'toggle_founder_only'}:
            slug = (request.POST.get('slug') or '').strip().lower()
            if not slug:
                raise Http404()
            obj = get_object_or_404(BetaFeature, slug=slug)
            if action == 'toggle_enabled':
                obj.is_enabled = not obj.is_enabled
                obj.save(update_fields=['is_enabled', 'updated_at'])
                messages.success(request, f"{'Enabled' if obj.is_enabled else 'Disabled'}: {obj.slug}")
            else:
                obj.requires_founder_club = not obj.requires_founder_club
                obj.save(update_fields=['requires_founder_club', 'updated_at'])
                messages.success(
                    request,
                    f"{'Founder-only' if obj.requires_founder_club else 'Open to all'}: {obj.slug}",
                )
            return redirect('admin-beta-features')

    features = BetaFeature.objects.all().order_by('slug')
    return render(request, 'a_rtchat/admin_beta_features.html', {
        'features': features,
    })


@login_required
def moderation_logs_view(request):
    if not request.user.is_staff:
        raise Http404()

    action = (request.GET.get('action') or '').strip().lower()
    qs = ModerationEvent.objects.all()
    if action in {'flag', 'block', 'allow'}:
        qs = qs.filter(action=action)

    events = qs.select_related('user', 'room', 'message')[:200]
    return render(request, 'a_rtchat/moderation_logs.html', {
        'events': events,
        'action': action,
    })


@login_required
def admin_toggle_user_block_view(request, user_id: int):
    if request.method != 'POST':
        raise Http404()
    if not request.user.is_staff:
        raise Http404()

    target = get_object_or_404(User, pk=user_id)
    if target.is_superuser:
        messages.error(request, 'Cannot block a superuser')
        return redirect('admin-users')
    if target.id == request.user.id:
        messages.error(request, 'You cannot block yourself')
        return redirect('admin-users')

    profile, _ = Profile.objects.get_or_create(user=target)

    rl = check_rate_limit(
        make_key('admin_block_toggle', request.user.id, get_client_ip(request)),
        limit=int(getattr(settings, 'ADMIN_BLOCK_TOGGLE_RATE_LIMIT', 60)),
        period_seconds=int(getattr(settings, 'ADMIN_BLOCK_TOGGLE_RATE_PERIOD', 60)),
    )
    if not rl.allowed:
        messages.error(request, 'Too many actions. Please wait and try again.')
        return redirect('admin-users')

    profile.chat_blocked = not bool(profile.chat_blocked)
    profile.save(update_fields=['chat_blocked'])

    # Realtime: notify the user (all open tabs) that their chat permissions changed.
    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"notify_user_{target.id}",
            {
                'type': 'chat_block_status_notify_handler',
                'blocked': bool(profile.chat_blocked),
                'by_username': getattr(request.user, 'username', '') or '',
            },
        )
    except Exception:
        pass

    if profile.chat_blocked:
        messages.success(request, f'Blocked {target.username} from chatting')
    else:
        messages.success(request, f'Unblocked {target.username}')

    next_url = (request.POST.get('next') or '').strip()
    if next_url and url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)

    referer = (request.META.get('HTTP_REFERER') or '').strip()
    if referer and url_has_allowed_host_and_scheme(
        url=referer,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(referer)

    return redirect('admin-users')


@login_required
def admin_user_ban_view(request, user_id: int):
    """Ban/unban a user from reading/writing chats for a duration (minutes).

    POST param: minutes (int). If 0, unban.
    """
    if request.method != 'POST':
        raise Http404()
    if not request.user.is_staff:
        raise Http404()

    target = get_object_or_404(User, pk=user_id)
    if target.is_superuser:
        messages.error(request, 'Cannot ban a superuser')
        return redirect('admin-users')
    if target.id == request.user.id:
        messages.error(request, 'You cannot ban yourself')
        return redirect('admin-users')

    profile, _ = Profile.objects.get_or_create(user=target)

    rl = check_rate_limit(
        make_key('admin_ban_set', request.user.id, get_client_ip(request)),
        limit=int(getattr(settings, 'ADMIN_BAN_SET_RATE_LIMIT', 60)),
        period_seconds=int(getattr(settings, 'ADMIN_BAN_SET_RATE_PERIOD', 60)),
    )
    if not rl.allowed:
        messages.error(request, 'Too many actions. Please wait and try again.')
        return redirect('admin-users')

    raw_minutes = (request.POST.get('minutes') or '').strip()
    try:
        minutes = int(raw_minutes)
    except Exception:
        minutes = 0

    minutes = max(0, minutes)
    # Safety cap: 365 days.
    minutes = min(minutes, 60 * 24 * 365)

    until = None
    if minutes > 0:
        until = timezone.now() + timedelta(minutes=minutes)
        profile.chat_banned_until = until
        profile.save(update_fields=['chat_banned_until'])
        messages.success(request, f'Banned {target.username} for {minutes} minutes')
    else:
        profile.chat_banned_until = None
        profile.save(update_fields=['chat_banned_until'])
        messages.success(request, f'Unbanned {target.username}')

    # Realtime: notify the user (all open tabs) that their ban status changed.
    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"notify_user_{target.id}",
            {
                'type': 'chat_ban_status_notify_handler',
                'banned': bool(until),
                'until': until.isoformat() if until else '',
                'by_username': getattr(request.user, 'username', '') or '',
            },
        )
    except Exception:
        pass

    referer = (request.META.get('HTTP_REFERER') or '').strip()
    if referer and url_has_allowed_host_and_scheme(
        url=referer,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(referer)

    return redirect('admin-users')


@login_required
def admin_reports_view(request):
    if not request.user.is_staff:
        raise Http404()

    status = (request.GET.get('status') or '').strip().lower()
    qs = UserReport.objects.select_related('reporter', 'reported_user', 'handled_by')
    if status in {UserReport.STATUS_OPEN, UserReport.STATUS_RESOLVED, UserReport.STATUS_DISMISSED}:
        qs = qs.filter(status=status)

    reports = qs[:200]
    return render(request, 'a_rtchat/admin_reports.html', {
        'reports': reports,
        'status': status,
    })


@login_required
def admin_report_update_status_view(request, report_id: int):
    if request.method != 'POST':
        raise Http404()
    if not request.user.is_staff:
        raise Http404()

    report = get_object_or_404(UserReport, pk=report_id)
    new_status = (request.POST.get('status') or '').strip().lower()
    if new_status not in {UserReport.STATUS_OPEN, UserReport.STATUS_RESOLVED, UserReport.STATUS_DISMISSED}:
        messages.error(request, 'Invalid status')
        return redirect('admin-reports')

    report.status = new_status
    report.handled_by = request.user
    report.handled_at = timezone.now()
    note = (request.POST.get('note') or '').strip()
    if note:
        report.resolution_note = note
    report.save(update_fields=['status', 'handled_by', 'handled_at', 'resolution_note'])
    messages.success(request, f'Updated report #{report.id}')
    return redirect('admin-reports')


@login_required
def admin_support_enquiries_view(request):
    if not request.user.is_staff:
        raise Http404()

    status = (request.GET.get('status') or '').strip().lower()
    qs = SupportEnquiry.objects.select_related('user')
    if status in {SupportEnquiry.STATUS_OPEN, SupportEnquiry.STATUS_RESOLVED}:
        qs = qs.filter(status=status)

    enquiries = qs[:200]
    open_count = SupportEnquiry.objects.filter(status=SupportEnquiry.STATUS_OPEN).count()
    resolved_count = SupportEnquiry.objects.filter(status=SupportEnquiry.STATUS_RESOLVED).count()

    banner_message = ''
    banner_active = False
    try:
        from a_rtchat.models import GlobalAnnouncement

        ann = GlobalAnnouncement.objects.filter(pk=1).first()
        if ann is not None:
            banner_message = (ann.message or '').strip()
            banner_active = bool(ann.is_active and banner_message)
    except Exception:
        pass

    return render(request, 'a_rtchat/admin_support_enquiries.html', {
        'enquiries': enquiries,
        'status': status,
        'open_count': int(open_count or 0),
        'resolved_count': int(resolved_count or 0),
        'banner_message': banner_message,
        'banner_active': banner_active,
    })


@login_required
def admin_support_enquiry_update_status_view(request, enquiry_id: int):
    if request.method != 'POST':
        raise Http404()
    if not request.user.is_staff:
        raise Http404()

    enquiry = get_object_or_404(SupportEnquiry, pk=enquiry_id)
    new_status = (request.POST.get('status') or '').strip().lower()
    if new_status not in {SupportEnquiry.STATUS_OPEN, SupportEnquiry.STATUS_RESOLVED}:
        messages.error(request, 'Invalid status')
        return redirect('admin-support-enquiries')

    enquiry.status = new_status
    note = (request.POST.get('note') or '').strip()
    enquiry.admin_note = note
    enquiry.save(update_fields=['status', 'admin_note'])

    messages.success(request, f'Updated enquiry #{enquiry.id}')
    status = (request.POST.get('next_status') or '').strip().lower()
    if status in {SupportEnquiry.STATUS_OPEN, SupportEnquiry.STATUS_RESOLVED}:
        return redirect(f"{reverse('admin-support-enquiries')}?status={status}")
    return redirect('admin-support-enquiries')


@login_required
def admin_support_enquiry_reply_view(request, enquiry_id: int):
    if request.method != 'POST':
        raise Http404()
    if not request.user.is_staff:
        raise Http404()

    enquiry = get_object_or_404(SupportEnquiry, pk=enquiry_id)
    reply = (request.POST.get('reply') or '').strip()
    if not reply:
        messages.error(request, 'Reply cannot be empty')
        return redirect('admin-support-enquiries')

    try:
        enquiry.admin_reply = reply
        enquiry.replied_at = timezone.now()
        enquiry.status = SupportEnquiry.STATUS_RESOLVED
        enquiry.save(update_fields=['admin_reply', 'replied_at', 'status'])
    except Exception:
        enquiry.admin_reply = reply
        enquiry.status = SupportEnquiry.STATUS_RESOLVED
        enquiry.save()

    # Persist notification (dropdown)
    try:
        from a_rtchat.models import Notification

        Notification.objects.create(
            user=enquiry.user,
            from_user=None,
            type='support',
            preview=f"From Vixogram Team: {reply}"[:180],
            url='/profile/support/',
        )
    except Exception:
        pass

    # Realtime: notify the user (all open tabs) via notify websocket.
    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"notify_user_{enquiry.user_id}",
            {
                'type': 'support_notify_handler',
                'preview': f"From Vixogram Team: {reply}"[:180],
                'url': '/profile/support/',
            },
        )
    except Exception:
        pass

    messages.success(request, f"Replied to enquiry #{enquiry.id}")
    status = (request.POST.get('next_status') or '').strip().lower()
    if status in {SupportEnquiry.STATUS_OPEN, SupportEnquiry.STATUS_RESOLVED}:
        return redirect(f"{reverse('admin-support-enquiries')}?status={status}")
    return redirect('admin-support-enquiries')


@login_required
def admin_global_announcement_update_view(request):
    if request.method != 'POST':
        raise Http404()
    if not request.user.is_staff:
        raise Http404()

    raw_message = (request.POST.get('message') or '').strip()
    # If admin pastes the prefix, avoid duplicating it in UI.
    lowered = raw_message.lower()
    for prefix in ('team vixogram:', 'team vixogram -', 'team vixogram'):
        if lowered.startswith(prefix):
            raw_message = raw_message[len(prefix):].lstrip(' :-')
            break

    is_active = bool(request.POST.get('is_active'))
    if not raw_message:
        is_active = False

    try:
        from a_rtchat.models import GlobalAnnouncement

        channel_layer = None
        try:
            from channels.layers import get_channel_layer
            channel_layer = get_channel_layer()
        except Exception:
            channel_layer = None

        ann, _ = GlobalAnnouncement.objects.get_or_create(pk=1)
        ann.message = raw_message
        ann.is_active = bool(is_active)
        ann.updated_by = request.user
        ann.save(update_fields=['message', 'is_active', 'updated_by', 'updated_at'])

        # Realtime: broadcast to all connected clients.
        try:
            if channel_layer is not None:
                async_to_sync(channel_layer.group_send)(
                    'global_announcement',
                    {
                        'type': 'global_announcement_handler',
                        'active': bool(ann.is_active),
                        'message': (ann.message or '').strip(),
                    },
                )
        except Exception:
            pass

        if ann.is_active:
            messages.success(request, 'Global banner enabled')
        else:
            messages.success(request, 'Global banner disabled')
    except Exception:
        messages.error(request, 'Could not update global banner')

    next_url = (request.POST.get('next') or '').strip()
    if next_url and url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)

    referer = (request.META.get('HTTP_REFERER') or '').strip()
    if referer and url_has_allowed_host_and_scheme(
        url=referer,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(referer)

    return redirect('admin-support-enquiries')


def _today_localdate():
    try:
        return timezone.localdate()
    except Exception:
        return timezone.now().date()


def _global_online_user_count() -> int:
    """Best-effort global online users count.

    Presence is driven by websockets updating ChatGroup.users_online.
    """
    try:
        through = ChatGroup.users_online.through
        return int(through.objects.values('user_id').distinct().count())
    except Exception:
        try:
            User = get_user_model()
            return int(User.objects.filter(online_in_groups__isnull=False).distinct().count())
        except Exception:
            return 0


def _get_and_update_peak_today(current: int) -> int:
    today = _today_localdate().isoformat()
    key = f"admin:online_peak:{today}"
    try:
        prev = int(cache.get(key) or 0)
    except Exception:
        prev = 0
    peak = max(prev, int(current or 0))
    try:
        cache.set(key, peak, timeout=60 * 60 * 48)
    except Exception:
        pass
    return peak


@login_required
def admin_analytics_live_view(request):
    """Lightweight live metrics for polling (staff only)."""
    if not request.user.is_staff:
        raise Http404()

    today = _today_localdate()
    now = timezone.now()

    online_now = _global_online_user_count()
    peak_today = _get_and_update_peak_today(online_now)

    # Today's counts used for quick refresh without reloading whole page.
    messages_today = GroupMessage.objects.filter(created__date=today).count()
    blocked_today = BlockedMessageEvent.objects.filter(created__date=today).count()
    reports_open = UserReport.objects.filter(status=UserReport.STATUS_OPEN).count()
    enquiries_open = SupportEnquiry.objects.filter(status=SupportEnquiry.STATUS_OPEN).count()

    return JsonResponse({
        'ok': True,
        'ts': now.isoformat(),
        'online_now': int(online_now),
        'peak_today': int(peak_today),
        'messages_today': int(messages_today),
        'blocked_today': int(blocked_today),
        'open_reports': int(reports_open),
        'open_enquiries': int(enquiries_open),
    })


@login_required
def admin_analytics_view(request):
    if not request.user.is_staff:
        raise Http404()

    User = get_user_model()
    today = _today_localdate()
    now = timezone.now()
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)

    # ---- Summary cards ----
    total_users = User.objects.count()
    new_users_24h = User.objects.filter(date_joined__gte=last_24h).count()

    online_now = _global_online_user_count()
    peak_today = _get_and_update_peak_today(online_now)

    messages_today = GroupMessage.objects.filter(created__date=today).count()
    messages_7d = GroupMessage.objects.filter(created__gte=last_7d).count()

    blocked_today = BlockedMessageEvent.objects.filter(created__date=today).count()
    yesterday = today - timedelta(days=1)
    blocked_yesterday = BlockedMessageEvent.objects.filter(created__date=yesterday).count()
    blocked_pct_vs_yesterday = None
    try:
        if blocked_yesterday > 0:
            blocked_pct_vs_yesterday = round(((blocked_today - blocked_yesterday) / blocked_yesterday) * 100, 1)
        elif blocked_today > 0:
            blocked_pct_vs_yesterday = 100.0
        else:
            blocked_pct_vs_yesterday = 0.0
    except Exception:
        blocked_pct_vs_yesterday = None

    # ---- Activity graph (daily last 7 days) ----
    start_day = today - timedelta(days=6)
    daily = (
        GroupMessage.objects
        .filter(created__date__gte=start_day)
        .annotate(day=TruncDate('created'))
        .values('day')
        .annotate(count=Count('id'))
        .order_by('day')
    )
    daily_map = {row['day']: int(row['count']) for row in daily}
    daily_labels = []
    daily_counts = []
    for i in range(7):
        d = start_day + timedelta(days=i)
        daily_labels.append(d.strftime('%b %d'))
        daily_counts.append(int(daily_map.get(d, 0)))

    # ---- Message quality split (last 7d, best-effort) ----
    # Note: AI moderation can be disabled; in that case allow/flag will be 0.
    allow_7d = ModerationEvent.objects.filter(created__gte=last_7d, action='allow', message__isnull=False).count()
    flag_7d = ModerationEvent.objects.filter(created__gte=last_7d, action='flag', message__isnull=False).count()
    block_ai_7d = ModerationEvent.objects.filter(created__gte=last_7d, action='block').count()
    block_other_7d = BlockedMessageEvent.objects.filter(created__gte=last_7d).exclude(scope='ai_block').count()
    blocked_total_7d = int(block_ai_7d + block_other_7d)

    quality_total = int(allow_7d + flag_7d + blocked_total_7d)
    quality = {
        'useful': int(allow_7d),
        'low': int(flag_7d),
        'spam': int(blocked_total_7d),
        'total': int(quality_total),
    }

    # ---- Top lists ----
    most_active = list(
        GroupMessage.objects
        .filter(created__gte=last_7d)
        .values('author_id', 'author__username')
        .annotate(messages=Count('id'))
        .order_by('-messages')[:10]
    )
    active_user_ids = [row['author_id'] for row in most_active]

    quality_by_user = {
        row['user_id']: row
        for row in (
            ModerationEvent.objects
            .filter(created__gte=last_7d, user_id__in=active_user_ids, message__isnull=False)
            .values('user_id')
            .annotate(
                allow=Count('id', filter=Q(action='allow')),
                flag=Count('id', filter=Q(action='flag')),
            )
        )
    }

    for row in most_active:
        qrow = quality_by_user.get(row['author_id'])
        allow_c = int((qrow or {}).get('allow') or 0)
        flag_c = int((qrow or {}).get('flag') or 0)
        denom = allow_c + flag_c
        row['quality_score'] = round((allow_c / denom) * 100, 1) if denom > 0 else None

    top_spammers = list(
        BlockedMessageEvent.objects
        .filter(created__gte=last_7d)
        .values('user_id', 'user__username')
        .annotate(spam=Count('id'))
        .order_by('-spam')[:10]
    )

    spam_user_ids = [row['user_id'] for row in top_spammers]
    blocked_profiles = {
        p['user_id']: bool(p['chat_blocked'])
        for p in Profile.objects.filter(user_id__in=spam_user_ids).values('user_id', 'chat_blocked')
    }

    for row in top_spammers:
        row['auto_action'] = 'Blocked from chat' if blocked_profiles.get(row['user_id']) else '—'

    # ---- Room stats (today) ----
    msgs_by_room = {
        row['group_id']: row
        for row in (
            GroupMessage.objects
            .filter(created__date=today)
            .values('group_id')
            .annotate(messages=Count('id'), active_users=Count('author_id', distinct=True))
        )
    }

    blocked_by_room = {
        row['room_id']: int(row['blocked'])
        for row in (
            BlockedMessageEvent.objects
            .filter(created__date=today)
            .values('room_id')
            .annotate(blocked=Count('id'))
        )
    }
    blocked_ai_by_room = {
        row['room_id']: int(row['blocked'])
        for row in (
            ModerationEvent.objects
            .filter(created__date=today, action='block')
            .values('room_id')
            .annotate(blocked=Count('id'))
        )
    }

    rooms = list(
        ChatGroup.objects
        .exclude(group_name='online-status')
        .order_by('groupchat_name', 'group_name')
    )

    room_rows = []
    for room in rooms:
        m = msgs_by_room.get(room.id, {})
        msg_c = int(m.get('messages') or 0)
        act_u = int(m.get('active_users') or 0)
        blocked_c = int(blocked_by_room.get(room.id, 0) + blocked_ai_by_room.get(room.id, 0))
        denom = msg_c + blocked_c
        spam_ratio = round((blocked_c / denom) * 100, 1) if denom > 0 else 0.0

        display = getattr(room, 'groupchat_name', None) or getattr(room, 'code_room_name', None) or getattr(room, 'group_name', '')
        room_rows.append({
            'name': display,
            'group_name': getattr(room, 'group_name', ''),
            'messages': msg_c,
            'active_users': act_u,
            'blocked': blocked_c,
            'spam_ratio': spam_ratio,
        })

    # Sort rooms: most messages today first, then blocked.
    room_rows.sort(key=lambda r: (r['messages'], r['blocked']), reverse=True)
    room_rows = room_rows[:20]

    # ---- Reports & moderation ----
    reports_today = UserReport.objects.filter(created_at__date=today).count()
    reports_open = UserReport.objects.filter(status=UserReport.STATUS_OPEN).count()
    enquiries_today = SupportEnquiry.objects.filter(created_at__date=today).count()
    enquiries_open = SupportEnquiry.objects.filter(status=SupportEnquiry.STATUS_OPEN).count()

    auto_actions_today = BlockedMessageEvent.objects.filter(created__date=today, auto_muted_seconds__gt=0).count()
    pending_actions = int(reports_open + enquiries_open)

    context = {
        'total_users': int(total_users),
        'new_users_24h': int(new_users_24h),
        'online_now': int(online_now),
        'peak_today': int(peak_today),
        'messages_today': int(messages_today),
        'messages_7d': int(messages_7d),
        'blocked_today': int(blocked_today),
        'blocked_pct_vs_yesterday': blocked_pct_vs_yesterday,
        'daily_labels_json': json.dumps(daily_labels),
        'daily_counts_json': json.dumps(daily_counts),
        'quality_json': json.dumps(quality),
        'most_active': most_active,
        'top_spammers': top_spammers,
        'room_rows': room_rows,
        'reports_today': int(reports_today),
        'enquiries_today': int(enquiries_today),
        'auto_actions_today': int(auto_actions_today),
        'pending_actions': int(pending_actions),
        'reports_open': int(reports_open),
        'enquiries_open': int(enquiries_open),
    }

    return render(request, 'a_rtchat/admin_analytics.html', context)


@login_required
def call_view(request, chatroom_name):
    """Agora call UI for private 1:1 chats."""
    if _is_chat_banned(request.user):
        return render(request, '403.html', status=403)

    chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name)

    if _is_chat_blocked(request.user):
        raise Http404()

    if not getattr(chat_group, 'is_private', False):
        raise Http404()

    if request.user not in chat_group.members.all():
        raise Http404()

    call_type = (request.GET.get('type') or 'voice').lower()
    if call_type not in {'voice', 'video'}:
        call_type = 'voice'

    role = (request.GET.get('role') or 'caller').lower()
    if role not in {'caller', 'callee'}:
        role = 'caller'

    member_usernames = list(chat_group.members.values_list('username', flat=True))

    return render(request, 'a_rtchat/call.html', {
        'chat_group': chat_group,
        'chatroom_name': chatroom_name,
        'call_type': call_type,
        'member_usernames': member_usernames,
        'member_usernames_json': json.dumps(member_usernames),
        'call_role': role,
        'agora_app_id': getattr(settings, 'AGORA_APP_ID', ''),
    })


@login_required
def agora_token_view(request, chatroom_name):
    """Return Agora RTC token for the given chatroom (members only)."""
    if _is_chat_banned(request.user):
        return JsonResponse({'error': 'banned'}, status=403)

    chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name)

    rl = check_rate_limit(
        make_key('agora_token', chatroom_name, get_client_ip(request), getattr(request.user, 'id', 'anon')),
        limit=int(getattr(settings, 'AGORA_TOKEN_RATE_LIMIT', 30)),
        period_seconds=int(getattr(settings, 'AGORA_TOKEN_RATE_PERIOD', 300)),
    )
    if not rl.allowed:
        resp = JsonResponse({'error': 'rate_limited'}, status=429)
        resp.headers['Retry-After'] = str(rl.retry_after)
        return resp

    if _is_chat_blocked(request.user):
        raise Http404()

    if not getattr(chat_group, 'is_private', False):
        raise Http404()

    if request.user not in chat_group.members.all():
        raise Http404()

    call_type = (request.GET.get('type') or 'voice').lower()
    if call_type not in {'voice', 'video'}:
        call_type = 'voice'

    # Free minutes: 4 min voice, 2 min video (rolling window per room).
    default_limit = 2 * 60 if call_type == 'video' else 4 * 60
    try:
        free_limit_seconds = int(getattr(settings, 'FREE_CALL_LIMIT_SECONDS_VIDEO' if call_type == 'video' else 'FREE_CALL_LIMIT_SECONDS_VOICE', default_limit) or default_limit)
    except Exception:
        free_limit_seconds = default_limit
    free_limit_seconds = max(0, int(free_limit_seconds or 0))

    try:
        user_id = int(getattr(request.user, 'id', 0) or 0)
    except Exception:
        user_id = 0

    used_key = f"call_free_used:{chat_group.group_name}:{call_type}:{user_id}"
    join_key = f"call_free_join:{chat_group.group_name}:{call_type}:{user_id}"

    try:
        used = int(cache.get(used_key) or 0)
    except Exception:
        used = 0

    # Include in-flight usage if a join timestamp exists.
    try:
        start_ts = cache.get(join_key)
        if start_ts:
            used = max(0, used + max(0, int(time.time() - float(start_ts))))
    except Exception:
        pass

    free_seconds_left = max(0, int(free_limit_seconds - max(0, used)))

    # If no time left, don't issue tokens.
    if free_limit_seconds > 0 and free_seconds_left <= 0:
        return JsonResponse({
            'error': 'free_limit_reached',
            'free_limit_seconds': int(free_limit_seconds),
            'free_seconds_left': 0,
            'channel': chat_group.group_name,
            'app_id': getattr(settings, 'AGORA_APP_ID', ''),
        }, status=403)

    try:
        token, uid = build_rtc_token(channel_name=chat_group.group_name)
    except Exception as exc:
        return JsonResponse({'error': str(exc)}, status=500)

    return JsonResponse({
        'token': token,
        'uid': uid,
        'channel': chat_group.group_name,
        'app_id': getattr(settings, 'AGORA_APP_ID', ''),
        'free_limit_seconds': int(free_limit_seconds),
        'free_seconds_left': int(free_seconds_left),
    })


@login_required
def call_invite_view(request, chatroom_name):
    """Broadcast an incoming-call invite to the other member(s) in this room."""
    if _is_chat_banned(request.user):
        return JsonResponse({'error': 'banned'}, status=403)

    if request.method != 'POST':
        raise Http404()

    if _is_chat_blocked(request.user):
        raise Http404()

    rl = check_rate_limit(
        make_key('call_invite', chatroom_name, request.user.id),
        limit=int(getattr(settings, 'CALL_INVITE_RATE_LIMIT', 6)),
        period_seconds=int(getattr(settings, 'CALL_INVITE_RATE_PERIOD', 60)),
    )
    if not rl.allowed:
        resp = JsonResponse({'error': 'rate_limited'}, status=429)
        resp.headers['Retry-After'] = str(rl.retry_after)
        return resp

    chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name)
    if not getattr(chat_group, 'is_private', False):
        raise Http404()
    if request.user not in chat_group.members.all():
        raise Http404()

    call_type = (request.POST.get('type') or 'voice').lower()
    if call_type not in {'voice', 'video'}:
        call_type = 'voice'

    # Mark this invite as pending (dedupe decline events)
    invite_key = f"call_invite:{chat_group.group_name}:{call_type}"
    cache.set(invite_key, 'pending', timeout=2 * 60)

    channel_layer = get_channel_layer()
    event = {
        'type': 'call_invite_handler',
        'author_id': request.user.id,
        'from_username': request.user.username,
        'call_type': call_type,
    }
    async_to_sync(channel_layer.group_send)(chatroom_channel_group_name(chat_group), event)

    # Also notify each recipient on their personal notifications channel so they
    # receive the call even if they switched to another chatroom page.
    call_url = reverse('chat-call', kwargs={'chatroom_name': chat_group.group_name}) + f"?type={call_type}&role=callee"
    call_event_url = reverse('chat-call-event', kwargs={'chatroom_name': chat_group.group_name})
    for member in chat_group.members.exclude(id=request.user.id):
        try:
            from a_rtchat.notifications import should_send_realtime_notification

            if not should_send_realtime_notification(user_id=member.id):
                continue
        except Exception:
            pass

        async_to_sync(channel_layer.group_send)(
            f"notify_user_{member.id}",
            {
                'type': 'call_invite_notify_handler',
                'from_username': request.user.username,
                'call_type': call_type,
                'chatroom_name': chat_group.group_name,
                'call_url': call_url,
                'call_event_url': call_event_url,
            },
        )

    return JsonResponse({'ok': True})

@login_required
def call_presence_view(request, chatroom_name):
    """Announce a participant joining/leaving a call (UI only)."""
    if _is_chat_banned(request.user):
        return JsonResponse({'error': 'banned'}, status=403)

    if request.method != 'POST':
        raise Http404()

    if _is_chat_blocked(request.user):
        raise Http404()

    rl = check_rate_limit(
        make_key('call_presence', chatroom_name, request.user.id),
        limit=int(getattr(settings, 'CALL_PRESENCE_RATE_LIMIT', 60)),
        period_seconds=int(getattr(settings, 'CALL_PRESENCE_RATE_PERIOD', 60)),
    )
    if not rl.allowed:
        resp = JsonResponse({'error': 'rate_limited'}, status=429)
        resp.headers['Retry-After'] = str(rl.retry_after)
        return resp

    chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name)
    if not getattr(chat_group, 'is_private', False):
        raise Http404()
    if request.user not in chat_group.members.all():
        raise Http404()

    action = (request.POST.get('action') or 'join').lower()
    if action not in {'join', 'leave'}:
        action = 'join'

    call_type = (request.POST.get('type') or 'voice').lower()
    if call_type not in {'voice', 'video'}:
        call_type = 'voice'

    # --- Free call usage tracking (per user + room + call type) ---
    # This prevents users from resetting the free timer by leaving and rejoining.
    usage_timeout = 6 * 60 * 60  # keep usage within a rolling window
    try:
        user_id = int(getattr(request.user, 'id', 0) or 0)
    except Exception:
        user_id = 0

    join_key = f"call_free_join:{chat_group.group_name}:{call_type}:{user_id}"
    used_key = f"call_free_used:{chat_group.group_name}:{call_type}:{user_id}"

    now_ts = time.time()

    try:
        uid = int(request.POST.get('uid') or '0')
    except ValueError:
        uid = 0

    if user_id:
        try:
            if action == 'join':
                # Only set if absent so multiple joins don't reset the timer.
                cache.add(join_key, now_ts, timeout=usage_timeout)
            else:
                start_ts = cache.get(join_key)
                if start_ts:
                    try:
                        elapsed = max(0, int(now_ts - float(start_ts)))
                    except Exception:
                        elapsed = 0

                    try:
                        used = int(cache.get(used_key) or 0)
                    except Exception:
                        used = 0

                    cache.set(used_key, max(0, used + elapsed), timeout=usage_timeout)
                cache.delete(join_key)
        except Exception:
            pass

    channel_layer = get_channel_layer()
    event = {
        'type': 'call_presence_handler',
        'action': action,
        'uid': uid,
        'username': request.user.username,
        'call_type': call_type,
    }
    async_to_sync(channel_layer.group_send)(chatroom_channel_group_name(chat_group), event)
    return JsonResponse({'ok': True})


@login_required
def call_event_view(request, chatroom_name):
    """Persist call started/ended markers to chat + broadcast."""
    if _is_chat_banned(request.user):
        return JsonResponse({'error': 'banned'}, status=403)

    if request.method != 'POST':
        raise Http404()

    if _is_chat_blocked(request.user):
        raise Http404()

    rl = check_rate_limit(
        make_key('call_event', chatroom_name, request.user.id),
        limit=int(getattr(settings, 'CALL_EVENT_RATE_LIMIT', 30)),
        period_seconds=int(getattr(settings, 'CALL_EVENT_RATE_PERIOD', 60)),
    )
    if not rl.allowed:
        resp = JsonResponse({'error': 'rate_limited'}, status=429)
        resp.headers['Retry-After'] = str(rl.retry_after)
        return resp

    chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name)
    if not getattr(chat_group, 'is_private', False):
        raise Http404()
    if request.user not in chat_group.members.all():
        raise Http404()

    action = (request.POST.get('action') or '').lower()
    if action not in {'start', 'end', 'decline'}:
        return JsonResponse({'error': 'Invalid action'}, status=400)

    call_type = (request.POST.get('type') or 'voice').lower()
    if call_type not in {'voice', 'video'}:
        call_type = 'voice'

    # Ensure we only create ONE start and ONE end marker per call session.
    # This also protects against duplicates caused by both users sending events
    # and browser beforeunload sending multiple beacons.
    call_state_key = f"call_state:{chat_group.group_name}:{call_type}"
    is_active = bool(cache.get(call_state_key))

    invite_key = f"call_invite:{chat_group.group_name}:{call_type}"
    is_pending_invite = bool(cache.get(invite_key))

    if action == 'start' and is_active:
        return JsonResponse({'ok': True, 'deduped': True})
    # If the call never became active but an invite is still pending,
    # we still want an instant "end" (cancel) to propagate to everyone.
    if action == 'end' and (not is_active) and (not is_pending_invite):
        return JsonResponse({'ok': True, 'deduped': True})
    if action == 'decline' and not is_pending_invite:
        return JsonResponse({'ok': True, 'deduped': True})

    if action == 'start':
        body = f"[CALL] {call_type.title()} call started"
    elif action == 'end':
        body = f"[CALL] {call_type.title()} call ended"
    else:
        body = f"[CALL] {call_type.title()} call declined"

    message = GroupMessage.objects.create(
        body=body,
        author=request.user,
        group=chat_group,
    )

    # Retention: keep only the newest messages per room (best-effort).
    # Public/group rooms and private rooms can use different caps.
    try:
        from a_rtchat.retention import trim_chat_group_messages

        is_private = bool(getattr(chat_group, 'is_private', False))
        if is_private:
            keep_last = int(getattr(settings, 'PRIVATE_CHAT_MAX_MESSAGES_PER_ROOM', 1000))
        else:
            keep_last = int(getattr(settings, 'CHAT_MAX_MESSAGES_PER_ROOM', 300))

        trim_chat_group_messages(
            chat_group_id=chat_group.id,
            keep_last=max(1, keep_last),
        )
    except Exception:
        pass

    # Update call state
    if action == 'start':
        # Keep call state for a while; end will delete it.
        cache.set(call_state_key, 'active', timeout=6 * 60 * 60)
        cache.delete(invite_key)
    else:
        if action == 'end':
            cache.delete(call_state_key)
        cache.delete(invite_key)

    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(chatroom_channel_group_name(chat_group), {
        'type': 'message_handler',
        'message_id': message.id,
    })

    # If one user ends the call, notify everyone in the room so they can auto-hangup.
    if action == 'end':
        async_to_sync(channel_layer.group_send)(chatroom_channel_group_name(chat_group), {
            'type': 'call_control_handler',
            'action': 'end',
            'from_username': request.user.username,
            'call_type': call_type,
        })

        for member in chat_group.members.exclude(id=request.user.id):
            try:
                from a_rtchat.notifications import should_send_realtime_notification

                if not should_send_realtime_notification(user_id=member.id):
                    continue
            except Exception:
                pass

            async_to_sync(channel_layer.group_send)(
                f"notify_user_{member.id}",
                {
                    'type': 'call_control_notify_handler',
                    'action': 'end',
                    'from_username': request.user.username,
                    'call_type': call_type,
                    'chatroom_name': chat_group.group_name,
                },
            )

    if action == 'decline':
        async_to_sync(channel_layer.group_send)(chatroom_channel_group_name(chat_group), {
            'type': 'call_control_handler',
            'action': 'decline',
            'from_username': request.user.username,
            'call_type': call_type,
        })

        for member in chat_group.members.exclude(id=request.user.id):
            async_to_sync(channel_layer.group_send)(
                f"notify_user_{member.id}",
                {
                    'type': 'call_control_notify_handler',
                    'action': 'decline',
                    'from_username': request.user.username,
                    'call_type': call_type,
                    'chatroom_name': chat_group.group_name,
                },
            )

    return JsonResponse({'ok': True})


@login_required
def push_config(request):
    """Return Firebase web-push public config for the current session.

    This is not a secret, but keeping it out of the base HTML avoids showing it
    in page source/inspect for every page.
    """
    if request.method != 'GET':
        raise Http404()

    if not getattr(settings, 'FIREBASE_ENABLED', False):
        resp = JsonResponse({'enabled': False}, status=404)
        resp['Cache-Control'] = 'no-store'
        return resp

    vapid_key = (getattr(settings, 'FIREBASE_VAPID_PUBLIC_KEY', '') or '').strip()
    raw_cfg = (getattr(settings, 'FIREBASE_CONFIG_JSON', '{}') or '{}').strip()
    try:
        cfg = json.loads(raw_cfg) if raw_cfg else {}
    except Exception:
        cfg = {}

    resp = JsonResponse({
        'enabled': True,
        'vapidKey': vapid_key,
        'config': cfg,
    })
    resp['Cache-Control'] = 'no-store'
    return resp