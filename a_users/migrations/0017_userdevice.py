from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('a_users', '0016_story'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserDevice',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ua_hash', models.CharField(db_index=True, max_length=64)),
                ('user_agent', models.CharField(blank=True, default='', max_length=300)),
                ('device_label', models.CharField(blank=True, default='', max_length=120)),
                ('first_seen', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('last_seen', models.DateTimeField(auto_now=True, db_index=True)),
                ('last_ip', models.GenericIPAddressField(blank=True, null=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='devices', to='auth.user')),
            ],
            options={
                'indexes': [models.Index(fields=['user', '-last_seen'], name='ud_user_last_seen_idx')],
            },
        ),
        migrations.AddConstraint(
            model_name='userdevice',
            constraint=models.UniqueConstraint(fields=('user', 'ua_hash'), name='uniq_user_device_uahash'),
        ),
    ]
