# Generated by Django 4.0.7 on 2022-09-02 08:48

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='product',
            name='packet_size',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]