from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('a_users', '0021_followrequest'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProSubscription',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('active', 'Active'), ('expired', 'Expired'), ('canceled', 'Canceled')], db_index=True, default='expired', max_length=12)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('expires_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('provider', models.CharField(blank=True, default='', max_length=32)),
                ('last_payment_id', models.CharField(blank=True, default='', max_length=128)),
                ('last_order_id', models.CharField(blank=True, default='', max_length=128)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='pro_subscription', to='auth.user')),
            ],
            options={
                'indexes': [models.Index(fields=['status', 'expires_at'], name='pro_status_exp_idx')],
            },
        ),
        migrations.CreateModel(
            name='ProPayment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('provider', models.CharField(choices=[('razorpay', 'Razorpay'), ('stripe', 'Stripe')], default='razorpay', max_length=20)),
                ('status', models.CharField(choices=[('created', 'Created'), ('paid', 'Paid'), ('failed', 'Failed')], db_index=True, default='created', max_length=12)),
                ('amount_paise', models.PositiveIntegerField(default=0)),
                ('currency', models.CharField(default='INR', max_length=8)),
                ('order_id', models.CharField(blank=True, db_index=True, default='', max_length=128)),
                ('payment_id', models.CharField(blank=True, db_index=True, default='', max_length=128)),
                ('signature', models.CharField(blank=True, default='', max_length=256)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pro_payments', to='auth.user')),
            ],
            options={
                'indexes': [
                    models.Index(fields=['provider', 'order_id'], name='proprov_order_idx'),
                    models.Index(fields=['provider', 'payment_id'], name='proprov_pay_idx'),
                ],
            },
        ),
    ]
