from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('a_users', '0020_storyview'),
    ]

    operations = [
        migrations.CreateModel(
            name='FollowRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('from_user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='follow_requests_sent', to=settings.AUTH_USER_MODEL)),
                ('to_user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='follow_requests_received', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'indexes': [
                    models.Index(fields=['to_user', '-created_at'], name='followreq_to_created_idx'),
                    models.Index(fields=['from_user', '-created_at'], name='followreq_from_created_idx'),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name='followrequest',
            constraint=models.UniqueConstraint(fields=('from_user', 'to_user'), name='unique_follow_request'),
        ),
    ]
