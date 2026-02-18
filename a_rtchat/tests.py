from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.contrib.messages import get_messages
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from datetime import timedelta
import base64

from .models import ChatGroup, CodeRoomJoinRequest, GroupMessage, OneTimeMessageView
from .retention import trim_chat_group_messages
from a_users.models import ChatBanHistory


class AdminToggleUserBlockTests(TestCase):
	def test_staff_can_toggle_block_and_redirect_next(self):
		staff = User.objects.create_user(username='staff', password='pass12345', is_staff=True)
		target = User.objects.create_user(username='target', password='pass12345')

		self.client.force_login(staff)

		next_url = reverse('chatroom', kwargs={'chatroom_name': 'public-chat'})
		url = reverse('admin-user-toggle-block', kwargs={'user_id': target.id})

		response = self.client.post(url, data={'next': next_url})
		self.assertEqual(response.status_code, 302)
		self.assertEqual(response['Location'], next_url)

		target.refresh_from_db()
		self.assertTrue(target.profile.chat_blocked)


class AdminUserBanTests(TestCase):
	def test_staff_can_ban_and_unban_user(self):
		staff = User.objects.create_user(username='staff2', password='pass12345', is_staff=True)
		target = User.objects.create_user(username='target2', password='pass12345')
		self.client.force_login(staff)

		url = reverse('admin-user-ban', kwargs={'user_id': target.id})
		resp = self.client.post(url, data={'minutes': '10'})
		self.assertEqual(resp.status_code, 302)

		target.refresh_from_db()
		self.assertIsNotNone(target.profile.chat_banned_until)
		self.assertTrue(target.profile.chat_banned_until > timezone.now())
		self.assertTrue(
			ChatBanHistory.objects.filter(
				user=target,
				action=ChatBanHistory.ACTION_BAN,
				duration_minutes=10,
			).exists()
		)

		resp2 = self.client.post(url, data={'minutes': '0'})
		self.assertEqual(resp2.status_code, 302)

		target.refresh_from_db()
		self.assertIsNone(target.profile.chat_banned_until)
		self.assertTrue(
			ChatBanHistory.objects.filter(
				user=target,
				action=ChatBanHistory.ACTION_UNBAN,
			).exists()
		)


class PrivateRoomMemberLimitTests(TestCase):
	def test_join_private_code_room_blocks_after_limit(self):
		# Create a private code room
		owner = User.objects.create_user(username='owner', password='pass12345')
		room = ChatGroup.objects.create(is_private=True, is_code_room=True, admin=owner)
		room.members.add(owner)

		# Fill room up to 10 members total
		for i in range(2, 11):
			u = User.objects.create_user(username=f'u{i}', password='pass12345')
			room.members.add(u)

		self.assertEqual(room.members.count(), 10)

		# 11th user tries to join by code
		joiner = User.objects.create_user(username='joiner', password='pass12345')
		self.client.force_login(joiner)
		url = reverse('private-room-join')
		response = self.client.post(url, data={'code': room.room_code}, follow=True)

		# Should redirect back to home with an error message
		self.assertEqual(response.status_code, 200)
		msgs = [m.message for m in get_messages(response.wsgi_request)]
		self.assertIn('User limit reached', msgs)
		room.refresh_from_db()
		self.assertEqual(room.members.count(), 10)


class PrivateRoomRenameTests(TestCase):
	def test_admin_can_rename_private_code_room(self):
		owner = User.objects.create_user(username='owner2', password='pass12345')
		room = ChatGroup.objects.create(is_private=True, is_code_room=True, admin=owner)
		room.members.add(owner)

		self.client.force_login(owner)
		url = reverse('private-room-rename', kwargs={'chatroom_name': room.group_name})
		resp = self.client.post(url, data={'name': 'My Room'})
		self.assertEqual(resp.status_code, 200)
		data = resp.json()
		self.assertTrue(data.get('ok'))

		room.refresh_from_db()
		self.assertEqual(room.code_room_name, 'My Room')

	def test_non_admin_cannot_rename(self):
		owner = User.objects.create_user(username='owner3', password='pass12345')
		other = User.objects.create_user(username='other3', password='pass12345')
		room = ChatGroup.objects.create(is_private=True, is_code_room=True, admin=owner)
		room.members.add(owner, other)

		self.client.force_login(other)
		url = reverse('private-room-rename', kwargs={'chatroom_name': room.group_name})
		resp = self.client.post(url, data={'name': 'Hacked'})
		self.assertEqual(resp.status_code, 404)

		room.refresh_from_db()
		self.assertNotEqual(room.code_room_name, 'Hacked')

	def test_admin_can_clear_name(self):
		owner = User.objects.create_user(username='owner4', password='pass12345')
		room = ChatGroup.objects.create(is_private=True, is_code_room=True, admin=owner, code_room_name='X')
		room.members.add(owner)

		self.client.force_login(owner)
		url = reverse('private-room-rename', kwargs={'chatroom_name': room.group_name})
		resp = self.client.post(url, data={'name': ''})
		self.assertEqual(resp.status_code, 200)

		room.refresh_from_db()
		self.assertIsNone(room.code_room_name)


class CodeRoomWaitingListTests(TestCase):
	def test_join_by_code_creates_waiting_request_not_member(self):
		owner = User.objects.create_user(username='owner_wait', password='pass12345')
		room = ChatGroup.objects.create(is_private=True, is_code_room=True, admin=owner)
		room.members.add(owner)

		joiner = User.objects.create_user(username='joiner_wait', password='pass12345')
		self.client.force_login(joiner)
		url = reverse('private-room-join')
		resp = self.client.post(url, data={'code': room.room_code})
		self.assertEqual(resp.status_code, 302)

		room.refresh_from_db()
		self.assertFalse(room.members.filter(pk=joiner.pk).exists())
		self.assertTrue(CodeRoomJoinRequest.objects.filter(room=room, user=joiner, admitted_at__isnull=True).exists())

		# Visiting the room shows waiting page (not 404)
		resp2 = self.client.get(reverse('chatroom', kwargs={'chatroom_name': room.group_name}))
		self.assertEqual(resp2.status_code, 200)

	def test_admin_can_list_and_admit_waiting_user(self):
		owner = User.objects.create_user(username='owner_admit', password='pass12345')
		room = ChatGroup.objects.create(is_private=True, is_code_room=True, admin=owner)
		room.members.add(owner)

		joiner = User.objects.create_user(username='joiner_admit', password='pass12345')
		CodeRoomJoinRequest.objects.create(room=room, user=joiner)

		self.client.force_login(owner)
		list_url = reverse('code-room-waiting-list', args=[room.group_name])
		list_resp = self.client.get(list_url)
		self.assertEqual(list_resp.status_code, 200)
		data = list_resp.json()
		self.assertTrue(data.get('ok'))
		self.assertEqual(data.get('count'), 1)

		admit_url = reverse('code-room-waiting-admit', args=[room.group_name])
		admit_resp = self.client.post(admit_url, data={'user_id': joiner.id})
		self.assertEqual(admit_resp.status_code, 200)
		self.assertTrue(admit_resp.json().get('ok'))

		room.refresh_from_db()
		self.assertTrue(room.members.filter(pk=joiner.pk).exists())
		jr = CodeRoomJoinRequest.objects.get(room=room, user=joiner)
		self.assertIsNotNone(jr.admitted_at)

	def test_waiting_list_only_shows_active_requesters(self):
		owner = User.objects.create_user(username='owner_active', password='pass12345')
		room = ChatGroup.objects.create(is_private=True, is_code_room=True, admin=owner)
		room.members.add(owner)

		joiner = User.objects.create_user(username='joiner_inactive', password='pass12345')
		jr = CodeRoomJoinRequest.objects.create(room=room, user=joiner)
		CodeRoomJoinRequest.objects.filter(pk=jr.pk).update(last_seen_at=timezone.now() - timedelta(minutes=5))

		self.client.force_login(owner)
		list_url = reverse('code-room-waiting-list', args=[room.group_name])
		resp = self.client.get(list_url)
		self.assertEqual(resp.status_code, 200)
		data = resp.json()
		self.assertTrue(data.get('ok'))
		self.assertEqual(data.get('count'), 0)

	def test_waiting_status_updates_last_seen_at(self):
		owner = User.objects.create_user(username='owner_seen', password='pass12345')
		room = ChatGroup.objects.create(is_private=True, is_code_room=True, admin=owner)
		room.members.add(owner)

		joiner = User.objects.create_user(username='joiner_seen', password='pass12345')
		jr = CodeRoomJoinRequest.objects.create(room=room, user=joiner)
		past = timezone.now() - timedelta(minutes=2)
		CodeRoomJoinRequest.objects.filter(pk=jr.pk).update(last_seen_at=past)

		self.client.force_login(joiner)
		status_url = reverse('code-room-waiting-status', args=[room.group_name])
		resp = self.client.get(status_url)
		self.assertEqual(resp.status_code, 200)
		self.assertEqual(resp.json().get('status'), 'pending')

		jr.refresh_from_db()
		self.assertGreater(jr.last_seen_at, past)

	def test_waiting_leave_removes_pending_request(self):
		owner = User.objects.create_user(username='owner_leave', password='pass12345')
		room = ChatGroup.objects.create(is_private=True, is_code_room=True, admin=owner)
		room.members.add(owner)

		joiner = User.objects.create_user(username='joiner_leave', password='pass12345')
		CodeRoomJoinRequest.objects.create(room=room, user=joiner)

		self.client.force_login(joiner)
		leave_url = reverse('code-room-waiting-leave', args=[room.group_name])
		resp = self.client.get(f'{leave_url}?next={reverse("home")}')
		self.assertEqual(resp.status_code, 302)
		self.assertEqual(resp.url, reverse('home'))

		self.assertFalse(
			CodeRoomJoinRequest.objects.filter(
				room=room,
				user=joiner,
				admitted_at__isnull=True,
			).exists()
		)


class PrivateRoomRemovalRealtimeTests(TestCase):
	def test_removed_member_cannot_send_without_refresh(self):
		owner = User.objects.create_user(username='owner_rm1', password='pass12345')
		member = User.objects.create_user(username='member_rm1', password='pass12345')
		room = ChatGroup.objects.create(is_private=True, is_code_room=True, admin=owner)
		room.members.add(owner, member)

		# Admin removes member.
		self.client.force_login(owner)
		remove_url = reverse('chatroom-member-remove', kwargs={'chatroom_name': room.group_name, 'user_id': member.id})
		remove_resp = self.client.post(remove_url)
		self.assertEqual(remove_resp.status_code, 200)
		room.refresh_from_db()
		self.assertFalse(room.members.filter(pk=member.pk).exists())

		# Removed user tries to send immediately (HTMX-style request) without page refresh.
		self.client.force_login(member)
		send_url = reverse('chatroom', kwargs={'chatroom_name': room.group_name})
		send_resp = self.client.post(send_url, data={'body': 'hello after removal'}, HTTP_HX_REQUEST='true')
		self.assertEqual(send_resp.status_code, 403)
		self.assertEqual(send_resp.headers.get('X-Vixo-Not-Member', ''), '1')

		# No new user-authored message should be persisted.
		self.assertFalse(
			GroupMessage.objects.filter(group=room, author=member, body='hello after removal').exists()
		)


class MessageRetentionTests(TestCase):
	def test_room_keeps_only_latest_100_messages(self):
		owner = User.objects.create_user(username='owner_ret', password='pass12345')
		room = ChatGroup.objects.create(is_private=False, admin=owner)

		# Create 105 messages (ids increase with creation order)
		for i in range(105):
			GroupMessage.objects.create(group=room, author=owner, body=f'm{i}')

		self.assertEqual(GroupMessage.objects.filter(group=room).count(), 105)

		trim_chat_group_messages(chat_group_id=room.id, keep_last=100)

		qs = GroupMessage.objects.filter(group=room).order_by('id')
		self.assertEqual(qs.count(), 100)
		remaining_bodies = list(qs.values_list('body', flat=True)[:6])
		self.assertEqual(remaining_bodies[0], 'm5')


class OneTimeViewTests(TestCase):
	def _png_file(self):
		# 1x1 transparent PNG
		data = base64.b64decode(
			'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO5kZpQAAAAASUVORK5CYII='
		)
		return SimpleUploadedFile('t.png', data, content_type='image/png')

	def test_recipient_can_open_once(self):
		sender = User.objects.create_user(username='ot_sender', password='pass12345')
		recipient = User.objects.create_user(username='ot_recipient', password='pass12345')
		room = ChatGroup.objects.create(is_private=True, admin=sender)
		room.members.add(sender, recipient)

		msg = GroupMessage.objects.create(
			group=room,
			author=sender,
			file=self._png_file(),
			one_time_view_seconds=3,
		)

		self.client.force_login(recipient)
		url = reverse('message-one-time-open', kwargs={'message_id': msg.id})
		resp = self.client.post(url)
		self.assertEqual(resp.status_code, 200)
		data = resp.json()
		self.assertTrue(data.get('ok'))

		self.assertTrue(OneTimeMessageView.objects.filter(message=msg, user=recipient).exists())

		# Second open should be blocked.
		resp2 = self.client.post(url)
		self.assertEqual(resp2.status_code, 410)

	def test_sender_cannot_open(self):
		sender = User.objects.create_user(username='ot_sender2', password='pass12345')
		recipient = User.objects.create_user(username='ot_recipient2', password='pass12345')
		room = ChatGroup.objects.create(is_private=True, admin=sender)
		room.members.add(sender, recipient)
		msg = GroupMessage.objects.create(
			group=room,
			author=sender,
			file=self._png_file(),
			one_time_view_seconds=8,
		)

		self.client.force_login(sender)
		url = reverse('message-one-time-open', kwargs={'message_id': msg.id})
		resp = self.client.post(url)
		self.assertEqual(resp.status_code, 403)
