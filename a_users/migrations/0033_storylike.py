from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('a_users', '0032_alter_profile_chat_theme'),
    ]

    operations = [
        migrations.CreateModel(
            name='StoryLike',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('story', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='likes', to='a_users.story')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='story_likes', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'indexes': [
                    models.Index(fields=['story', '-created_at'], name='storylike_story_created_idx'),
                    models.Index(fields=['user', '-created_at'], name='storylike_user_created_idx'),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name='storylike',
            constraint=models.UniqueConstraint(fields=('story', 'user'), name='uniq_story_like'),
        ),
    ]
