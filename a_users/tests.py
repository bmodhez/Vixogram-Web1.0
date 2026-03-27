import tempfile
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Story


@override_settings(MEDIA_ROOT=tempfile.gettempdir())
class StoryLimitTests(TestCase):
	def _make_active_story(self, user, name_suffix='x'):
		f = SimpleUploadedFile(
			f'story_{name_suffix}.jpg',
			b'fake-image-bytes',
			content_type='image/jpeg',
		)
		return Story.objects.create(
			user=user,
			image=f,
			expires_at=timezone.now() + timedelta(hours=1),
		)

	def test_story_add_modal_blocked_at_1(self):
		user = User.objects.create_user(username='u_story1', password='pass12345')
		self.client.force_login(user)

		self._make_active_story(user, '1')
		self.assertEqual(Story.objects.filter(user=user).count(), 1)

		url = reverse('story-add')
		resp = self.client.get(f'{url}?modal=1', HTTP_HX_REQUEST='true')
		self.assertEqual(resp.status_code, 200)
		self.assertIn('Free plan limited to 1 story', resp.content.decode('utf-8'))

	def test_story_add_allowed_after_delete(self):
		user = User.objects.create_user(username='u_story2', password='pass12345')
		self.client.force_login(user)

		stories = [self._make_active_story(user, str(i)) for i in range(1)]
		stories[0].delete()
		self.assertEqual(Story.objects.filter(user=user).count(), 0)

		url = reverse('story-add')
		resp = self.client.get(f'{url}?modal=1', HTTP_HX_REQUEST='true')
		self.assertEqual(resp.status_code, 200)
		self.assertIn('Add Story', resp.content.decode('utf-8'))

	def test_story_delete_response_updates_story_upload_state(self):
		user = User.objects.create_user(username='u_story3', password='pass12345')
		self.client.force_login(user)

		story = self._make_active_story(user, 'delete_state')
		url = reverse('story-delete', args=[story.id])
		resp = self.client.post(url)

		self.assertEqual(resp.status_code, 200)
		data = resp.json()
		self.assertTrue(bool(data.get('ok')))
		state = data.get('story_upload') or {}
		self.assertTrue(bool(state.get('can_add_story')))
		self.assertEqual(int(state.get('active_count') or -1), 0)
