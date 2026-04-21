# users/apps.py

from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'users'
    
    def ready(self):
        # Importer les signals seulement quand l'application est prête
        import users.signals