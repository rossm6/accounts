# Generated by Django 3.1.1 on 2020-09-23 21:25

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0004_customer_address'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='customer',
            name='address',
        ),
    ]