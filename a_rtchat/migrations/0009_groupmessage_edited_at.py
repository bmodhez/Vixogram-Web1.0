from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('a_rtchat', '0008_chatgroup_created'),
    ]

    operations = [
        migrations.AddField(
            model_name='groupmessage',
            name='edited_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
