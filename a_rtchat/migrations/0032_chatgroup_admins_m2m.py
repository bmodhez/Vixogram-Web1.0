from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('a_rtchat', '0031_chatgroup_only_admins_can_send'),
    ]

    operations = [
        migrations.AddField(
            model_name='chatgroup',
            name='admins',
            field=models.ManyToManyField(blank=True, related_name='admin_in_groups', to='auth.user'),
        ),
    ]
