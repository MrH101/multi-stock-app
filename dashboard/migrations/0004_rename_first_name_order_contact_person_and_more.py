# Generated by Django 4.0.7 on 2022-10-19 23:23

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0003_product_batch_number'),
    ]

    operations = [
        migrations.RenameField(
            model_name='order',
            old_name='first_name',
            new_name='contact_person',
        ),
        migrations.RenameField(
            model_name='order',
            old_name='last_name',
            new_name='pharmacy_name',
        ),
        migrations.AddField(
            model_name='customer',
            name='contact_person',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='customer',
            name='pharmacy_name',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='order',
            name='user',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='orders', to='dashboard.customer'),
        ),
        migrations.AlterField(
            model_name='product',
            name='batch_number',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
