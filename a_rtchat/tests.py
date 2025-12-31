from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


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
