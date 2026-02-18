from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('a_users', '0025_profile_chat_banned_until'),
    ]

    operations = [
        migrations.CreateModel(
            name='ChatBanHistory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(choices=[('ban', 'Ban'), ('unban', 'Unban')], db_index=True, max_length=8)),
                ('duration_minutes', models.PositiveIntegerField(default=0)),
                ('banned_until', models.DateTimeField(blank=True, null=True)),
                ('admin_ip', models.GenericIPAddressField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('banned_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='issued_chat_ban_history', to='auth.user')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='chat_ban_history', to='auth.user')),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['user', '-created_at'], name='cbh_user_created_idx'), models.Index(fields=['action', '-created_at'], name='cbh_action_created_idx')],
            },
        ),
    ]
