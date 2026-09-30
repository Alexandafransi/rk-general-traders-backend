from django.core.management.base import BaseCommand

from ops.models import PaymentMethod

DEFAULT_PAYMENT_METHODS = ["Cash", "Mobile Money", "Bank Transfer", "Card"]


class Command(BaseCommand):
    help = "Idempotently ensure the default payment methods exist, so Sales/Purchases/Expenses forms aren't empty on a fresh deployment."

    def handle(self, *args, **options):
        created = 0
        for name in DEFAULT_PAYMENT_METHODS:
            _, was_created = PaymentMethod.objects.get_or_create(name=name)
            created += int(was_created)
        if created:
            self.stdout.write(self.style.SUCCESS(f"Created {created} default payment method(s)."))
        else:
            self.stdout.write("Default payment methods already exist, skipping.")
