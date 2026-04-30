from django.apps import AppConfig


class MediaLibraryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "media_library"

    def ready(self):
        import media_library.tasks  # noqa: F401 — registers pre_enqueue/post_execute signal receivers
