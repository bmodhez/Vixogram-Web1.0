from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('a_users', '0030_profile_chat_theme'),
    ]

    operations = [
        migrations.AlterField(
            model_name='profile',
            name='chat_theme',
            field=models.CharField(
                choices=[
                    ('default', 'Default'),
                    ('theme1', 'Theme 1'),
                    ('theme2', 'Theme 2'),
                    ('theme3', 'Theme 3'),
                ],
                default='default',
                max_length=12,
            ),
        ),
    ]
