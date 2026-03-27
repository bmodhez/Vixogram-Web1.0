# Generated manually - avatar moderation fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('a_users', '0035_chatbanhistory_note'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='avatar_review_status',
            field=models.CharField(
                choices=[
                    ('none', 'None'),
                    ('pending', 'Pending'),
                    ('approved', 'Approved'),
                    ('rejected', 'Rejected'),
                ],
                db_index=True,
                default='none',
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name='profile',
            name='avatar_pending_local',
            field=models.CharField(blank=True, default='', max_length=500),
        ),
    ]
