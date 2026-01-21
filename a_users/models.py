from django.db import models
from django.contrib.auth.models import User
from django.db.models import Q
from django.conf import settings

import base64

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    image = models.ImageField(upload_to='avatars/', null=True, blank=True)
    displayname = models.CharField(max_length=20, null=True, blank=True)
    info = models.TextField(null=True, blank=True) 
    chat_blocked = models.BooleanField(default=False)
    is_private_account = models.BooleanField(default=False)
    is_stealth = models.BooleanField(default=False)
    is_bot = models.BooleanField(default=False)
    is_dnd = models.BooleanField(default=False)
    referral_points = models.PositiveIntegerField(default=0)
    
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
            models.UniqueConstraint(
                fields=['reporter', 'reported_user'],
                condition=Q(status='open'),
                name='userreport_unique_open_report',
            ),
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