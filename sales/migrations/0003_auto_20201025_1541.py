# Generated by Django 3.1.2 on 2020-10-25 15:41

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('contacts', '0001_initial'),
        ('sales', '0002_auto_20201018_1134'),
    ]

    operations = [
        migrations.DeleteModel(
            name='Customer',
        ),
        migrations.DeleteModel(
            name='HistoricalCustomer',
        ),
        migrations.CreateModel(
            name='Customer',
            fields=[
            ],
            options={
                'proxy': True,
                'indexes': [],
                'constraints': [],
            },
            bases=('contacts.contact',),
        ),
    ]
