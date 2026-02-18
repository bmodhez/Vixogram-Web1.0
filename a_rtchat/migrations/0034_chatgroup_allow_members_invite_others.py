from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('a_rtchat', '0033_chatgroup_private_settings_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='chatgroup',
            name='allow_members_invite_others',
            field=models.BooleanField(default=False),
        ),
    ]
