from django.db import migrations, models


class Migration(migrations.Migration):

	dependencies = [
		('a_rtchat', '0036_globalannouncement_prefix'),
	]

	operations = [
		migrations.AddField(
			model_name='groupmessage',
			name='is_support_submission',
			field=models.BooleanField(db_index=True, default=False),
		),
		migrations.AddField(
			model_name='groupmessage',
			name='support_submission_type',
			field=models.CharField(blank=True, db_index=True, default='', max_length=20),
		),
	]