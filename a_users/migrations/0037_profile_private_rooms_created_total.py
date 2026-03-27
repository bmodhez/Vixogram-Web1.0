from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('a_users', '0036_profile_avatar_review'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='private_rooms_created_total',
            field=models.PositiveIntegerField(default=0),
        ),
    ]
