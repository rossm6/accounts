# Generated by Django 3.0.7 on 2020-08-01 12:53

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('nominals', '0010_auto_20200727_2009'),
        ('purchases', '0015_purchaseheader_cash_book'),
    ]

    operations = [
        migrations.AddField(
            model_name='purchaseline',
            name='total_nominal_transaction',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='purchase_total_line', to='nominals.NominalTransaction'),
        ),
    ]