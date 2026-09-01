from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.Model):
    """A dynamic, superadmin-managed access level (e.g. Manager, Accountant,
    Sales). Superadmin and Admin are NOT rows here — they're fixed, built-in
    roles with full access, hardcoded as User.SUPERADMIN / User.ADMIN."""

    key = models.SlugField(max_length=30, unique=True)
    name = models.CharField(max_length=60)
    modules = models.JSONField(default=list, blank=True, help_text="Module keys this role can access")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class User(AbstractUser):
    """A login account for the dashboard. Role controls which modules the
    account can access; branch scopes it to one shop's data (superadmin and
    admin see every branch)."""

    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    FIXED_ROLES = (SUPERADMIN, ADMIN)

    role = models.CharField(max_length=30, default="sales", help_text="'superadmin', 'admin', or a Role.key")
    branch = models.ForeignKey(
        "ops.Branch", on_delete=models.SET_NULL, null=True, blank=True, related_name="staff_accounts"
    )
    phone = models.CharField(max_length=30, blank=True)

    class Meta:
        ordering = ["username"]

    @property
    def full_name(self):
        return self.get_full_name() or self.username

    @property
    def is_operational_role(self):
        return self.role not in self.FIXED_ROLES
