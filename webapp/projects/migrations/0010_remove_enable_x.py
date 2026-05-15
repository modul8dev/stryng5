# Generated manually on 2026-05-15

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0009_add_enable_autopost'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='project',
            name='enable_x',
        ),
    ]
