# Generated by Django 5.1.2 on 2024-11-19 09:29

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='userseat',
            name='user',
        ),
        migrations.AddField(
            model_name='userseat',
            name='booking',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='app.booking'),
        ),
    ]
