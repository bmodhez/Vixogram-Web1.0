from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('a_rtchat', '0032_chatgroup_admins_m2m'),
    ]

    operations = [
        migrations.AddField(
            model_name='chatgroup',
            name='allow_media_uploads',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='chatgroup',
            name='announcement_pinned',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='chatgroup',
            name='room_avatar',
            field=models.ImageField(blank=True, null=True, upload_to='room_avatars/'),
        ),
        migrations.AddField(
            model_name='chatgroup',
            name='room_description',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='chatgroup',
            name='slow_mode_seconds',
            field=models.PositiveSmallIntegerField(default=0),
        ),
    ]
