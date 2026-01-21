from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('a_rtchat', '0022_blocked_message_event'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ChatChallenge',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('emoji_only', 'Emoji-only'), ('no_vowels', 'No vowels'), ('finish_meme', 'Finish the meme'), ('truth_or_dare', 'Truth or dare'), ('time_attack', 'Time attack')], db_index=True, max_length=32)),
                ('status', models.CharField(choices=[('active', 'Active'), ('ended', 'Ended')], db_index=True, default='active', max_length=16)),
                ('prompt', models.TextField(blank=True, default='')),
                ('meta', models.JSONField(blank=True, default=dict)),
                ('started_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('ends_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('ended_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_chat_challenges', to=settings.AUTH_USER_MODEL)),
                ('group', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='challenges', to='a_rtchat.chatgroup')),
            ],
            options={
                'ordering': ['-created'],
            },
        ),
        migrations.AddIndex(
            model_name='chatchallenge',
            index=models.Index(fields=['group', 'status', '-created'], name='cc_group_status_idx'),
        ),
    ]
