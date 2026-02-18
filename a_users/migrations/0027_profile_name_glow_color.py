from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('a_users', '0026_chatbanhistory'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='name_glow_color',
            field=models.CharField(
                choices=[
                    ('none', 'No glow'),
                    ('aurora', 'Aurora'),
                    ('sunset', 'Sunset'),
                    ('neon', 'Neon'),
                    ('rose', 'Rose'),
                    ('electric', 'Electric'),
                    ('toxic', 'Toxic'),
                    ('royal', 'Royal'),
                    ('ice', 'Ice'),
                    ('cosmic', 'Cosmic'),
                ],
                default='none',
                max_length=16,
            ),
        ),
    ]
