from django.db import migrations


def convert_manual_to_imported(apps, schema_editor):
    Media = apps.get_model('media_library', 'Media')
    Media.objects.filter(source_type='manual').update(source_type='imported')


def revert_imported_to_manual(apps, schema_editor):
    Media = apps.get_model('media_library', 'Media')
    Media.objects.filter(source_type='imported').update(source_type='manual')


class Migration(migrations.Migration):

    dependencies = [
        ('media_library', '0013_delete_image_delete_imagegroup'),
    ]

    operations = [
        migrations.RunPython(convert_manual_to_imported, revert_imported_to_manual),
    ]
