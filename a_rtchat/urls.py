from django.urls import path
from .views import *

urlpatterns = [
    path('', chat_view, name="home"),
    path('chat/<username>', get_or_create_chatroom, name="start-chat"),
    path('chat/room/<chatroom_name>', chat_view, name="chatroom"),
    path('chat/poll/<chatroom_name>', chat_poll_view, name="chat-poll"),
    path('chat/new_groupchat/', create_groupchat, name="new-groupchat"),
    path('chat/private/create/', create_private_room, name='private-room-create'),
    path('chat/private/join/', join_private_room_by_code, name='private-room-join'),
    path('chat/edit/<chatroom_name>', chatroom_edit_view, name="edit-chatroom"),
    path('chat/delete/<chatroom_name>', chatroom_delete_view, name="chatroom-delete"),
    path('chat/close/<chatroom_name>', chatroom_close_view, name="chatroom-close"),
    path('chat/leave/<chatroom_name>', chatroom_leave_view, name="chatroom-leave"),
    path('chat/fileupload/<chatroom_name>', chat_file_upload, name="chat-file-upload"),
    path('chat/call/<chatroom_name>', call_view, name='chat-call'),
    path('chat/agora/token/<chatroom_name>', agora_token_view, name='agora-token'),
    path('chat/call/invite/<chatroom_name>', call_invite_view, name='chat-call-invite'),
    path('chat/call/presence/<chatroom_name>', call_presence_view, name='chat-call-presence'),
    path('chat/call/event/<chatroom_name>', call_event_view, name='chat-call-event'),
    path('chat/message/<int:message_id>/edit/', message_edit_view, name='message-edit'),
    path('chat/message/<int:message_id>/delete/', message_delete_view, name='message-delete'),

    # Staff tools
    path('chat/admin/users/', admin_users_view, name='admin-users'),
    path('chat/admin/users/<int:user_id>/toggle-block/', admin_toggle_user_block_view, name='admin-user-toggle-block'),
    path('chat/admin/moderation/', moderation_logs_view, name='moderation-logs'),
]