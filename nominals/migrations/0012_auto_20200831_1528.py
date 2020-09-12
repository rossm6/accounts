# Generated by Django 3.0.8 on 2020-08-31 15:28

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('nominals', '0011_auto_20200803_2048'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='nominaltransaction',
            name='unique_batch',
        ),
        migrations.AlterField(
            model_name='nominaltransaction',
            name='type',
            field=models.CharField(choices=[('pp', 'Payment'), ('pr', 'Refund'), ('pi', 'Invoice'), ('pc', 'Credit Note'), ('nj', 'Journal'), ('sp', 'Receipt'), ('sr', 'Refund'), ('si', 'Invoice'), ('sc', 'Credit Note'), ('cp', 'Payment'), ('cr', 'Receipt')], max_length=10),
        ),
        migrations.AddConstraint(
            model_name='nominaltransaction',
            constraint=models.UniqueConstraint(fields=('module', 'header', 'line', 'field'), name='nominal_unique_batch'),
        ),
    ]