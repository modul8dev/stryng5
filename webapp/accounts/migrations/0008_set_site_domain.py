from django.db import migrations


def set_site(apps, schema_editor):
    Site = apps.get_model('sites', 'Site')
    Site.objects.filter(pk=1).update(name='Stryng', domain='stryng.io')


def unset_site(apps, schema_editor):
    Site = apps.get_model('sites', 'Site')
    Site.objects.filter(pk=1).update(name='example.com', domain='example.com')


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0007_company_uuid_field'),
        ('sites', '0002_alter_domain_unique'),
    ]

    operations = [
        migrations.RunPython(set_site, reverse_code=unset_site),
    ]
