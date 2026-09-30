from accounts.models import Role, User
from rest_framework.permissions import SAFE_METHODS, BasePermission

# The full set of module keys a dynamic Role can be granted. "accounts" (the
# login-account registry) and role management itself are deliberately absent
# — those stay hardcoded to admin/superadmin regardless of role config.
ALLOWED_MODULES = [
    "dashboard", "branches", "jobs", "leads", "customers", "staff", "payroll",
    "finance", "sales", "purchases", "inventory", "expenses", "suppliers", "categories",
    "payment_methods",
]


def can_access_module(user, module):
    if not (user and user.is_authenticated):
        return False
    if user.role in User.FIXED_ROLES:
        return True
    role = Role.objects.filter(key=user.role).only("modules").first()
    return bool(role and module in role.modules)


def assignable_roles_for(user):
    """Which role keys `user` is allowed to hand out when registering/editing
    other accounts. Prevents privilege escalation — only superadmin may mint
    another admin or superadmin."""
    if not (user and user.is_authenticated):
        return set()
    dynamic_keys = set(Role.objects.values_list("key", flat=True))
    if user.role == User.SUPERADMIN:
        return {User.SUPERADMIN, User.ADMIN} | dynamic_keys
    if user.role == User.ADMIN:
        return dynamic_keys
    return set()


def ModulePermission(module):
    """A DRF permission class requiring the caller's role to be allowed on `module`."""

    class _ModulePermission(BasePermission):
        def has_permission(self, request, view):
            return can_access_module(request.user, module)

    return _ModulePermission


def ReadOpenModulePermission(module):
    """Like ModulePermission, but GET/HEAD/OPTIONS are open to any authenticated
    account. Use for resources that double as reference data in other pages'
    forms (e.g. picking a technician on a Job, a product on a Sale) — a role
    that can't manage `module` as its own page should still be able to read
    it when it just needs the list for a dropdown, not be locked out entirely."""

    class _Perm(BasePermission):
        def has_permission(self, request, view):
            user = request.user
            if not (user and user.is_authenticated):
                return False
            if request.method in SAFE_METHODS:
                return True
            return can_access_module(user, module)

    return _Perm


class IsAdminOrSuperAdmin(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role in User.FIXED_ROLES)


class IsSuperAdmin(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role == User.SUPERADMIN)


class BranchReadPermission(BasePermission):
    """Every authenticated role needs to know branch names to work within
    their own branch-scoped data (the header switcher, form pickers, etc.),
    but only admin/superadmin may create, edit or delete branches themselves."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return can_access_module(user, "branches")


class RoleReadPermission(BasePermission):
    """Every authenticated role needs to read the role list (to know its own
    module access and to power the Accounts role picker), but only
    superadmin may create, edit or delete roles."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return user.role == User.SUPERADMIN
