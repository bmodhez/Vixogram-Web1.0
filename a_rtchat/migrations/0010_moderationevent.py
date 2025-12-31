from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('a_rtchat', '0009_groupmessage_edited_at'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ModerationEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('text', models.TextField(blank=True, default='')),
                ('action', models.CharField(choices=[('allow', 'Allow'), ('flag', 'Flag'), ('block', 'Block')], max_length=16)),
                ('categories', models.JSONField(blank=True, default=list)),
                ('severity', models.PositiveSmallIntegerField(default=0)),
                ('confidence', models.FloatField(default=0.0)),
                ('reason', models.CharField(blank=True, default='', max_length=255)),
                ('source', models.CharField(blank=True, default='gemini', max_length=32)),
                ('meta', models.JSONField(blank=True, default=dict)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('message', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='moderation_events', to='a_rtchat.groupmessage')),
                ('room', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='moderation_events', to='a_rtchat.chatgroup')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='moderation_events', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created'],
            },
        ),
    ]
