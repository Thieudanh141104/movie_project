# Generated by Django 5.1.2 on 2024-11-24 07:08

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0004_user_reset_token'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='avatar',
            field=models.TextField(blank=True, null=True, verbose_name='file'),
        ),
    ]
