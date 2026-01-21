# a_users/urls.py
from django.urls import path
from .views import *

urlpatterns = [
    path('', profile_view, name='profile'),
    path('config/', profile_config_view, name='profile-config-self'),
    path('edit/', profile_edit_view, name="profile-edit"),
    path('settings/', profile_settings_view, name="profile-settings"),
    path('u/<username>/', profile_view, name='profile-user'),
    path('u/<username>/config/', profile_config_view, name='profile-config'),
    path('u/<username>/followers/', profile_followers_partial_view, name='profile-followers'),
    path('u/<username>/following/', profile_following_partial_view, name='profile-following'),
    path('u/<username>/report/', report_user_view, name='report-user'),
    path('u/<username>/follow/', follow_toggle_view, name='follow-toggle'),
    path('notifications/dropdown/', notifications_dropdown_view, name='notifications-dropdown'),
    path('notifications/<int:notif_id>/read/', notifications_mark_read_view, name='notifications-mark-read'),
    path('notifications/read-all/', notifications_mark_all_read_view, name='notifications-read-all'),
    path('notifications/clear-all/', notifications_clear_all_view, name='notifications-clear-all'),
    path('support/', contact_support_view, name='contact-support'),
    path('invite/', invite_friends_view, name='invite-friends'),
]