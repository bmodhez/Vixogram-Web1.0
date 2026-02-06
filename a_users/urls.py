# a_users/urls.py
from django.urls import path
from .views import *

urlpatterns = [
    path('', profile_view, name='profile'),
    path('story/add/', story_add_view, name='story-add'),
    path('story/<int:story_id>/delete/', story_delete_view, name='story-delete'),
    path('story/<int:story_id>/seen/', story_seen_view, name='story-seen'),
    path('story/<int:story_id>/viewers/', story_viewers_json_view, name='story-viewers'),
    path('config/', profile_config_view, name='profile-config-self'),
    path('edit/', profile_edit_view, name="profile-edit"),
    path('settings/', profile_settings_view, name="profile-settings"),
    path('username/check/', username_availability_view, name='username-check'),
    path('u/<username>/', profile_view, name='profile-user'),
    path('u/<username>/config/', profile_config_view, name='profile-config'),
    path('u/<username>/followers/', profile_followers_partial_view, name='profile-followers'),
    path('u/<username>/following/', profile_following_partial_view, name='profile-following'),
    path('u/<username>/report/', report_user_view, name='report-user'),
    path('u/<username>/follow/', follow_toggle_view, name='follow-toggle'),
    path('follow-requests/', follow_requests_modal_view, name='follow-requests-modal'),
    path('follow-requests/<int:req_id>/<str:action>/', follow_request_decide_view, name='follow-request-decide'),
    path('u/<username>/stories/', user_stories_json_view, name='user-stories'),
    path('u/<username>/remove-follower/', remove_follower_view, name='remove-follower'),
    path('notifications/dropdown/', notifications_dropdown_view, name='notifications-dropdown'),
    path('notifications/<int:notif_id>/read/', notifications_mark_read_view, name='notifications-mark-read'),
    path('notifications/read-all/', notifications_mark_all_read_view, name='notifications-read-all'),
    path('notifications/clear-all/', notifications_clear_all_view, name='notifications-clear-all'),
    path('support/', contact_support_view, name='contact-support'),
    path('invite/', invite_friends_view, name='invite-friends'),
    path('founder-club/apply/', founder_club_apply_view, name='founder-club-apply'),
    path('location/save/', save_location_view, name='profile-location-save'),
]