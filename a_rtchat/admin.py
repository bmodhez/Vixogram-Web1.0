from django.contrib import admin
from django.contrib.admin.views.main import ChangeList

from .models import ChatGroup, GroupMessage, PrivateChatGroup, ModerationEvent


@admin.register(ChatGroup)
class ChatGroupAdmin(admin.ModelAdmin):
	list_display = ('group_name', 'groupchat_name', 'code_room_name', 'room_code', 'is_private', 'is_code_room', 'admin')
	list_filter = ('is_private', 'is_code_room')
	search_fields = ('group_name', 'groupchat_name', 'code_room_name', 'room_code', 'admin__username')


@admin.register(PrivateChatGroup)
class PrivateChatGroupAdmin(admin.ModelAdmin):
	list_display = ('group_name', 'code_room_name', 'room_code', 'is_code_room', 'admin')
	list_filter = ('is_code_room',)
	search_fields = ('group_name', 'code_room_name', 'room_code', 'admin__username')

	def get_queryset(self, request):
		qs = super().get_queryset(request)
		return qs.filter(is_private=True)


@admin.register(GroupMessage)
class GroupMessageAdmin(admin.ModelAdmin):
	list_display = (
		'sr_no',
		'id',
		'group',
		'author',
		'created',
		'is_support_submission',
		'support_submission_type',
		'body',
		'file_caption',
		'file',
	)
	list_filter = ('created', 'is_support_submission', 'support_submission_type')
	search_fields = ('body', 'author__username', 'group__group_name', 'group__room_code')

	class VixoChangeList(ChangeList):
		def get_results(self, request):
			super().get_results(request)
			try:
				start = int(getattr(self, 'page_num', 0) or 0) * int(getattr(self, 'list_per_page', 0) or 0)
			except Exception:
				start = 0
			for i, obj in enumerate(self.result_list, start=start + 1):
				try:
					obj._vixo_sr_no = i
				except Exception:
					pass

	def get_changelist(self, request, **kwargs):
		return self.VixoChangeList

	@admin.display(description='No.')
	def sr_no(self, obj):
		value = getattr(obj, '_vixo_sr_no', None)
		try:
			n = int(value)
		except Exception:
			n = None
		return f'{n:02d}' if n else ''


@admin.register(ModerationEvent)
class ModerationEventAdmin(admin.ModelAdmin):
	list_display = ('id', 'created', 'action', 'severity', 'confidence', 'user', 'room', 'message')
	list_filter = ('action', 'severity', 'created')
	search_fields = ('text', 'reason', 'user__username', 'room__group_name')