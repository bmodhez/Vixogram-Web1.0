from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('a_users', '0028_profile_preferred_location'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='preferred_location_last_changed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
