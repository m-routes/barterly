from django.apps import AppConfig


class PrivacyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.privacy"
    label = "privacy"
    verbose_name = "Privacy: consent, data rights and retention"
