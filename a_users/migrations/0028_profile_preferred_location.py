from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('a_users', '0027_profile_name_glow_color'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='preferred_location_city',
            field=models.CharField(blank=True, max_length=80, null=True),
        ),
        migrations.AddField(
            model_name='profile',
            name='preferred_location_country',
            field=models.CharField(blank=True, max_length=80, null=True),
        ),
        migrations.AddField(
            model_name='profile',
            name='preferred_location_state',
            field=models.CharField(blank=True, max_length=80, null=True),
        ),
    ]
