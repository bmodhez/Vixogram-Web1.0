from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('a_rtchat', '0030_one_time_message_view'),
    ]

    operations = [
        migrations.AddField(
            model_name='chatgroup',
            name='only_admins_can_send',
            field=models.BooleanField(default=False),
        ),
    ]
