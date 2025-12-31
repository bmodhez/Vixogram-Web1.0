from django.db import models
from django.contrib.auth.models import User
import shortuuid
from PIL import Image
import os

class ChatGroup(models.Model):
    group_name = models.CharField(max_length=128, unique=True, blank=True)
    groupchat_name = models.CharField(max_length=128, null=True, blank=True)
    admin = models.ForeignKey(User, related_name='groupchats', blank=True, null=True, on_delete=models.SET_NULL)
    users_online = models.ManyToManyField(User, related_name='online_in_groups', blank=True)
    members = models.ManyToManyField(User, related_name='chat_groups', blank=True)
    is_private = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)
    # Private rooms that can be joined via a shareable code (not listed globally).
    is_code_room = models.BooleanField(default=False)
    room_code = models.CharField(max_length=16, unique=True, null=True, blank=True, db_index=True)
    code_room_name = models.CharField(max_length=128, null=True, blank=True)
    
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


class PrivateChatGroup(ChatGroup):
    class Meta:
        proxy = True
        verbose_name = 'Private chat'
        verbose_name_plural = 'Private chats'
    
    
class GroupMessage(models.Model):
    group = models.ForeignKey(ChatGroup, related_name='chat_messages', on_delete=models.CASCADE)
    reply_to = models.ForeignKey('self', related_name='replies', null=True, blank=True, on_delete=models.SET_NULL)
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    body = models.CharField(max_length=300, blank=True, null=True)
    file = models.FileField(upload_to='files/', blank=True, null=True)
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
    
    class Meta:
        ordering = ['-created']
        
    @property    
    def is_image(self):
        try:
            image = Image.open(self.file) 
            image.verify()
            return True 
        except:
            return False


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

