from django.urls import path
from .consumers import *
from .random_video_consumers import RandomVideoConsumer

websocket_urlpatterns = [
    path("ws/chatroom/<chatroom_name>", ChatroomConsumer.as_asgi()),
    path("ws/random-video/", RandomVideoConsumer.as_asgi()),
    path("ws/online-status/", OnlineStatusConsumer.as_asgi()),
    path("ws/presence/<username>/", ProfilePresenceConsumer.as_asgi()),
    path("ws/notify/", NotificationsConsumer.as_asgi()),
    path("ws/global-announcement/", GlobalAnnouncementConsumer.as_asgi()),
]