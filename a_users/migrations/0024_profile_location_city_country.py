from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('a_users', '0023_remove_prosubscription_user_delete_propayment_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='last_location_city',
            field=models.CharField(blank=True, max_length=80, null=True),
        ),
        migrations.AddField(
            model_name='profile',
            name='last_location_country',
            field=models.CharField(blank=True, max_length=80, null=True),
        ),
    ]
