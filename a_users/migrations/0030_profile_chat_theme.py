from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('a_users', '0029_profile_preferred_location_last_changed_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='chat_theme',
            field=models.CharField(
                choices=[('theme1', 'Theme 1'), ('theme2', 'Theme 2'), ('theme3', 'Theme 3')],
                default='theme1',
                max_length=12,
            ),
        ),
    ]
