from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('a_users', '0010_referrals_and_points'),
    ]

    operations = [
        migrations.AddField(
            model_name='supportenquiry',
            name='admin_reply',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='supportenquiry',
            name='replied_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
