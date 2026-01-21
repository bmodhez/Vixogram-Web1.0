from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('a_users', '0009_profile_dnd'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='referral_points',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.CreateModel(
            name='Referral',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('points_awarded', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('awarded_at', models.DateTimeField(blank=True, null=True)),
                ('referred', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='referral_received', to=settings.AUTH_USER_MODEL)),
                ('referrer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='referrals_made', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='referral',
            index=models.Index(fields=['referrer', '-created_at'], name='ref_referrer_created_idx'),
        ),
        migrations.AddIndex(
            model_name='referral',
            index=models.Index(fields=['awarded_at', '-created_at'], name='ref_awarded_created_idx'),
        ),
    ]
