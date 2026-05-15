# Generated manually on 2026-05-15

import core.fields
from django.db import migrations


def delete_twitter_posts(apps, schema_editor):
    SocialMediaPostPlatform = apps.get_model('social_media', 'SocialMediaPostPlatform')
    SocialMediaPostPlatform.objects.filter(platform='x').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('social_media', '0014_socialmediapost_processing_status'),
    ]

    operations = [
        migrations.RunPython(delete_twitter_posts, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='socialmediapostplatform',
            name='platform',
            field=core.fields.TruncatingCharField(
                choices=[
                    ('linkedin', 'LinkedIn'),
                    ('facebook', 'Facebook'),
                    ('instagram', 'Instagram'),
                ],
                max_length=20,
            ),
        ),
    ]
