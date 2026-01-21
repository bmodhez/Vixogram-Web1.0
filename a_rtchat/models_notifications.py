from __future__ import annotations

from django.conf import settings
from django.db import models


class Notification(models.Model):
    TYPE_CHOICES = (
        ('mention', 'Mention'),
        ('reply', 'Reply'),
        ('ping', 'Ping'),
        ('follow', 'Follow'),
        ('support', 'Support'),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications_sent',
    )
    type = models.CharField(max_length=16, choices=TYPE_CHOICES)
    chatroom_name = models.CharField(max_length=128, blank=True, default='')
    message_id = models.PositiveBigIntegerField(null=True, blank=True)
    preview = models.CharField(max_length=180, blank=True, default='')
    url = models.CharField(max_length=255, blank=True, default='')
    is_read = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created']
        indexes = [
            models.Index(fields=['user', 'is_read', '-created'], name='notif_user_read_idx'),
            models.Index(fields=['user', '-created'], name='notif_user_created_idx'),
        ]

    def __str__(self):
        return f"Notification({self.type}) u={self.user_id}"
