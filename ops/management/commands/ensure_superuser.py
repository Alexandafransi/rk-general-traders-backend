import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Idempotently create a superuser from DJANGO_SUPERUSER_* env vars if one doesn't exist."

    def handle(self, *args, **options):
        User = get_user_model()
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME", "admin")
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "admin@rkgeneraltraders.co.tz")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "rkadmin2026")

        if User.objects.filter(username=username).exists():
            self.stdout.write(f"Superuser '{username}' already exists, skipping.")
            return

        User.objects.create_superuser(username=username, email=email, password=password, role=User.SUPERADMIN)
        self.stdout.write(self.style.SUCCESS(f"Created superuser '{username}'."))
