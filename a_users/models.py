from django.db import models, transaction
from django.contrib.auth.models import User
from django.db.models import Q
from django.conf import settings
from django.utils import timezone
from django.core.validators import MaxLengthValidator

from datetime import timedelta
import os

import base64
import hashlib
import time

class Profile(models.Model):
    NAME_GLOW_NONE = 'none'
    NAME_GLOW_AURORA = 'aurora'
    NAME_GLOW_SUNSET = 'sunset'
    NAME_GLOW_NEON = 'neon'
    NAME_GLOW_ROSE = 'rose'
    NAME_GLOW_ELECTRIC = 'electric'
    NAME_GLOW_TOXIC = 'toxic'
    NAME_GLOW_ROYAL = 'royal'
    NAME_GLOW_ICE = 'ice'
    NAME_GLOW_COSMIC = 'cosmic'

    NAME_GLOW_CHOICES = (
        (NAME_GLOW_NONE, 'No glow'),
        (NAME_GLOW_AURORA, 'Aurora'),
        (NAME_GLOW_SUNSET, 'Sunset'),
        (NAME_GLOW_NEON, 'Neon'),
        (NAME_GLOW_ROSE, 'Rose'),
        (NAME_GLOW_ELECTRIC, 'Electric'),
        (NAME_GLOW_TOXIC, 'Toxic'),
        (NAME_GLOW_ROYAL, 'Royal'),
        (NAME_GLOW_ICE, 'Ice'),
        (NAME_GLOW_COSMIC, 'Cosmic'),
    )

    CHAT_THEME_DEFAULT = 'default'
    CHAT_THEME_1 = 'theme1'
    CHAT_THEME_2 = 'theme2'
    CHAT_THEME_3 = 'theme3'
    CHAT_THEME_CHOICES = (
        (CHAT_THEME_DEFAULT, 'Default'),
        (CHAT_THEME_1, 'Cyber Grid'),
        (CHAT_THEME_2, 'Aurora Night'),
        (CHAT_THEME_3, 'Neon Wave'),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    image = models.ImageField(upload_to='avatars/', null=True, blank=True)
    cover_image = models.ImageField(upload_to='profile_covers/', null=True, blank=True)
    displayname = models.CharField(max_length=20, null=True, blank=True)
    info = models.TextField(
        null=True,
        blank=True,
        max_length=200,
        validators=[MaxLengthValidator(200)],
    )
    # Avatar moderation (NudeNet async review)
    AVATAR_REVIEW_NONE = 'none'
    AVATAR_REVIEW_PENDING = 'pending'
    AVATAR_REVIEW_APPROVED = 'approved'
    AVATAR_REVIEW_REJECTED = 'rejected'
    AVATAR_REVIEW_CHOICES = [
        ('none', 'None'),
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    avatar_review_status = models.CharField(
        max_length=10,
        choices=AVATAR_REVIEW_CHOICES,
        default='none',
        db_index=True,
    )
    avatar_pending_local = models.CharField(max_length=500, blank=True, default='')
    COVER_REVIEW_NONE = 'none'
    COVER_REVIEW_PENDING = 'pending'
    COVER_REVIEW_APPROVED = 'approved'
    COVER_REVIEW_REJECTED = 'rejected'
    COVER_REVIEW_CHOICES = [
        ('none', 'None'),
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    cover_review_status = models.CharField(
        max_length=10,
        choices=COVER_REVIEW_CHOICES,
        default='none',
        db_index=True,
    )
    cover_pending_local = models.CharField(max_length=500, blank=True, default='')

    chat_blocked = models.BooleanField(default=False)
    chat_banned_until = models.DateTimeField(null=True, blank=True)
    is_private_account = models.BooleanField(default=False)
    is_stealth = models.BooleanField(default=False)
    is_bot = models.BooleanField(default=False)
    is_dnd = models.BooleanField(default=False)
    name_glow_color = models.CharField(max_length=16, choices=NAME_GLOW_CHOICES, default=NAME_GLOW_NONE)
    chat_theme = models.CharField(max_length=12, choices=CHAT_THEME_CHOICES, default=CHAT_THEME_DEFAULT)
    referral_points = models.PositiveIntegerField(default=0)
    private_rooms_created_total = models.PositiveIntegerField(default=0)

    def save(self, *args, **kwargs):
        old_image_name = None
        old_cover_name = None

        # Keep a stable Cloudinary public_id for profile background updates.
        # This makes each new cover upload overwrite the previous one.
        try:
            cover_field = getattr(self, 'cover_image', None)
            is_new_cover_upload = bool(cover_field and getattr(cover_field, 'file', None) and not getattr(cover_field, '_committed', True))
            if is_new_cover_upload:
                storage_obj = getattr(cover_field, 'storage', None)
                storage_module = str(getattr(getattr(storage_obj, '__class__', object), '__module__', '')).lower()
                storage_name = str(getattr(getattr(storage_obj, '__class__', object), '__name__', '')).lower()
                if 'cloudinary' in storage_module or 'cloudinary' in storage_name:
                    ext = os.path.splitext(str(getattr(cover_field, 'name', '') or ''))[1].lower()
                    if ext not in {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.tif', '.tiff'}:
                        ext = '.jpg'
                    cover_version = int(time.time() * 1000)
                    cover_field.name = f'profile_covers/user_{self.user_id}_cover_{cover_version}{ext}'
        except Exception:
            pass

        if self.pk:
            try:
                old = Profile.objects.only('image', 'cover_image').get(pk=self.pk)
                old_image_name = getattr(getattr(old, 'image', None), 'name', None)
                old_cover_name = getattr(getattr(old, 'cover_image', None), 'name', None)
            except Exception:
                old_image_name = None
                old_cover_name = None

        result = super().save(*args, **kwargs)

        new_image_name = getattr(getattr(self, 'image', None), 'name', None)
        new_cover_name = getattr(getattr(self, 'cover_image', None), 'name', None)

        def _delete_from_storage(name: str | None):
            if not name:
                return
            try:
                # Use the field's storage (Cloudinary when enabled).
                # Delete by name/public_id.
                self.image.storage.delete(name)
            except Exception:
                pass

        if old_image_name and old_image_name != new_image_name:
            transaction.on_commit(lambda n=old_image_name: _delete_from_storage(n))

        if old_cover_name and old_cover_name != new_cover_name:
            transaction.on_commit(lambda n=old_cover_name: _delete_from_storage(n))

        return result

    # Last known location (best-effort, from optional user permission)
    last_location_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    last_location_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    last_location_at = models.DateTimeField(null=True, blank=True)
    last_location_city = models.CharField(max_length=80, null=True, blank=True)
    last_location_country = models.CharField(max_length=80, null=True, blank=True)
    preferred_location_country = models.CharField(max_length=80, null=True, blank=True)
    preferred_location_state = models.CharField(max_length=80, null=True, blank=True)
    preferred_location_city = models.CharField(max_length=80, null=True, blank=True)
    preferred_location_last_changed_at = models.DateTimeField(null=True, blank=True)

    # Founder Club (invite rewards)
    is_founder_club = models.BooleanField(default=False)
    founder_club_granted_at = models.DateTimeField(null=True, blank=True)
    founder_club_revoked_at = models.DateTimeField(null=True, blank=True)
    founder_club_reapply_available_at = models.DateTimeField(null=True, blank=True)
    founder_club_last_checked = models.DateField(null=True, blank=True)

    # Username change limits
    username_change_count = models.PositiveIntegerField(default=0)
    username_last_changed_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return str(self.user)

    @property
    def name(self):
        if self.displayname:
            return self.displayname
        return self.user.username 

    # Iska gap (indent) ab sahi hai, ye 'name' ke barabar hona chahiye
    @property
    def avatar(self):
        # Special-case: Natasha bot DP from static.
        try:
            if getattr(getattr(self, 'user', None), 'username', '') in {'natasha', 'natasha-bot'}:
                static_url = (getattr(settings, 'STATIC_URL', '/static/') or '/static/').strip()
                if not static_url.endswith('/'):
                    static_url += '/'
                return f"{static_url}natasha.jpeg"
        except Exception:
            pass

        if self.image:
            try:
                return self.image.url
            except Exception:
                # If storage isn't configured or the file is missing, fall back to default.
                pass
        return DEFAULT_AVATAR_DATA_URI

    @property
    def cover_url(self) -> str | None:
        if not self.cover_image:
            return None
        try:
            base_url = str(self.cover_image.url)
            sep = '&' if '?' in base_url else '?'
            return f"{base_url}{sep}v={time.time_ns()}"
        except Exception:
            return None


class ProfileAvatarSubmission(Profile):
    """Proxy model used to expose avatar moderation queue in Django admin."""

    class Meta:
        proxy = True
        verbose_name = 'Profile photo submission'
        verbose_name_plural = 'Profile photo submissions'


class ProfileBannerSubmission(Profile):
    """Proxy model used to expose banner/cover moderation queue in Django admin."""

    class Meta:
        proxy = True
        verbose_name = 'Banner photo submission'
        verbose_name_plural = 'Banner photo submissions'


class VixoPoints(Profile):
    """Proxy model to manage/show user referral points in Django admin."""

    class Meta:
        proxy = True
        verbose_name = 'Vixo Points'
        verbose_name_plural = 'Vixo Points'


"""Premium/Pro subscription models (disabled for now).

We are intentionally keeping the planned subscription + payment models in the codebase
as a reference, but the feature is not live yet.

When you want to enable Premium again:
- Restore the classes below
- Re-add URLs/views and UI toggles
"""

# if False:
#     class ProSubscription(models.Model):
#         ...
#
#     class ProPayment(models.Model):
#         ...


class Story(models.Model):
    """Image-only stories.

    Notes:
    - Only images are supported (no videos).
    - Viewer autoplay duration is fixed at 10 seconds per story.
    - Stories expire after 24 hours by default.
    """

    DURATION_SECONDS = 10
    TTL_HOURS = 24

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='stories')
    image = models.ImageField(upload_to='stories/', null=False, blank=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['user', '-created_at'], name='story_user_created_idx'),
            models.Index(fields=['user', 'expires_at'], name='story_user_expires_idx'),
        ]

    def save(self, *args, **kwargs):
        if not self.expires_at:
            try:
                self.expires_at = timezone.now() + timedelta(hours=self.TTL_HOURS)
            except Exception:
                self.expires_at = None
        return super().save(*args, **kwargs)

    def delete(self, using=None, keep_parents=False):
        # Ensure the underlying file is removed from storage when the DB row is deleted.
        try:
            if getattr(self, 'image', None):
                self.image.delete(save=False)
        except Exception:
            pass
        return super().delete(using=using, keep_parents=keep_parents)

    def __str__(self):
        return f"Story({self.id}) u={self.user_id}"


class StorySubmission(models.Model):
    """Manual moderation queue for story uploads before publish."""

    REVIEW_NONE = 'none'
    REVIEW_PENDING = 'pending'
    REVIEW_APPROVED = 'approved'
    REVIEW_REJECTED = 'rejected'
    REVIEW_CHOICES = [
        ('none', 'None'),
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='story_submissions')
    pending_local = models.CharField(max_length=500, blank=True, default='')
    review_status = models.CharField(max_length=10, choices=REVIEW_CHOICES, default='pending', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_story_submissions',
    )
    approved_story = models.ForeignKey(
        Story,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='submission_source',
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['review_status', '-created_at'], name='storysub_status_created_idx'),
            models.Index(fields=['user', '-created_at'], name='storysub_user_created_idx'),
        ]

    def __str__(self):
        return f"StorySubmission({self.id}) u={self.user_id} {self.review_status}"


class StoryView(models.Model):
    """Tracks which users have viewed a specific story.

    This enables the story owner to see the list of viewers.
    """

    story = models.ForeignKey(Story, on_delete=models.CASCADE, related_name='views')
    viewer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='story_views')
    first_seen = models.DateTimeField(auto_now_add=True, db_index=True)
    last_seen = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['story', 'viewer'], name='uniq_story_view'),
        ]
        indexes = [
            models.Index(fields=['story', '-last_seen'], name='storyview_story_lastseen_idx'),
        ]

    def __str__(self):
        return f"StoryView(story={self.story_id}, viewer={self.viewer_id})"


class StoryLike(models.Model):
    """Tracks which users liked a specific story."""

    story = models.ForeignKey(Story, on_delete=models.CASCADE, related_name='likes')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='story_likes')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['story', 'user'], name='uniq_story_like'),
        ]
        indexes = [
            models.Index(fields=['story', '-created_at'], name='storylike_story_created_idx'),
            models.Index(fields=['user', '-created_at'], name='storylike_user_created_idx'),
        ]

    def __str__(self):
        return f"StoryLike(story={self.story_id}, user={self.user_id})"


_DEFAULT_AVATAR_SVG = """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 128 128' role='img' aria-label='User avatar'>
<circle cx='64' cy='64' r='60' fill='#4B5563'/>
<circle cx='64' cy='52' r='20' fill='#F3F4F6'/>
<path d='M24 112c6-24 26-36 40-36s34 12 40 36' fill='#F3F4F6'/>
</svg>"""

DEFAULT_AVATAR_DATA_URI = (
    "data:image/svg+xml;base64," + base64.b64encode(_DEFAULT_AVATAR_SVG.encode("utf-8")).decode("ascii")
)


class FCMToken(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='fcm_tokens')
    token = models.CharField(max_length=256, unique=True)
    user_agent = models.CharField(max_length=255, blank=True, default='')
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    last_seen = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"FCMToken(user={self.user_id})"


class UserDevice(models.Model):
    """Tracks devices used by a user (best-effort) based on User-Agent.

    Notes:
    - This is not a security boundary; it's for staff visibility.
    - Multiple physical devices may share the same User-Agent and will be grouped.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='devices')
    ua_hash = models.CharField(max_length=64, db_index=True)
    user_agent = models.CharField(max_length=300, blank=True, default='')
    device_label = models.CharField(max_length=120, blank=True, default='')
    first_seen = models.DateTimeField(auto_now_add=True, db_index=True)
    last_seen = models.DateTimeField(auto_now=True, db_index=True)
    last_ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'ua_hash'], name='uniq_user_device_uahash'),
        ]
        indexes = [
            models.Index(fields=['user', '-last_seen'], name='ud_user_last_seen_idx'),
        ]

    @staticmethod
    def hash_user_agent(user_agent: str) -> str:
        raw = (user_agent or '').strip()[:300]
        return hashlib.sha256(raw.encode('utf-8', errors='ignore')).hexdigest()

    def __str__(self):
        return f"UserDevice(user={self.user_id}, last_seen={self.last_seen})"


class ChatBanHistory(models.Model):
    ACTION_BAN = 'ban'
    ACTION_UNBAN = 'unban'
    ACTION_CHOICES = (
        (ACTION_BAN, 'Ban'),
        (ACTION_UNBAN, 'Unban'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chat_ban_history')
    action = models.CharField(max_length=8, choices=ACTION_CHOICES, db_index=True)
    duration_minutes = models.PositiveIntegerField(default=0)
    banned_until = models.DateTimeField(null=True, blank=True)
    banned_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='issued_chat_ban_history',
    )
    note = models.TextField(blank=True, default='')
    admin_ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at'], name='cbh_user_created_idx'),
            models.Index(fields=['action', '-created_at'], name='cbh_action_created_idx'),
        ]

    def __str__(self):
        return f"ChatBanHistory(user={self.user_id}, action={self.action}, at={self.created_at})"


class Follow(models.Model):
    follower = models.ForeignKey(User, on_delete=models.CASCADE, related_name='following_rel')
    following = models.ForeignKey(User, on_delete=models.CASCADE, related_name='followers_rel')
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['follower', 'following'], name='unique_follow'),
        ]
        indexes = [
            models.Index(fields=['following', '-created'], name='follow_following_idx'),
            models.Index(fields=['follower', '-created'], name='follow_follower_idx'),
        ]

    def __str__(self):
        return f"{self.follower_id} -> {self.following_id}"


class FollowRequest(models.Model):
    from_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='follow_requests_sent')
    to_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='follow_requests_received')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['from_user', 'to_user'], name='unique_follow_request'),
        ]
        indexes = [
            models.Index(fields=['to_user', '-created_at'], name='followreq_to_created_idx'),
            models.Index(fields=['from_user', '-created_at'], name='followreq_from_created_idx'),
        ]

    def __str__(self):
        return f"FollowRequest({self.from_user_id} -> {self.to_user_id})"


class UserReport(models.Model):
    STATUS_OPEN = 'open'
    STATUS_RESOLVED = 'resolved'
    STATUS_DISMISSED = 'dismissed'
    STATUS_CHOICES = [
        (STATUS_OPEN, 'Open'),
        (STATUS_RESOLVED, 'Resolved'),
        (STATUS_DISMISSED, 'Dismissed'),
    ]

    REASON_SPAM = 'spam'
    REASON_ABUSE = 'abuse'
    REASON_IMPERSONATION = 'impersonation'
    REASON_NUDITY = 'nudity'
    REASON_OTHER = 'other'
    REASON_CHOICES = [
        (REASON_SPAM, 'Spam'),
        (REASON_ABUSE, 'Harassment / abuse'),
        (REASON_IMPERSONATION, 'Impersonation'),
        (REASON_NUDITY, 'Inappropriate content'),
        (REASON_OTHER, 'Other'),
    ]

    reporter = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reports_made')
    reported_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reports_received')
    reason = models.CharField(max_length=32, choices=REASON_CHOICES)
    details = models.TextField(blank=True, default='')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_OPEN)
    created_at = models.DateTimeField(auto_now_add=True)

    handled_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reports_handled',
    )
    handled_at = models.DateTimeField(null=True, blank=True)
    resolution_note = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at'], name='ur_status_created_idx'),
            models.Index(fields=['reported_user', '-created_at'], name='ur_reported_created_idx'),
        ]
        constraints = [
            models.CheckConstraint(check=~Q(reporter=models.F('reported_user')), name='userreport_no_self'),
        ]

    def __str__(self):
        return f"Report({self.id}) {self.reporter_id} -> {self.reported_user_id} ({self.status})"


class SupportEnquiry(models.Model):
    STATUS_OPEN = 'open'
    STATUS_RESOLVED = 'resolved'
    STATUS_CHOICES = [
        (STATUS_OPEN, 'Open'),
        (STATUS_RESOLVED, 'Resolved'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='support_enquiries')
    subject = models.CharField(max_length=120, blank=True, default='')
    message = models.TextField(max_length=2000)
    page = models.CharField(max_length=300, blank=True, default='')
    user_agent = models.CharField(max_length=300, blank=True, default='')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_OPEN)
    admin_note = models.TextField(blank=True, default='')
    admin_reply = models.TextField(blank=True, default='')
    replied_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at'], name='se_status_created_idx'),
            models.Index(fields=['user', '-created_at'], name='se_user_created_idx'),
        ]

    def __str__(self):
        return f"SupportEnquiry({self.id}) u={self.user_id} {self.status}"


class Referral(models.Model):
    """Tracks invite/referral attribution and rewards.

    A referral is created when a new user signs up with a valid invite token.
    Points are only awarded after the referred user's email is verified.
    """

    referrer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='referrals_made')
    referred = models.OneToOneField(User, on_delete=models.CASCADE, related_name='referral_received')
    points_awarded = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    awarded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['referrer', '-created_at'], name='ref_referrer_created_idx'),
            models.Index(fields=['awarded_at', '-created_at'], name='ref_awarded_created_idx'),
        ]

    def __str__(self):
        return f"Referral({self.id}) referrer={self.referrer_id} referred={self.referred_id} awarded={bool(self.awarded_at)}"


class DailyUserActivity(models.Model):
    """Per-user daily activity time (seconds).

    Used for enforcing Founder Club minimum daily activity.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='daily_activity')
    date = models.DateField(db_index=True)
    active_seconds = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'date'], name='uniq_daily_user_activity_user_date'),
        ]
        indexes = [
            models.Index(fields=['user', '-date'], name='dua_user_date_idx'),
        ]

    def __str__(self):
        return f"DailyUserActivity(u={self.user_id} date={self.date} sec={self.active_seconds})"


class BetaFeature(models.Model):
    """Feature flags for beta rollout.

    Admin can "push to beta" by enabling a feature.
    The UI can show the feature to everyone, but usage can be restricted
    (typically to Founder Club).
    """

    slug = models.SlugField(unique=True)
    title = models.CharField(max_length=120)
    description = models.TextField(blank=True, default='')
    is_enabled = models.BooleanField(default=False, db_index=True)
    requires_founder_club = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['slug']

    def __str__(self):
        return f"BetaFeature({self.slug}) enabled={self.is_enabled} founder_only={self.requires_founder_club}"

    def is_accessible_by(self, user: User | None) -> bool:
        if not self.is_enabled:
            return False
        if not self.requires_founder_club:
            return True
        if not user or not getattr(user, 'is_authenticated', False):
            return False
        try:
            if bool(getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False)):
                return True
        except Exception:
            pass
        try:
            return bool(getattr(getattr(user, 'profile', None), 'is_founder_club', False))
        except Exception:
            return False