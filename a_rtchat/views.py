import json

from django.shortcuts import render, get_object_or_404, redirect 
from django.contrib.auth.decorators import login_required
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.http import HttpResponse, Http404
from django.http import JsonResponse
from django.utils import timezone
from django.contrib import messages
from django.core.cache import cache
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.urls import reverse
from django.db.models import Q
from django.utils.http import url_has_allowed_host_and_scheme
from a_users.models import Profile
from .models import *
from .forms import *
from .agora import build_rtc_token
from .moderation import moderate_message
from .channels_utils import chatroom_channel_group_name
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


CHAT_UPLOAD_LIMIT_PER_ROOM = getattr(settings, 'CHAT_UPLOAD_LIMIT_PER_ROOM', 20)
CHAT_UPLOAD_MAX_BYTES = getattr(settings, 'CHAT_UPLOAD_MAX_BYTES', 10 * 1024 * 1024)


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

@login_required
def chat_view(request, chatroom_name='public-chat'):
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
    
    # Show the latest 30 messages but render them oldest -> newest (so refresh doesn't invert order)
    latest_messages = list(chat_group.chat_messages.order_by('-created')[:30])
    latest_messages.reverse()
    chat_messages = latest_messages
    form = ChatmessageCreateForm()

    chat_blocked = _is_chat_blocked(request.user)
    chat_muted_seconds = get_muted_seconds(getattr(request.user, 'id', 0))
    
    other_user = None
    if chat_group.is_private:
        if chat_blocked:
            messages.error(request, 'You are blocked from private chats.')
            return redirect('chatroom', 'public-chat')
        if request.user not in chat_group.members.all():
            raise Http404()
        for member in chat_group.members.all():
            if member != request.user:
                other_user = member
                break
            
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

    uploads_used = 0
    uploads_remaining = None
    if getattr(chat_group, 'is_private', False) and getattr(chat_group, 'is_code_room', False):
        uploads_used = (
            chat_group.chat_messages
            .filter(author=request.user)
            .exclude(file__isnull=True)
            .exclude(file='')
            .count()
        )
        uploads_remaining = max(0, CHAT_UPLOAD_LIMIT_PER_ROOM - uploads_used)
    
    if request.htmx:
        if chat_blocked:
            return HttpResponse('', status=403)

        if chat_muted_seconds > 0:
            resp = HttpResponse('', status=429)
            resp.headers['Retry-After'] = str(chat_muted_seconds)
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
            resp = HttpResponse('', status=429)
            resp.headers['Retry-After'] = str(room_rl.retry_after)
            return resp

        # Duplicate message detection (same message spam).
        raw_body = (request.POST.get('body') or '').strip()
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
                resp = HttpResponse('', status=429)
                resp.headers['Retry-After'] = str(muted5 or fast_retry)
                return resp

        # Rate limit message sends (HTMX path).
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
            return resp

        # AI moderation (Gemini): run after cheap anti-spam checks but before saving.
        pending_moderation = None
        if raw_body and int(getattr(settings, 'AI_MODERATION_ENABLED', 1)):
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
            event = {
                'type': 'message_handler',
                'message_id': message.id,
            }
            async_to_sync(channel_layer.group_send)(chatroom_channel_group_name(chat_group), event)

            # HTMX request: no HTML swap needed; websocket will append the rendered message.
            return HttpResponse('', status=204)

        # Invalid (e.g., empty/whitespace) message -> do nothing
        return HttpResponse('', status=204)
    
    context = {
        'chat_messages' : chat_messages, 
        'form' : form,
        'other_user' : other_user,
        'chatroom_name' : chatroom_name,
        'chat_group' : chat_group,
        'chat_blocked': chat_blocked,
        'chat_muted_seconds': chat_muted_seconds,
        # Show all group chats so admin-created rooms appear in UI even before the user joins.
        'sidebar_groupchats': ChatGroup.objects.filter(groupchat_name__isnull=False).exclude(group_name='online-status').order_by('groupchat_name'),
        'sidebar_privatechats': [] if chat_blocked else request.user.chat_groups.filter(is_private=True, is_code_room=False).exclude(group_name='online-status'),
        'sidebar_code_rooms': [] if chat_blocked else request.user.chat_groups.filter(is_private=True, is_code_room=True).exclude(group_name='online-status'),
        'private_room_create_form': PrivateRoomCreateForm(),
        'room_code_join_form': RoomCodeJoinForm(),
        'uploads_used': uploads_used,
        'uploads_remaining': uploads_remaining,
        'upload_limit': CHAT_UPLOAD_LIMIT_PER_ROOM,
    }
    
    return render(request, 'a_rtchat/chat.html', context)


@login_required
def create_private_room(request):
    if request.method != 'POST':
        return redirect('home')

    if _is_chat_blocked(request.user):
        messages.error(request, 'You are blocked from creating private rooms.')
        return redirect('home')

    rl = check_rate_limit(
        make_key('private_room_create', request.user.id, get_client_ip(request)),
        limit=int(getattr(settings, 'PRIVATE_ROOM_CREATE_RATE_LIMIT', 5)),
        period_seconds=int(getattr(settings, 'PRIVATE_ROOM_CREATE_RATE_PERIOD', 300)),
    )
    if not rl.allowed:
        messages.error(request, 'Too many attempts. Please wait and try again.')
        return redirect('home')

    form = PrivateRoomCreateForm(request.POST)
    if not form.is_valid():
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
    messages.success(request, f'Private room created. Share code: {room.room_code}')
    return redirect('chatroom', room.group_name)


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

    room.members.add(request.user)
    return redirect('chatroom', room.group_name)

@login_required
def get_or_create_chatroom(request, username):
    if _is_chat_blocked(request.user):
        messages.error(request, 'You are blocked from private chats.')
        return redirect('home')
    if request.user.username == username:
        return redirect('home')
    
    other_user = User.objects.get(username = username)
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
def chat_file_upload(request, chatroom_name):
    chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name)

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

    # Uploads allowed ONLY in private code rooms.
    if not getattr(chat_group, 'is_private', False) or not getattr(chat_group, 'is_code_room', False):
        raise Http404()

    if request.user not in chat_group.members.all():
        raise Http404()

    # If HTMX isn't present for some reason, still allow a normal POST fallback.
    is_htmx = bool(getattr(request, 'htmx', False))

    if not request.FILES or 'file' not in request.FILES:
        if is_htmx:
            return HttpResponse(
                '<div class="text-xs text-red-400">Please choose a file first.</div>',
                status=200,
            )
        return redirect('chatroom', chatroom_name)

    upload = request.FILES['file']

    # Enforce max file size
    if getattr(upload, 'size', 0) > CHAT_UPLOAD_MAX_BYTES:
        return HttpResponse(
            '<div class="text-xs text-red-400">File is too large.</div>',
            status=200,
        )

    # Enforce content type: images/videos only
    content_type = (getattr(upload, 'content_type', '') or '').lower()
    if not (content_type.startswith('image/') or content_type.startswith('video/')):
        return HttpResponse(
            '<div class="text-xs text-red-400">Only photos/videos are allowed.</div>',
            status=200,
        )

    # Enforce per-user per-room upload limit
    uploads_used = (
        chat_group.chat_messages
        .filter(author=request.user)
        .exclude(file__isnull=True)
        .exclude(file='')
        .count()
    )
    if uploads_used >= CHAT_UPLOAD_LIMIT_PER_ROOM:
        return HttpResponse(
            f'<div class="text-xs text-red-400">Upload limit reached ({CHAT_UPLOAD_LIMIT_PER_ROOM}/{CHAT_UPLOAD_LIMIT_PER_ROOM}).</div>',
            status=200,
        )

    message = GroupMessage.objects.create(
        file=upload,
        author=request.user,
        group=chat_group,
    )

    channel_layer = get_channel_layer()
    event = {
        'type': 'message_handler',
        'message_id': message.id,
    }
    async_to_sync(channel_layer.group_send)(chatroom_channel_group_name(chat_group), event)

    # Clear any prior error text + let the client know it can clear the file input.
    response = HttpResponse('', status=200)
    if is_htmx:
        response.headers['HX-Trigger'] = 'chatFileUploaded'
    return response


@login_required
def chat_poll_view(request, chatroom_name):
    """Return new messages after a given message id (used as a realtime fallback)."""
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

    # Render a batch of messages using the same bubble template
    parts = []
    for message in new_messages:
        parts.append(render(request, 'a_rtchat/chat_message.html', {'message': message, 'user': request.user}).content.decode('utf-8'))

    last_id = new_messages[-1].id
    return JsonResponse({'messages_html': ''.join(parts), 'last_id': last_id, 'online_count': online_count})


@login_required
def message_edit_view(request, message_id: int):
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

    body = (request.POST.get('body') or '').strip()
    if not body:
        return JsonResponse({'error': 'Message cannot be empty'}, status=400)

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

    users = users[:200]

    user_ids = [u.id for u in users]
    existing = set(Profile.objects.filter(user_id__in=user_ids).values_list('user_id', flat=True))
    missing = [Profile(user_id=uid) for uid in user_ids if uid not in existing]
    if missing:
        Profile.objects.bulk_create(missing, ignore_conflicts=True)

    return render(request, 'a_rtchat/admin_users.html', {
        'q': q,
        'users': users,
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
def call_view(request, chatroom_name):
    """Agora call UI for private 1:1 chats."""
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
        'call_role': role,
        'agora_app_id': getattr(settings, 'AGORA_APP_ID', ''),
    })


@login_required
def agora_token_view(request, chatroom_name):
    """Return Agora RTC token for the given chatroom (members only)."""
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

    try:
        token, uid = build_rtc_token(channel_name=chat_group.group_name)
    except Exception as exc:
        return JsonResponse({'error': str(exc)}, status=500)

    return JsonResponse({
        'token': token,
        'uid': uid,
        'channel': chat_group.group_name,
        'app_id': getattr(settings, 'AGORA_APP_ID', ''),
    })


@login_required
def call_invite_view(request, chatroom_name):
    """Broadcast an incoming-call invite to the other member(s) in this room."""
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

    try:
        uid = int(request.POST.get('uid') or '0')
    except ValueError:
        uid = 0

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
    if action == 'end' and not is_active:
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

    if action == 'decline':
        async_to_sync(channel_layer.group_send)(chatroom_channel_group_name(chat_group), {
            'type': 'call_control_handler',
            'action': 'decline',
            'from_username': request.user.username,
            'call_type': call_type,
        })

    return JsonResponse({'ok': True})