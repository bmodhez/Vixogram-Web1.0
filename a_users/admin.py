from django.contrib import admin
from django.utils import timezone

try:
	from asgiref.sync import async_to_sync
	from channels.layers import get_channel_layer
except Exception:  # pragma: no cover
	async_to_sync = None
	get_channel_layer = None

from .models import Profile, SupportEnquiry, UserReport

try:
	from a_rtchat.models import Notification
except Exception:  # pragma: no cover
	Notification = None


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
	list_display = ('user', 'displayname', 'chat_blocked', 'is_private_account')
	search_fields = ('user__username', 'displayname')


@admin.register(UserReport)
class UserReportAdmin(admin.ModelAdmin):
	list_display = ('id', 'status', 'reason', 'reporter', 'reported_user', 'created_at')
	list_filter = ('status', 'reason')
	search_fields = ('reporter__username', 'reported_user__username')


@admin.register(SupportEnquiry)
class SupportEnquiryAdmin(admin.ModelAdmin):
	list_display = ('id', 'status', 'user', 'subject', 'created_at')
	list_filter = ('status',)
	search_fields = ('user__username', 'subject', 'message')
	readonly_fields = ('created_at',)
	fields = (
		'user',
		'status',
		'subject',
		'message',
		'page',
		'user_agent',
		'created_at',
		'admin_reply',
		'replied_at',
		'admin_note',
	)

	def save_model(self, request, obj, form, change):
		old_reply = ''
		try:
			if change and obj.pk:
				old_reply = str(SupportEnquiry.objects.get(pk=obj.pk).admin_reply or '')
		except Exception:
			old_reply = ''

		reply = str(getattr(obj, 'admin_reply', '') or '').strip()
		reply_changed = bool(reply and reply != str(old_reply or '').strip())

		if reply_changed:
			try:
				obj.replied_at = timezone.now()
			except Exception:
				pass
			try:
				obj.status = SupportEnquiry.STATUS_RESOLVED
			except Exception:
				pass

		super().save_model(request, obj, form, change)

		if not reply_changed:
			return

		# Persist notification (for dropdown)
		if Notification is not None:
			try:
				Notification.objects.create(
					user=obj.user,
					from_user=None,
					type='support',
					preview=f"From Vixogram Team: {reply}"[:180],
					url="/profile/support/",
				)
			except Exception:
				pass

		# Realtime toast/badge via per-user notify WS
		try:
			if async_to_sync is None or get_channel_layer is None:
				return
			channel_layer = get_channel_layer()
			if channel_layer is None:
				return
			async_to_sync(channel_layer.group_send)(
				f"notify_user_{obj.user_id}",
				{
					'type': 'support_notify_handler',
					'preview': f"From Vixogram Team: {reply}"[:180],
					'url': "/profile/support/",
				},
			)
		except Exception:
			pass