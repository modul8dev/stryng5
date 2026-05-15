# Generated manually on 2026-05-15


from django.db import migrations


def delete_twitter_connections(apps, schema_editor):
    IntegrationConnection = apps.get_model('integrations', 'IntegrationConnection')
    IntegrationConnection.objects.filter(provider='twitter').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0004_alter_integrationconnection_external_account_id_and_more'),
    ]

    operations = [
        migrations.RunPython(delete_twitter_connections, migrations.RunPython.noop),
    ]
