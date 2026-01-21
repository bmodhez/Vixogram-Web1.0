from django.db import migrations, models


def forwards_map_ended_to_completed(apps, schema_editor):
    ChatChallenge = apps.get_model('a_rtchat', 'ChatChallenge')
    # Old implementation used status='ended'. New lifecycle uses completed/cancelled.
    try:
        ChatChallenge.objects.filter(status='ended').update(status='completed')
    except Exception:
        pass


def backwards_map_completed_to_ended(apps, schema_editor):
    ChatChallenge = apps.get_model('a_rtchat', 'ChatChallenge')
    try:
        ChatChallenge.objects.filter(status='completed').update(status='ended')
        ChatChallenge.objects.filter(status='cancelled').update(status='ended')
    except Exception:
        pass


class Migration(migrations.Migration):

    dependencies = [
        ('a_rtchat', '0023_chatchallenge'),
    ]

    operations = [
        migrations.RunPython(
            forwards_map_ended_to_completed,
            backwards_map_completed_to_ended,
        ),
        migrations.AlterField(
            model_name='chatchallenge',
            name='status',
            field=models.CharField(
                choices=[('active', 'Active'), ('completed', 'Completed'), ('cancelled', 'Cancelled')],
                db_index=True,
                default='active',
                max_length=16,
            ),
        ),
    ]
