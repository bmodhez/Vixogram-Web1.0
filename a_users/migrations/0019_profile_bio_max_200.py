from django.db import migrations, models
import django.core.validators


BIO_MAX_LENGTH = 200


def trim_profile_bios(apps, schema_editor):
    Profile = apps.get_model('a_users', 'Profile')
    qs = Profile.objects.exclude(info__isnull=True).exclude(info='')
    for prof in qs.iterator():
        try:
            info = prof.info
            if info and len(info) > BIO_MAX_LENGTH:
                prof.info = info[:BIO_MAX_LENGTH]
                prof.save(update_fields=['info'])
        except Exception:
            # Best-effort; don't fail migrations due to a single bad row.
            continue


class Migration(migrations.Migration):

    dependencies = [
        ('a_users', '0018_profile_location'),
    ]

    operations = [
        migrations.AlterField(
            model_name='profile',
            name='info',
            field=models.TextField(
                blank=True,
                max_length=BIO_MAX_LENGTH,
                null=True,
                validators=[django.core.validators.MaxLengthValidator(BIO_MAX_LENGTH)],
            ),
        ),
        migrations.RunPython(trim_profile_bios, migrations.RunPython.noop),
    ]
