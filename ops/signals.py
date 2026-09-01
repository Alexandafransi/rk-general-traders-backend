from django.db.models.signals import post_save
from django.dispatch import receiver

from accounts.models import Role, User

from .models import Technician


@receiver(post_save, sender=User)
def sync_technician_from_account(sender, instance, **kwargs):
    """Keeps the Staff Directory in sync with login accounts: every account
    with an operational role (not admin/superadmin) gets a matching
    Technician entry, created automatically the first time and kept
    up to date on every subsequent edit."""

    if instance.role in User.FIXED_ROLES:
        Technician.objects.filter(account=instance).update(access_role="")
        return

    role_obj = Role.objects.filter(key=instance.role).first()
    Technician.objects.update_or_create(
        account=instance,
        defaults={
            "name": instance.get_full_name() or instance.username,
            "email": instance.email,
            "phone": instance.phone,
            "access_role": instance.role,
            "role": role_obj.name if role_obj else instance.role.title(),
        },
    )
