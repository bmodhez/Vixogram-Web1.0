from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
import shortuuid
from PIL import Image
import os
import mimetypes

from .models_notifications import Notification
from .models_read import ChatReadState

class ChatGroup(models.Model):
    group_name = models.CharField(max_length=128, unique=True, blank=True)
    groupchat_name = models.CharField(max_length=128, null=True, blank=True)
    admin = models.ForeignKey(User, related_name='groupchats', blank=True, null=True, on_delete=models.SET_NULL)
    # Additional admins for this room (the `admin` field remains the room owner/creator).
    admins = models.ManyToManyField(User, related_name='admin_in_groups', blank=True)
    users_online = models.ManyToManyField(User, related_name='online_in_groups', blank=True)
    members = models.ManyToManyField(User, related_name='chat_groups', blank=True)
    is_private = models.BooleanField(default=False)
    # When enabled, only the room admin (and staff) can send messages.
    only_admins_can_send = models.BooleanField(default=False)
    allow_media_uploads = models.BooleanField(default=True)
    allow_members_invite_others = models.BooleanField(default=False)
    slow_mode_seconds = models.PositiveSmallIntegerField(default=0)
    created = models.DateTimeField(auto_now_add=True)
    # Private rooms that can be joined via a shareable code (not listed globally).
    is_code_room = models.BooleanField(default=False)
    room_code = models.CharField(max_length=16, unique=True, null=True, blank=True, db_index=True)
    code_room_name = models.CharField(max_length=128, null=True, blank=True)
    room_description = models.TextField(blank=True, default='')
    room_avatar = models.ImageField(upload_to='room_avatars/', null=True, blank=True)
    announcement_pinned = models.BooleanField(default=False)
    pinned_message = models.TextField(blank=True, default='')
    
    def __str__(self):
        return self.group_name

    def save(self, *args, **kwargs):
        if not self.group_name:
            self.group_name = shortuuid.uuid()

        if self.is_code_room and not self.room_code:
            su = shortuuid.ShortUUID()
            # Generate a reasonably short, unique code (case-insensitive friendly)
            alphabet = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ'
            su.set_alphabet(alphabet)
            for _ in range(20):
                candidate = su.random(length=8)
                if not ChatGroup.objects.filter(room_code=candidate).exists():
                    self.room_code = candidate
                    break
        super().save(*args, **kwargs)


class CodeRoomJoinRequest(models.Model):
    """Pending join requests for private code rooms.

    Users who join via room code are placed here until the room admin (or staff)
    admits them, at which point they are added to ChatGroup.members.
    """

    room = models.ForeignKey(ChatGroup, related_name='code_room_join_requests', on_delete=models.CASCADE)
    user = models.ForeignKey(User, related_name='code_room_join_requests', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    # Updated by the waiting page poll to indicate the requester is still present.
    last_seen_at = models.DateTimeField(default=timezone.now, db_index=True)
    admitted_at = models.DateTimeField(null=True, blank=True)
    admitted_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='admitted_code_room_join_requests',
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['room', 'user'], name='uniq_code_room_join_request_room_user'),
        ]
        indexes = [
            models.Index(fields=['room', 'admitted_at', '-created_at'], name='crjr_room_status_created_idx'),
            models.Index(fields=['room', 'admitted_at', '-last_seen_at'], name='crjr_room_status_seen_idx'),
        ]

    @property
    def is_pending(self):
        return self.admitted_at is None

    def mark_admitted(self, by_user=None):
        self.admitted_at = timezone.now()
        self.admitted_by = by_user
        self.save(update_fields=['admitted_at', 'admitted_by'])


class GlobalAnnouncement(models.Model):
    """A single global banner message shown site-wide (set by staff)."""

    message = models.CharField(max_length=300, blank=True, default='')
    is_active = models.BooleanField(default=False)
    updated_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='updated_global_announcements',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        label = (self.message or '').strip()
        if not label:
            label = '(empty)'
        return f"GlobalAnnouncement({label[:40]})"


class PrivateChatGroup(ChatGroup):
    class Meta:
        proxy = True
        verbose_name = 'Private chat'
        verbose_name_plural = 'Private chats'
    
    
class GroupMessage(models.Model):
    group = models.ForeignKey(ChatGroup, related_name='chat_messages', on_delete=models.CASCADE)
    poll = models.OneToOneField('ChatPoll', related_name='message', null=True, blank=True, on_delete=models.SET_NULL)
    reply_to = models.ForeignKey('self', related_name='replies', null=True, blank=True, on_delete=models.SET_NULL)
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    body = models.CharField(max_length=300, blank=True, null=True)
    file = models.FileField(upload_to='files/', blank=True, null=True)
    file_caption = models.CharField(max_length=300, blank=True, null=True)
    # One-time view (private chats): recipient can open once, then it expires after N seconds.
    one_time_view_seconds = models.PositiveSmallIntegerField(null=True, blank=True)
    one_time_viewed_at = models.DateTimeField(null=True, blank=True)
    one_time_viewed_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='one_time_views',
    )
    link_url = models.URLField(max_length=500, blank=True, default='')
    link_title = models.CharField(max_length=300, blank=True, default='')
    link_description = models.CharField(max_length=500, blank=True, default='')
    link_image = models.URLField(max_length=500, blank=True, default='')
    link_site_name = models.CharField(max_length=120, blank=True, default='')
    created = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    
    @property
    def filename(self):
        if self.file:
            return os.path.basename(self.file.name)
        else:
            return None
    
    def __str__(self):
        if self.body:
            return f'{self.author.username} : {self.body}'
        elif self.file:
            return f'{self.author.username} : {self.filename}'
        return f'{self.author.username} : (empty message #{self.id})'

    @property
    def one_time_expires_at(self):
        if not self.one_time_view_seconds or not self.one_time_viewed_at:
            return None
        try:
            return self.one_time_viewed_at + timedelta(seconds=int(self.one_time_view_seconds))
        except Exception:
            return None

    @property
    def one_time_is_expired(self):
        exp = self.one_time_expires_at
        if not exp:
            return False
        try:
            return timezone.now() >= exp
        except Exception:
            return True
    
    class Meta:
        ordering = ['-created']
        indexes = [
            models.Index(fields=['group', '-created'], name='gm_group_created_idx'),
            models.Index(fields=['author', '-created'], name='gm_author_created_idx'),
        ]
        
    @property    
    def is_image(self):
        try:
            image = Image.open(self.file)
            image.verify()
            return True
        except:
            return False

    @property
    def is_video(self):
        if not self.file:
            return False
        name = (getattr(self.file, 'name', '') or '').lower()
        # Keep this to formats that are commonly playable in browsers.
        # (e.g. .mkv/.avi often upload fine but usually don't play in HTML5 video.)
        return name.endswith(('.mp4', '.webm', '.ogg', '.ogv', '.mov', '.m4v'))

    @property
    def video_mime_type(self):
        if not self.file:
            return ''
        name = (getattr(self.file, 'name', '') or '')
        guessed, _ = mimetypes.guess_type(name)
        if guessed:
            return guessed
        lower = name.lower()
        if lower.endswith('.mov'):
            return 'video/quicktime'
        if lower.endswith('.m4v'):
            return 'video/x-m4v'
        return 'video/mp4'


class OneTimeMessageView(models.Model):
    """Per-viewer open record for one-time messages.

    A (message, user) pair can only be created once.
    """

    message = models.ForeignKey(GroupMessage, related_name='one_time_views_v2', on_delete=models.CASCADE)
    user = models.ForeignKey(User, related_name='one_time_message_views', on_delete=models.CASCADE)
    viewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['message', 'user'], name='uniq_one_time_view_message_user'),
        ]
        indexes = [
            models.Index(fields=['message', 'user'], name='otv_message_user_idx'),
            models.Index(fields=['user', '-viewed_at'], name='otv_user_viewed_idx'),
        ]

    def __str__(self):
        return f"OneTimeView(m={self.message_id}, u={self.user_id})"


class ModerationEvent(models.Model):
    ACTION_CHOICES = (
        ('allow', 'Allow'),
        ('flag', 'Flag'),
        ('block', 'Block'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='moderation_events')
    room = models.ForeignKey(ChatGroup, on_delete=models.SET_NULL, null=True, blank=True, related_name='moderation_events')
    message = models.ForeignKey(GroupMessage, on_delete=models.SET_NULL, null=True, blank=True, related_name='moderation_events')
    text = models.TextField(blank=True, default='')
    action = models.CharField(max_length=16, choices=ACTION_CHOICES)
    categories = models.JSONField(default=list, blank=True)
    severity = models.PositiveSmallIntegerField(default=0)
    confidence = models.FloatField(default=0.0)
    reason = models.CharField(max_length=255, blank=True, default='')
    source = models.CharField(max_length=32, blank=True, default='gemini')
    meta = models.JSONField(default=dict, blank=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created']

    def __str__(self):
        return f"{self.action} u={self.user_id} room={getattr(self.room, 'group_name', '')}"


class MessageReaction(models.Model):
    message = models.ForeignKey(GroupMessage, related_name='reactions', on_delete=models.CASCADE)
    user = models.ForeignKey(User, related_name='message_reactions', on_delete=models.CASCADE)
    emoji = models.CharField(max_length=8)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['message', 'user', 'emoji'], name='unique_message_reaction_v2'),
        ]

    def __str__(self):
        return f"{self.user.username} reacted {self.emoji} to #{self.message_id}"


class BlockedMessageEvent(models.Model):
    """Analytics log for blocked chat attempts (spam/flood/moderation).

    This intentionally duplicates small bits of context so staff dashboards can
    show trends even when anti-spam uses cache-only counters.
    """

    SCOPE_CHOICES = (
        ('muted', 'Muted'),
        ('room_flood', 'Room flood'),
        ('dup_msg', 'Duplicate message'),
        ('emoji_spam', 'Emoji spam'),
        ('typing_speed', 'Typing speed'),
        ('fast_long_msg', 'Fast long msg'),
        ('chat_send', 'Rate limit'),
        ('chat_upload', 'Upload rate limit'),
        ('ai_block', 'AI block'),
        ('other', 'Other'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blocked_message_events')
    room = models.ForeignKey(ChatGroup, on_delete=models.SET_NULL, null=True, blank=True, related_name='blocked_message_events')
    scope = models.CharField(max_length=32, choices=SCOPE_CHOICES, default='other', db_index=True)

    status_code = models.PositiveSmallIntegerField(default=0)
    retry_after = models.PositiveIntegerField(default=0)
    auto_muted_seconds = models.PositiveIntegerField(default=0)

    text = models.TextField(blank=True, default='')
    meta = models.JSONField(default=dict, blank=True)
    created = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created']
        indexes = [
            models.Index(fields=['room', '-created'], name='bme_room_created_idx'),
            models.Index(fields=['user', '-created'], name='bme_user_created_idx'),
            models.Index(fields=['scope', '-created'], name='bme_scope_created_idx'),
        ]

    def __str__(self):
        return f"Blocked({self.scope}) u={self.user_id} room={getattr(self.room, 'group_name', '')}"


class ChatChallenge(models.Model):
    STATUS_ACTIVE = 'active'
    STATUS_COMPLETED = 'completed'
    STATUS_CANCELLED = 'cancelled'

    KIND_EMOJI_ONLY = 'emoji_only'
    KIND_NO_VOWELS = 'no_vowels'
    KIND_FINISH_MEME = 'finish_meme'
    KIND_TRUTH_OR_DARE = 'truth_or_dare'
    KIND_TIME_ATTACK = 'time_attack'

    STATUS_CHOICES = (
        (STATUS_ACTIVE, 'Active'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_CANCELLED, 'Cancelled'),
    )

    KIND_CHOICES = (
        (KIND_EMOJI_ONLY, 'Emoji-only'),
        (KIND_NO_VOWELS, 'No vowels'),
        (KIND_FINISH_MEME, 'Finish the meme'),
        (KIND_TRUTH_OR_DARE, 'Truth or dare'),
        (KIND_TIME_ATTACK, 'Time attack'),
    )
    KIND_CHOICES_DICT = {k: v for (k, v) in KIND_CHOICES}

    group = models.ForeignKey(ChatGroup, related_name='challenges', on_delete=models.CASCADE)
    kind = models.CharField(max_length=32, choices=KIND_CHOICES, db_index=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_ACTIVE, db_index=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='created_chat_challenges')
    prompt = models.TextField(blank=True, default='')
    meta = models.JSONField(default=dict, blank=True)

    started_at = models.DateTimeField(null=True, blank=True, db_index=True)
    ends_at = models.DateTimeField(null=True, blank=True, db_index=True)
    ended_at = models.DateTimeField(null=True, blank=True, db_index=True)

    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created']
        indexes = [
            models.Index(fields=['group', 'status', '-created'], name='cc_group_status_idx'),
        ]

    def __str__(self):
        return f"Challenge({self.kind}) room={getattr(self.group, 'group_name', '')} status={self.status}"


class ChatPoll(models.Model):
    group = models.ForeignKey(ChatGroup, related_name='polls', on_delete=models.CASCADE)
    created_by = models.ForeignKey(User, related_name='created_chat_polls', on_delete=models.CASCADE)
    question = models.CharField(max_length=180)
    allow_multiple_answers = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created']
        indexes = [
            models.Index(fields=['group', '-created'], name='cp_group_created_idx'),
        ]

    def __str__(self):
        return f"Poll#{self.id} in {getattr(self.group, 'group_name', '')}"


class ChatPollOption(models.Model):
    poll = models.ForeignKey(ChatPoll, related_name='options', on_delete=models.CASCADE)
    text = models.CharField(max_length=120)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'id']
        indexes = [
            models.Index(fields=['poll', 'sort_order'], name='cpo_poll_order_idx'),
        ]

    def __str__(self):
        return f"PollOption#{self.id}({self.text[:30]})"


class ChatPollVote(models.Model):
    poll = models.ForeignKey(ChatPoll, related_name='votes', on_delete=models.CASCADE)
    option = models.ForeignKey(ChatPollOption, related_name='votes', on_delete=models.CASCADE)
    user = models.ForeignKey(User, related_name='chat_poll_votes', on_delete=models.CASCADE)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['poll', 'option', 'user'], name='uniq_chat_poll_option_user'),
        ]
        indexes = [
            models.Index(fields=['poll', 'user'], name='cpv_poll_user_idx'),
            models.Index(fields=['option'], name='cpv_option_idx'),
        ]

    def __str__(self):
        return f"PollVote(p={self.poll_id}, o={self.option_id}, u={self.user_id})"

