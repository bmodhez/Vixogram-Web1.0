import csv
import os
from datetime import timedelta

from django.conf import settings
from django.contrib import admin, messages
from django.core.files.base import File
from django.db import models
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils import timezone

try:
	from asgiref.sync import async_to_sync
	from channels.layers import get_channel_layer
except Exception:  # pragma: no cover
	async_to_sync = None
	get_channel_layer = None

from .models import BetaFeature, ChatBanHistory, Profile, ProfileAvatarSubmission, ProfileBannerSubmission, Story, StorySubmission, SupportEnquiry, UserDevice, UserReport, VixoPoints
from .location_ip import geoip_city_country

try:
	from a_rtchat.models import Notification
except Exception:  # pragma: no cover
	Notification = None


def _notify_profile_avatar_review_result(*, profile, approved: bool) -> None:
	"""Persist + emit realtime notification for avatar moderation result."""
	try:
		user = getattr(profile, 'user', None)
		user_id = int(getattr(user, 'id', 0) or 0)
		if user_id <= 0:
			return
	except Exception:
		return

	if approved:
		preview = 'Your profile pic has been approved by the Vixo Team.'
	else:
		preview = 'Your profile pic was rejected by the Vixo Team. Please upload a different photo.'

	url = '/profile/edit/'

	if Notification is not None:
		try:
			Notification.objects.create(
				user_id=user_id,
				from_user=None,
				type='support',
				preview=preview[:180],
				url=url,
			)
		except Exception:
			pass

	try:
		if async_to_sync is None or get_channel_layer is None:
			return
		channel_layer = get_channel_layer()
		if channel_layer is None:
			return
		async_to_sync(channel_layer.group_send)(
			f"notify_user_{user_id}",
			{
				'type': 'support_notify_handler',
				'preview': preview[:180],
				'url': url,
			},
		)
	except Exception:
		pass


def _notify_profile_banner_review_result(*, profile, approved: bool) -> None:
	"""Persist + emit realtime notification for banner moderation result."""
	try:
		user = getattr(profile, 'user', None)
		user_id = int(getattr(user, 'id', 0) or 0)
		if user_id <= 0:
			return
	except Exception:
		return

	if approved:
		preview = 'Your banner photo has been approved by the Vixo Team.'
	else:
		preview = 'Your banner photo was rejected by the Vixo Team. Please upload a different photo.'

	url = '/profile/edit/'

	if Notification is not None:
		try:
			Notification.objects.create(
				user_id=user_id,
				from_user=None,
				type='support',
				preview=preview[:180],
				url=url,
			)
		except Exception:
			pass

	try:
		if async_to_sync is None or get_channel_layer is None:
			return
		channel_layer = get_channel_layer()
		if channel_layer is None:
			return
		async_to_sync(channel_layer.group_send)(
			f"notify_user_{user_id}",
			{
				'type': 'support_notify_handler',
				'preview': preview[:180],
				'url': url,
			},
		)
	except Exception:
		pass


def _notify_story_review_result(*, user_id: int, approved: bool) -> None:
	"""Persist + emit realtime notification for story moderation result."""
	try:
		uid = int(user_id or 0)
		if uid <= 0:
			return
	except Exception:
		return

	if approved:
		preview = 'Your story has been approved by the Vixo Team.'
	else:
		preview = 'Your story was rejected by the Vixo Team. Please upload a different image.'

	url = '/profile/'

	if Notification is not None:
		try:
			Notification.objects.create(
				user_id=uid,
				from_user=None,
				type='support',
				preview=preview[:180],
				url=url,
			)
		except Exception:
			pass

	try:
		if async_to_sync is None or get_channel_layer is None:
			return
		channel_layer = get_channel_layer()
		if channel_layer is None:
			return
		async_to_sync(channel_layer.group_send)(
			f"notify_user_{uid}",
			{
				'type': 'support_notify_handler',
				'preview': preview[:180],
				'url': url,
			},
		)
	except Exception:
		pass


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


@admin.register(VixoPoints)
class VixoPointsAdmin(admin.ModelAdmin):
	list_display = ('user', 'displayname', 'referral_points')
	search_fields = ('user__username', 'displayname')
	ordering = ('-referral_points', 'user__username')
	readonly_fields = ('user', 'displayname', 'referral_points')

	def has_add_permission(self, request):
		return False


@admin.register(ProfileAvatarSubmission)
class ProfileAvatarSubmissionAdmin(admin.ModelAdmin):
	list_display = ('user', 'queue_status', 'submitted_at', 'pending_preview', 'row_actions')
	list_filter = ('avatar_review_status',)
	search_fields = ('user__username', 'displayname', 'avatar_pending_local')
	actions = ('approve_selected_submissions', 'reject_selected_submissions')
	ordering = ('-id',)

	def get_urls(self):
		urls = super().get_urls()
		custom_urls = [
			path(
				'<int:object_id>/approve/',
				self.admin_site.admin_view(self.approve_single_submission_view),
				name=f'{self.model._meta.app_label}_{self.model._meta.model_name}_approve',
			),
			path(
				'<int:object_id>/reject/',
				self.admin_site.admin_view(self.reject_single_submission_view),
				name=f'{self.model._meta.app_label}_{self.model._meta.model_name}_reject',
			),
		]
		return custom_urls + urls

	def has_add_permission(self, request):
		return False

	def get_queryset(self, request):
		qs = super().get_queryset(request).select_related('user')
		return qs.filter(avatar_review_status='pending').exclude(avatar_pending_local='')

	@admin.display(description='Queue status')
	def queue_status(self, obj):
		return 'Pending review'

	@admin.display(description='Submitted at')
	def submitted_at(self, obj):
		path = str(getattr(obj, 'avatar_pending_local', '') or '').strip()
		if not path:
			return '-'
		try:
			ts = os.path.getmtime(path)
			return timezone.datetime.fromtimestamp(ts, tz=timezone.get_current_timezone())
		except Exception:
			return '-'

	@admin.display(description='Pending image')
	def pending_preview(self, obj):
		path = str(getattr(obj, 'avatar_pending_local', '') or '').strip()
		if not path:
			return '-'
		name = os.path.basename(path)
		if not name:
			return '-'
		base = str(getattr(settings, 'MEDIA_URL', '/media/') or '/media/')
		if not base.endswith('/'):
			base += '/'
		img_url = f"{base}pending_avatars/{name}"
		return format_html(
			'<a href="{}" target="_blank" rel="noopener">'
			'<img src="{}" alt="pending avatar" style="width:48px;height:48px;object-fit:cover;border-radius:9999px;border:1px solid #ddd;" />'
			'</a>',
			img_url,
			img_url,
		)

	@admin.display(description='Actions')
	def row_actions(self, obj):
		approve_url = reverse(
			f'admin:{self.model._meta.app_label}_{self.model._meta.model_name}_approve',
			args=[obj.pk],
		)
		reject_url = reverse(
			f'admin:{self.model._meta.app_label}_{self.model._meta.model_name}_reject',
			args=[obj.pk],
		)
		return format_html(
			'<div style="display:flex;gap:8px;align-items:center;">'
			'<a class="button" href="{}" style="background:#16a34a;border-color:#15803d;color:#fff;">Approve</a>'
			'<a class="button" href="{}" style="background:#dc2626;border-color:#b91c1c;color:#fff;" '
			'onclick="return confirm(\'Reject this profile pic submission?\');">Reject</a>'
			'</div>',
			approve_url,
			reject_url,
		)

	def _apply_approved_avatar(self, profile) -> bool:
		path = str(getattr(profile, 'avatar_pending_local', '') or '').strip()
		if not path or not os.path.exists(path):
			Profile.objects.filter(pk=profile.pk).update(
				avatar_review_status='rejected',
				avatar_pending_local='',
			)
			return False

		ext = os.path.splitext(path)[1].lower() or '.jpg'
		file_name = f"avatar_reviewed_{profile.user_id}_{int(timezone.now().timestamp())}{ext}"
		try:
			with open(path, 'rb') as fh:
				profile.image.save(file_name, File(fh), save=True)
		except Exception:
			return False

		Profile.objects.filter(pk=profile.pk).update(
			avatar_review_status='approved',
			avatar_pending_local='',
		)
		try:
			os.remove(path)
		except Exception:
			pass
		return True

	def approve_single_submission_view(self, request, object_id: int, *args, **kwargs):
		profile = self.get_queryset(request).filter(pk=object_id).first()
		if not profile:
			self.message_user(request, 'Submission not found or already processed.', level=messages.WARNING)
			return redirect(reverse(f'admin:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist'))

		if self._apply_approved_avatar(profile):
			_notify_profile_avatar_review_result(profile=profile, approved=True)
			self.message_user(request, f'Approved @{getattr(getattr(profile, "user", None), "username", profile.pk)} profile pic submission.')
		else:
			self.message_user(request, 'Could not approve submission (missing or invalid file).', level=messages.WARNING)

		return redirect(reverse(f'admin:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist'))

	def reject_single_submission_view(self, request, object_id: int, *args, **kwargs):
		profile = self.get_queryset(request).filter(pk=object_id).first()
		if not profile:
			self.message_user(request, 'Submission not found or already processed.', level=messages.WARNING)
			return redirect(reverse(f'admin:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist'))

		path = str(getattr(profile, 'avatar_pending_local', '') or '').strip()
		Profile.objects.filter(pk=profile.pk).update(
			avatar_review_status='rejected',
			avatar_pending_local='',
		)
		if path:
			try:
				os.remove(path)
			except Exception:
				pass
		_notify_profile_avatar_review_result(profile=profile, approved=False)
		self.message_user(request, f'Rejected @{getattr(getattr(profile, "user", None), "username", profile.pk)} profile pic submission.')
		return redirect(reverse(f'admin:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist'))

	@admin.action(description='Approve selected submissions')
	def approve_selected_submissions(self, request, queryset):
		ok = 0
		failed = 0
		for profile in queryset:
			if self._apply_approved_avatar(profile):
				ok += 1
				_notify_profile_avatar_review_result(profile=profile, approved=True)
			else:
				failed += 1
		if ok:
			self.message_user(request, f'Approved {ok} profile pic submission(s).')
		if failed:
			self.message_user(request, f'{failed} submission(s) could not be approved (missing or invalid file).', level=messages.WARNING)

	@admin.action(description='Reject selected submissions')
	def reject_selected_submissions(self, request, queryset):
		rejected = 0
		for profile in queryset:
			path = str(getattr(profile, 'avatar_pending_local', '') or '').strip()
			Profile.objects.filter(pk=profile.pk).update(
				avatar_review_status='rejected',
				avatar_pending_local='',
			)
			if path:
				try:
					os.remove(path)
				except Exception:
					pass
			rejected += 1
			_notify_profile_avatar_review_result(profile=profile, approved=False)
		self.message_user(request, f'Rejected {rejected} profile pic submission(s).')


@admin.register(ProfileBannerSubmission)
class ProfileBannerSubmissionAdmin(admin.ModelAdmin):
	list_display = ('user', 'queue_status', 'submitted_at', 'pending_preview', 'row_actions')
	list_filter = ('cover_review_status',)
	search_fields = ('user__username', 'displayname', 'cover_pending_local')
	actions = ('approve_selected_submissions', 'reject_selected_submissions')
	ordering = ('-id',)

	def get_urls(self):
		urls = super().get_urls()
		custom_urls = [
			path(
				'<int:object_id>/approve/',
				self.admin_site.admin_view(self.approve_single_submission_view),
				name=f'{self.model._meta.app_label}_{self.model._meta.model_name}_approve',
			),
			path(
				'<int:object_id>/reject/',
				self.admin_site.admin_view(self.reject_single_submission_view),
				name=f'{self.model._meta.app_label}_{self.model._meta.model_name}_reject',
			),
		]
		return custom_urls + urls

	def has_add_permission(self, request):
		return False

	def get_queryset(self, request):
		qs = super().get_queryset(request).select_related('user')
		return qs.filter(cover_review_status='pending').exclude(cover_pending_local='')

	@admin.display(description='Queue status')
	def queue_status(self, obj):
		return 'Pending review'

	@admin.display(description='Submitted at')
	def submitted_at(self, obj):
		path = str(getattr(obj, 'cover_pending_local', '') or '').strip()
		if not path:
			return '-'
		try:
			ts = os.path.getmtime(path)
			return timezone.datetime.fromtimestamp(ts, tz=timezone.get_current_timezone())
		except Exception:
			return '-'

	@admin.display(description='Pending image')
	def pending_preview(self, obj):
		path = str(getattr(obj, 'cover_pending_local', '') or '').strip()
		if not path:
			return '-'
		name = os.path.basename(path)
		if not name:
			return '-'
		base = str(getattr(settings, 'MEDIA_URL', '/media/') or '/media/')
		if not base.endswith('/'):
			base += '/'
		img_url = f"{base}pending_covers/{name}"
		return format_html(
			'<a href="{}" target="_blank" rel="noopener">'
			'<img src="{}" alt="pending banner" style="width:96px;height:48px;object-fit:cover;border-radius:8px;border:1px solid #ddd;" />'
			'</a>',
			img_url,
			img_url,
		)

	@admin.display(description='Actions')
	def row_actions(self, obj):
		approve_url = reverse(
			f'admin:{self.model._meta.app_label}_{self.model._meta.model_name}_approve',
			args=[obj.pk],
		)
		reject_url = reverse(
			f'admin:{self.model._meta.app_label}_{self.model._meta.model_name}_reject',
			args=[obj.pk],
		)
		return format_html(
			'<div style="display:flex;gap:8px;align-items:center;">'
			'<a class="button" href="{}" style="background:#16a34a;border-color:#15803d;color:#fff;">Approve</a>'
			'<a class="button" href="{}" style="background:#dc2626;border-color:#b91c1c;color:#fff;" '
			'onclick="return confirm(\'Reject this banner photo submission?\');">Reject</a>'
			'</div>',
			approve_url,
			reject_url,
		)

	def _apply_approved_cover(self, profile) -> bool:
		path = str(getattr(profile, 'cover_pending_local', '') or '').strip()
		if not path or not os.path.exists(path):
			Profile.objects.filter(pk=profile.pk).update(
				cover_review_status='rejected',
				cover_pending_local='',
			)
			return False

		ext = os.path.splitext(path)[1].lower() or '.jpg'
		file_name = f"cover_reviewed_{profile.user_id}_{int(timezone.now().timestamp())}{ext}"
		try:
			with open(path, 'rb') as fh:
				profile.cover_image.save(file_name, File(fh), save=True)
		except Exception:
			return False

		Profile.objects.filter(pk=profile.pk).update(
			cover_review_status='approved',
			cover_pending_local='',
		)
		try:
			os.remove(path)
		except Exception:
			pass
		return True

	def approve_single_submission_view(self, request, object_id: int, *args, **kwargs):
		profile = self.get_queryset(request).filter(pk=object_id).first()
		if not profile:
			self.message_user(request, 'Submission not found or already processed.', level=messages.WARNING)
			return redirect(reverse(f'admin:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist'))

		if self._apply_approved_cover(profile):
			_notify_profile_banner_review_result(profile=profile, approved=True)
			self.message_user(request, f'Approved @{getattr(getattr(profile, "user", None), "username", profile.pk)} banner photo submission.')
		else:
			self.message_user(request, 'Could not approve submission (missing or invalid file).', level=messages.WARNING)

		return redirect(reverse(f'admin:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist'))

	def reject_single_submission_view(self, request, object_id: int, *args, **kwargs):
		profile = self.get_queryset(request).filter(pk=object_id).first()
		if not profile:
			self.message_user(request, 'Submission not found or already processed.', level=messages.WARNING)
			return redirect(reverse(f'admin:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist'))

		path = str(getattr(profile, 'cover_pending_local', '') or '').strip()
		Profile.objects.filter(pk=profile.pk).update(
			cover_review_status='rejected',
			cover_pending_local='',
		)
		if path:
			try:
				os.remove(path)
			except Exception:
				pass
		_notify_profile_banner_review_result(profile=profile, approved=False)
		self.message_user(request, f'Rejected @{getattr(getattr(profile, "user", None), "username", profile.pk)} banner photo submission.')
		return redirect(reverse(f'admin:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist'))

	@admin.action(description='Approve selected submissions')
	def approve_selected_submissions(self, request, queryset):
		ok = 0
		failed = 0
		for profile in queryset:
			if self._apply_approved_cover(profile):
				ok += 1
				_notify_profile_banner_review_result(profile=profile, approved=True)
			else:
				failed += 1
		if ok:
			self.message_user(request, f'Approved {ok} banner photo submission(s).')
		if failed:
			self.message_user(request, f'{failed} submission(s) could not be approved (missing or invalid file).', level=messages.WARNING)

	@admin.action(description='Reject selected submissions')
	def reject_selected_submissions(self, request, queryset):
		rejected = 0
		for profile in queryset:
			path = str(getattr(profile, 'cover_pending_local', '') or '').strip()
			Profile.objects.filter(pk=profile.pk).update(
				cover_review_status='rejected',
				cover_pending_local='',
			)
			if path:
				try:
					os.remove(path)
				except Exception:
					pass
			rejected += 1
			_notify_profile_banner_review_result(profile=profile, approved=False)
		self.message_user(request, f'Rejected {rejected} banner photo submission(s).')


@admin.register(StorySubmission)
class StorySubmissionAdmin(admin.ModelAdmin):
	list_display = ('id', 'user', 'queue_status', 'submitted_at', 'pending_preview', 'row_actions')
	list_filter = ('review_status', 'created_at')
	search_fields = ('user__username', 'pending_local')
	actions = ('approve_selected_submissions', 'reject_selected_submissions')
	ordering = ('-created_at',)

	def get_urls(self):
		urls = super().get_urls()
		custom_urls = [
			path(
				'<int:object_id>/approve/',
				self.admin_site.admin_view(self.approve_single_submission_view),
				name=f'{self.model._meta.app_label}_{self.model._meta.model_name}_approve',
			),
			path(
				'<int:object_id>/reject/',
				self.admin_site.admin_view(self.reject_single_submission_view),
				name=f'{self.model._meta.app_label}_{self.model._meta.model_name}_reject',
			),
		]
		return custom_urls + urls

	def has_add_permission(self, request):
		return False

	def get_queryset(self, request):
		qs = super().get_queryset(request).select_related('user')
		return qs.filter(review_status='pending').exclude(pending_local='')

	@admin.display(description='Queue status')
	def queue_status(self, obj):
		return 'Pending review'

	@admin.display(description='Submitted at')
	def submitted_at(self, obj):
		path = str(getattr(obj, 'pending_local', '') or '').strip()
		if not path:
			return '-'
		try:
			ts = os.path.getmtime(path)
			return timezone.datetime.fromtimestamp(ts, tz=timezone.get_current_timezone())
		except Exception:
			return '-'

	@admin.display(description='Pending image')
	def pending_preview(self, obj):
		path = str(getattr(obj, 'pending_local', '') or '').strip()
		if not path:
			return '-'
		name = os.path.basename(path)
		if not name:
			return '-'
		base = str(getattr(settings, 'MEDIA_URL', '/media/') or '/media/')
		if not base.endswith('/'):
			base += '/'
		img_url = f"{base}pending_stories/{name}"
		return format_html(
			'<a href="{}" target="_blank" rel="noopener">'
			'<img src="{}" alt="pending story" style="width:48px;height:48px;object-fit:cover;border-radius:8px;border:1px solid #ddd;" />'
			'</a>',
			img_url,
			img_url,
		)

	@admin.display(description='Actions')
	def row_actions(self, obj):
		approve_url = reverse(
			f'admin:{self.model._meta.app_label}_{self.model._meta.model_name}_approve',
			args=[obj.pk],
		)
		reject_url = reverse(
			f'admin:{self.model._meta.app_label}_{self.model._meta.model_name}_reject',
			args=[obj.pk],
		)
		return format_html(
			'<div style="display:flex;gap:8px;align-items:center;">'
			'<a class="button" href="{}" style="background:#16a34a;border-color:#15803d;color:#fff;">Approve</a>'
			'<a class="button" href="{}" style="background:#dc2626;border-color:#b91c1c;color:#fff;" '
			'onclick="return confirm(\'Reject this story submission?\');">Reject</a>'
			'</div>',
			approve_url,
			reject_url,
		)

	def _create_approved_story(self, submission, reviewed_by=None):
		path = str(getattr(submission, 'pending_local', '') or '').strip()
		if not path or not os.path.exists(path):
			StorySubmission.objects.filter(pk=submission.pk).update(
				review_status='rejected',
				pending_local='',
				reviewed_at=timezone.now(),
				reviewed_by=reviewed_by,
			)
			return None

		ext = os.path.splitext(path)[1].lower() or '.jpg'
		file_name = f"story_reviewed_{submission.user_id}_{int(timezone.now().timestamp())}{ext}"
		story = Story(user=submission.user)
		try:
			with open(path, 'rb') as fh:
				story.image.save(file_name, File(fh), save=True)
		except Exception:
			return None

		# Keep only the newest active story for this user.
		now = timezone.now()
		cutoff = now - timedelta(hours=getattr(Story, 'TTL_HOURS', 24))
		active_qs = (
			Story.objects
			.filter(user=submission.user)
			.filter(
				models.Q(expires_at__gt=now)
				| models.Q(expires_at__isnull=True, created_at__gte=cutoff)
			)
			.order_by('-created_at', '-id')
		)
		for s in active_qs[1:]:
			try:
				s.delete()
			except Exception:
				pass

		StorySubmission.objects.filter(pk=submission.pk).update(
			review_status='approved',
			pending_local='',
			reviewed_at=timezone.now(),
			reviewed_by=reviewed_by,
			approved_story=story,
		)
		try:
			os.remove(path)
		except Exception:
			pass
		return story

	def approve_single_submission_view(self, request, object_id: int, *args, **kwargs):
		submission = self.get_queryset(request).filter(pk=object_id).first()
		if not submission:
			self.message_user(request, 'Submission not found or already processed.', level=messages.WARNING)
			return redirect(reverse(f'admin:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist'))

		story = self._create_approved_story(submission, reviewed_by=getattr(request, 'user', None))
		if story is not None:
			_notify_story_review_result(user_id=submission.user_id, approved=True)
			self.message_user(request, f'Approved @{getattr(submission.user, "username", submission.user_id)} story submission.')
		else:
			self.message_user(request, 'Could not approve story submission (missing or invalid file).', level=messages.WARNING)

		return redirect(reverse(f'admin:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist'))

	def reject_single_submission_view(self, request, object_id: int, *args, **kwargs):
		submission = self.get_queryset(request).filter(pk=object_id).first()
		if not submission:
			self.message_user(request, 'Submission not found or already processed.', level=messages.WARNING)
			return redirect(reverse(f'admin:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist'))

		path = str(getattr(submission, 'pending_local', '') or '').strip()
		StorySubmission.objects.filter(pk=submission.pk).update(
			review_status='rejected',
			pending_local='',
			reviewed_at=timezone.now(),
			reviewed_by=getattr(request, 'user', None),
		)
		if path:
			try:
				os.remove(path)
			except Exception:
				pass
		_notify_story_review_result(user_id=submission.user_id, approved=False)
		self.message_user(request, f'Rejected @{getattr(submission.user, "username", submission.user_id)} story submission.')
		return redirect(reverse(f'admin:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist'))

	@admin.action(description='Approve selected submissions')
	def approve_selected_submissions(self, request, queryset):
		ok = 0
		failed = 0
		for submission in queryset:
			story = self._create_approved_story(submission, reviewed_by=getattr(request, 'user', None))
			if story is not None:
				ok += 1
				_notify_story_review_result(user_id=submission.user_id, approved=True)
			else:
				failed += 1
		if ok:
			self.message_user(request, f'Approved {ok} story submission(s).')
		if failed:
			self.message_user(request, f'{failed} submission(s) could not be approved (missing or invalid file).', level=messages.WARNING)

	@admin.action(description='Reject selected submissions')
	def reject_selected_submissions(self, request, queryset):
		rejected = 0
		for submission in queryset:
			path = str(getattr(submission, 'pending_local', '') or '').strip()
			StorySubmission.objects.filter(pk=submission.pk).update(
				review_status='rejected',
				pending_local='',
				reviewed_at=timezone.now(),
				reviewed_by=getattr(request, 'user', None),
			)
			if path:
				try:
					os.remove(path)
				except Exception:
					pass
			rejected += 1
			_notify_story_review_result(user_id=submission.user_id, approved=False)
		self.message_user(request, f'Rejected {rejected} story submission(s).')


@admin.register(UserDevice)
class UserDeviceAdmin(admin.ModelAdmin):
	list_display = ('user', 'user_email', 'device_label', 'last_ip', 'ip_city', 'first_seen', 'last_seen')
	list_filter = ('first_seen', 'last_seen')
	search_fields = ('user__username', 'user__email', 'device_label', 'last_ip', 'user_agent')
	readonly_fields = ('user', 'ua_hash', 'user_agent', 'device_label', 'first_seen', 'last_seen', 'last_ip')
	actions = ('export_selected_as_csv',)

	@admin.display(description='Email')
	def user_email(self, obj):
		try:
			return str(getattr(getattr(obj, 'user', None), 'email', '') or '-')
		except Exception:
			return '-'

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

	@admin.action(description='Export selected user devices (CSV)')
	def export_selected_as_csv(self, request, queryset):
		response = HttpResponse(content_type='text/csv; charset=utf-8')
		response['Content-Disposition'] = 'attachment; filename="user_devices_export.csv"'

		writer = csv.writer(response)
		writer.writerow([
			'username',
			'device_label',
			'last_ip',
			'city_location',
			'first_seen',
			'last_seen',
			'user_agent',
		])

		for obj in queryset.select_related('user').order_by('-last_seen'):
			writer.writerow([
				str(getattr(getattr(obj, 'user', None), 'username', '') or ''),
				str(getattr(obj, 'device_label', '') or ''),
				str(getattr(obj, 'last_ip', '') or ''),
				str(self.ip_city(obj) or ''),
				str(getattr(obj, 'first_seen', '') or ''),
				str(getattr(obj, 'last_seen', '') or ''),
				str(getattr(obj, 'user_agent', '') or ''),
			])

		return response


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