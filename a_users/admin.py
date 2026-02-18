from django.contrib import admin
from django.utils import timezone

try:
	from asgiref.sync import async_to_sync
	from channels.layers import get_channel_layer
except Exception:  # pragma: no cover
	async_to_sync = None
	get_channel_layer = None

from .models import BetaFeature, ChatBanHistory, Profile, Story, SupportEnquiry, UserDevice, UserReport
from .location_ip import geoip_city_country

try:
	from a_rtchat.models import Notification
except Exception:  # pragma: no cover
	Notification = None


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
	list_display = (
		'user',
		'displayname',
		'is_founder_club',
		'chat_blocked',
		'chat_ban_active',
		'last_known_ip',
		'location_exact',
		'precise_coordinates',
		'last_location_at',
	)
	list_filter = ('is_founder_club', 'chat_blocked', 'is_private_account', 'is_stealth', 'is_dnd')
	search_fields = ('user__username', 'displayname', 'last_location_city', 'last_location_country')
	readonly_fields = ('chat_ban_active', 'last_known_ip', 'location_exact', 'precise_coordinates')
	fields = (
		'user',
		'displayname',
		'info',
		('image', 'cover_image'),
		('chat_blocked', 'chat_banned_until', 'chat_ban_active'),
		('is_private_account', 'is_stealth', 'is_bot', 'is_dnd'),
		('is_founder_club', 'founder_club_granted_at', 'founder_club_revoked_at'),
		('founder_club_reapply_available_at', 'founder_club_last_checked'),
		('last_known_ip', 'location_exact'),
		('last_location_lat', 'last_location_lng', 'precise_coordinates'),
		'last_location_at',
		'referral_points',
	)

	def get_readonly_fields(self, request, obj=None):
		base = list(super().get_readonly_fields(request, obj))
		if not getattr(request.user, 'is_superuser', False):
			base.extend([
				'is_founder_club',
				'founder_club_granted_at',
				'founder_club_revoked_at',
				'founder_club_reapply_available_at',
				'founder_club_last_checked',
			])
		return tuple(base)

	def save_model(self, request, obj, form, change):
		founder_changed = bool('is_founder_club' in getattr(form, 'changed_data', []))
		if founder_changed:
			now = timezone.now()
			today = timezone.localdate()
			if bool(getattr(obj, 'is_founder_club', False)):
				if not getattr(obj, 'founder_club_granted_at', None):
					obj.founder_club_granted_at = now
				obj.founder_club_revoked_at = None
				obj.founder_club_reapply_available_at = None
				obj.founder_club_last_checked = today
			else:
				obj.founder_club_revoked_at = now
				obj.founder_club_last_checked = today

		super().save_model(request, obj, form, change)

	@admin.display(boolean=True, description='Ban active')
	def chat_ban_active(self, obj):
		until = getattr(obj, 'chat_banned_until', None)
		try:
			return bool(until and until > timezone.now())
		except Exception:
			return False

	@admin.display(description='Last IP')
	def last_known_ip(self, obj):
		try:
			return (
				UserDevice.objects
				.filter(user_id=getattr(getattr(obj, 'user', None), 'id', None))
				.order_by('-last_seen')
				.values_list('last_ip', flat=True)
				.first()
			) or '-'
		except Exception:
			return '-'

	@admin.display(description='Exact location')
	def location_exact(self, obj):
		city = (getattr(obj, 'last_location_city', '') or '').strip()
		country = (getattr(obj, 'last_location_country', '') or '').strip()
		if city and country:
			return f'{city}, {country}'
		if city:
			return city
		if country:
			return country
		return '-'

	@admin.display(description='Precise coords')
	def precise_coordinates(self, obj):
		lat = getattr(obj, 'last_location_lat', None)
		lng = getattr(obj, 'last_location_lng', None)
		if lat is None or lng is None:
			return '-'
		return f'{lat}, {lng}'


@admin.register(UserDevice)
class UserDeviceAdmin(admin.ModelAdmin):
	list_display = ('user', 'device_label', 'last_ip', 'ip_city', 'first_seen', 'last_seen')
	list_filter = ('first_seen', 'last_seen')
	search_fields = ('user__username', 'device_label', 'last_ip', 'user_agent')
	readonly_fields = ('user', 'ua_hash', 'user_agent', 'device_label', 'first_seen', 'last_seen', 'last_ip')

	@admin.display(description='City / Location')
	def ip_city(self, obj):
		ip = (getattr(obj, 'last_ip', '') or '').strip()
		city = ''
		country = ''
		if ip:
			try:
				city, country = geoip_city_country(ip)
			except Exception:
				city = ''
				country = ''

		if not (city or country):
			try:
				profile = getattr(getattr(obj, 'user', None), 'profile', None)
				city = (getattr(profile, 'last_location_city', '') or '').strip()
				country = (getattr(profile, 'last_location_country', '') or '').strip()
			except Exception:
				city = ''
				country = ''

		if city and country:
			return f'{city}, {country}'
		if city:
			return city
		if country:
			return country
		return '-'

	def has_add_permission(self, request):
		return False


@admin.register(ChatBanHistory)
class ChatBanHistoryAdmin(admin.ModelAdmin):
	list_display = ('user', 'action', 'duration_minutes', 'banned_until', 'banned_by', 'admin_ip', 'created_at')
	list_filter = ('action', 'created_at')
	search_fields = ('user__username', 'banned_by__username', 'admin_ip')
	readonly_fields = ('user', 'action', 'duration_minutes', 'banned_until', 'banned_by', 'admin_ip', 'created_at')
	date_hierarchy = 'created_at'

	def has_add_permission(self, request):
		return False

	def has_change_permission(self, request, obj=None):
		return False


@admin.register(BetaFeature)
class BetaFeatureAdmin(admin.ModelAdmin):
	list_display = ('slug', 'title', 'is_enabled', 'requires_founder_club', 'updated_at')
	list_filter = ('is_enabled', 'requires_founder_club')
	search_fields = ('slug', 'title')
	list_editable = ('is_enabled', 'requires_founder_club')


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


@admin.register(Story)
class StoryAdmin(admin.ModelAdmin):
	list_display = ('id', 'user', 'created_at', 'expires_at')
	list_filter = ('created_at',)
	search_fields = ('user__username',)