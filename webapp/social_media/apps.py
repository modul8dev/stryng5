from django.apps import AppConfig


class SocialMediaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "social_media"

    def ready(self):
        try:
            from django_q.models import Schedule
            Schedule.objects.get_or_create(
                func='social_media.tasks.check_scheduled_posts',
                defaults={
                    'schedule_type': Schedule.MINUTES,
                    'minutes': 1,
                    'repeats': -1,
                    'name': 'Check scheduled social media posts',
                },
            )
        except Exception:
            # DB may not be ready (e.g. during initial migrate)
            pass
