from django.contrib import admin

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
	list_display = ('id', 'group', 'author', 'created', 'body', 'file')
	list_filter = ('created',)
	search_fields = ('body', 'author__username', 'group__group_name', 'group__room_code')


@admin.register(ModerationEvent)
class ModerationEventAdmin(admin.ModelAdmin):
	list_display = ('id', 'created', 'action', 'severity', 'confidence', 'user', 'room', 'message')
	list_filter = ('action', 'severity', 'created')
	search_fields = ('text', 'reason', 'user__username', 'room__group_name')