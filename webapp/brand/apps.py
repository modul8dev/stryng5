from django.apps import AppConfig


class BrandConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'brand'
    verbose_name = 'Brand'

    def ready(self):
        import brand.tasks  # noqa: F401 — registers pre_enqueue signal receiver

