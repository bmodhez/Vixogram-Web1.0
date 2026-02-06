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

	def test_story_add_modal_blocked_at_25(self):
		user = User.objects.create_user(username='u_story1', password='pass12345')
		self.client.force_login(user)

		for i in range(25):
			self._make_active_story(user, str(i))
		self.assertEqual(Story.objects.filter(user=user).count(), 25)

		url = reverse('story-add')
		resp = self.client.get(f'{url}?modal=1', HTTP_HX_REQUEST='true')
		self.assertEqual(resp.status_code, 200)
		self.assertIn('You can put only 25 stories.', resp.content.decode('utf-8'))

	def test_story_add_allowed_after_delete(self):
		user = User.objects.create_user(username='u_story2', password='pass12345')
		self.client.force_login(user)

		stories = [self._make_active_story(user, str(i)) for i in range(25)]
		stories[0].delete()
		self.assertEqual(Story.objects.filter(user=user).count(), 24)

		url = reverse('story-add')
		resp = self.client.get(f'{url}?modal=1', HTTP_HX_REQUEST='true')
		self.assertEqual(resp.status_code, 200)
		self.assertIn('Add Story', resp.content.decode('utf-8'))
