from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('a_rtchat', '0034_chatgroup_allow_members_invite_others'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ChatPoll',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('question', models.CharField(max_length=180)),
                ('allow_multiple_answers', models.BooleanField(default=False)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='created_chat_polls', to=settings.AUTH_USER_MODEL)),
                ('group', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='polls', to='a_rtchat.chatgroup')),
            ],
            options={
                'ordering': ['-created'],
            },
        ),
        migrations.CreateModel(
            name='ChatPollOption',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('text', models.CharField(max_length=120)),
                ('sort_order', models.PositiveSmallIntegerField(default=0)),
                ('poll', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='options', to='a_rtchat.chatpoll')),
            ],
            options={
                'ordering': ['sort_order', 'id'],
            },
        ),
        migrations.CreateModel(
            name='ChatPollVote',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('option', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='votes', to='a_rtchat.chatpolloption')),
                ('poll', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='votes', to='a_rtchat.chatpoll')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='chat_poll_votes', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddField(
            model_name='groupmessage',
            name='poll',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='message', to='a_rtchat.chatpoll'),
        ),
        migrations.AddIndex(
            model_name='chatpoll',
            index=models.Index(fields=['group', '-created'], name='cp_group_created_idx'),
        ),
        migrations.AddIndex(
            model_name='chatpolloption',
            index=models.Index(fields=['poll', 'sort_order'], name='cpo_poll_order_idx'),
        ),
        migrations.AddConstraint(
            model_name='chatpollvote',
            constraint=models.UniqueConstraint(fields=('poll', 'option', 'user'), name='uniq_chat_poll_option_user'),
        ),
        migrations.AddIndex(
            model_name='chatpollvote',
            index=models.Index(fields=['poll', 'user'], name='cpv_poll_user_idx'),
        ),
        migrations.AddIndex(
            model_name='chatpollvote',
            index=models.Index(fields=['option'], name='cpv_option_idx'),
        ),
    ]
