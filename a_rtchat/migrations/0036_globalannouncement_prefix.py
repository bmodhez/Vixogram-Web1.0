from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('a_rtchat', '0035_chat_polls'),
    ]

    operations = [
        migrations.AddField(
            model_name='globalannouncement',
            name='prefix',
            field=models.CharField(blank=True, default='Team Vixogram:', max_length=60),
        ),
    ]
