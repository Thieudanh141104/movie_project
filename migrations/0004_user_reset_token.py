# Generated by Django 5.1.2 on 2024-11-23 06:10

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0003_merge_20241120_0326'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='reset_token',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
    ]
