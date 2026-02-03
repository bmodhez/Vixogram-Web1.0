from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('a_users', '0017_userdevice'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='last_location_lat',
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
        ),
        migrations.AddField(
            model_name='profile',
            name='last_location_lng',
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
        ),
        migrations.AddField(
            model_name='profile',
            name='last_location_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
