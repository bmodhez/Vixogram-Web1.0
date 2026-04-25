from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('a_users', '0037_profile_private_rooms_created_total'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='cover_pending_local',
            field=models.CharField(blank=True, default='', max_length=500),
        ),
        migrations.AddField(
            model_name='profile',
            name='cover_review_status',
            field=models.CharField(
                choices=[('none', 'None'), ('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')],
                db_index=True,
                default='none',
                max_length=10,
            ),
        ),
    ]
