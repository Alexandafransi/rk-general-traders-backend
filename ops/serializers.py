from accounts.models import Role, User
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import (
    AuditLog,
    Branch,
    Category,
    Customer,
    Expense,
    InstallationJob,
    Lead,
    Payslip,
    PaymentMethod,
    Product,
    Purchase,
    Sale,
    StockMovement,
    Supplier,
    Technician,
    TodoItem,
)

FIXED_ROLE_LABELS = {User.SUPERADMIN: "Super Admin", User.ADMIN: "Admin"}


def role_display_for(role_key):
    if not role_key:
        return ""
    if role_key in FIXED_ROLE_LABELS:
        return FIXED_ROLE_LABELS[role_key]
    role = Role.objects.filter(key=role_key).only("name").first()
    return role.name if role else role_key.title()


class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = ["id", "name", "location", "phone", "active", "created_at"]


class AuditLogSerializer(serializers.ModelSerializer):
    action_display = serializers.CharField(source="get_action_display", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True, default=None)

    class Meta:
        model = AuditLog
        fields = [
            "id", "actor_username", "action", "action_display", "model_name",
            "object_id", "object_repr", "branch", "branch_name", "created_at",
        ]


class RoleSerializer(serializers.ModelSerializer):
    users_count = serializers.SerializerMethodField()

    class Meta:
        model = Role
        fields = ["id", "key", "name", "modules", "users_count", "created_at"]

    def get_users_count(self, obj):
        # Accounts using this role, plus staff-only records (no login) tagged
        # with it directly — linked staff are excluded here since they're
        # already counted via their account, and access_role just mirrors it.
        accounts = User.objects.filter(role=obj.key).count()
        unlinked_staff = Technician.objects.filter(access_role=obj.key, account__isnull=True).count()
        return accounts + unlinked_staff

    def validate_key(self, value):
        if value in User.FIXED_ROLES:
            raise serializers.ValidationError("'admin' and 'superadmin' are reserved and can't be used as a role key.")
        return value

    def validate_modules(self, value):
        from .permissions import ALLOWED_MODULES

        if not isinstance(value, list) or not all(isinstance(m, str) for m in value):
            raise serializers.ValidationError("modules must be a list of module key strings.")
        unknown = set(value) - set(ALLOWED_MODULES)
        if unknown:
            raise serializers.ValidationError(f"Unknown module(s): {', '.join(sorted(unknown))}")
        return value


class UserSerializer(serializers.ModelSerializer):
    branch = BranchSerializer(read_only=True)
    branch_id = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.all(), source="branch", write_only=True, required=False, allow_null=True
    )
    role_display = serializers.SerializerMethodField()
    full_name = serializers.ReadOnlyField()

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "first_name", "last_name", "full_name", "phone",
            "role", "role_display", "branch", "branch_id", "is_active", "date_joined", "last_login",
        ]
        read_only_fields = ["date_joined", "last_login"]

    def get_role_display(self, obj):
        return role_display_for(obj.role)


class UserWriteSerializer(serializers.ModelSerializer):
    """Used for admin-driven registration/editing. Password is optional on
    update (leave blank to keep the current one) and required on create."""

    password = serializers.CharField(write_only=True, required=False, allow_blank=True, validators=[validate_password])

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "first_name", "last_name", "phone",
            "role", "branch", "is_active", "password",
        ]

    def validate_email(self, value):
        value = (value or "").strip()
        if not value:
            return value
        qs = User.objects.filter(email__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_role(self, value):
        if value not in User.FIXED_ROLES and not Role.objects.filter(key=value).exists():
            raise serializers.ValidationError("Unknown role.")
        return value

    def validate(self, attrs):
        if self.instance is None and not attrs.get("password"):
            raise serializers.ValidationError({"password": "This field is required when creating a user."})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class CategorySerializer(serializers.ModelSerializer):
    products_count = serializers.SerializerMethodField()
    purchases_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ["id", "name", "products_count", "purchases_count", "created_at"]

    def get_products_count(self, obj):
        return obj.products.count()

    def get_purchases_count(self, obj):
        return obj.purchases.count()


class PaymentMethodSerializer(serializers.ModelSerializer):
    sales_count = serializers.SerializerMethodField()
    purchases_count = serializers.SerializerMethodField()
    expenses_count = serializers.SerializerMethodField()

    class Meta:
        model = PaymentMethod
        fields = ["id", "name", "sales_count", "purchases_count", "expenses_count", "created_at"]

    def get_sales_count(self, obj):
        return obj.sales.count()

    def get_purchases_count(self, obj):
        return obj.purchases.count()

    def get_expenses_count(self, obj):
        return obj.expenses.count()


class ProductSerializer(serializers.ModelSerializer):
    branch = BranchSerializer(read_only=True)
    branch_id = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.all(), source="branch", write_only=True, required=False, allow_null=True
    )
    category = CategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(), source="category", write_only=True, required=False, allow_null=True
    )
    is_low_stock = serializers.ReadOnlyField()
    is_out_of_stock = serializers.ReadOnlyField()

    class Meta:
        model = Product
        fields = [
            "id", "name", "branch", "branch_id", "category", "category_id", "unit", "quantity_on_hand",
            "reorder_level", "notes", "is_low_stock", "is_out_of_stock", "created_at",
        ]


class StockMovementSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    reason_display = serializers.CharField(source="get_reason_display", read_only=True)

    class Meta:
        model = StockMovement
        fields = ["id", "product", "change", "reason", "reason_display", "reference", "note", "created_at"]


class TechnicianSerializer(serializers.ModelSerializer):
    initials = serializers.ReadOnlyField()
    access_role_display = serializers.SerializerMethodField()
    account_username = serializers.CharField(source="account.username", read_only=True, default=None)

    class Meta:
        model = Technician
        fields = [
            "id", "name", "role", "access_role", "access_role_display", "account_username", "email", "phone",
            "tint", "active", "monthly_salary", "date_joined", "initials",
        ]

    def get_access_role_display(self, obj):
        return role_display_for(obj.access_role)


class LeadSerializer(serializers.ModelSerializer):
    branch = BranchSerializer(read_only=True)
    branch_id = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.all(), source="branch", write_only=True, required=False, allow_null=True
    )
    interest_display = serializers.CharField(source="get_interest_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    source_display = serializers.CharField(source="get_source_display", read_only=True)

    class Meta:
        model = Lead
        fields = [
            "id", "branch", "branch_id", "name", "phone", "email", "location", "interest", "interest_display",
            "source", "source_display", "status", "status_display", "notes", "created_at",
        ]


class InstallationJobSerializer(serializers.ModelSerializer):
    branch = BranchSerializer(read_only=True)
    branch_id = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.all(), source="branch", write_only=True, required=False, allow_null=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    category_display = serializers.CharField(source="get_category_display", read_only=True)
    priority_display = serializers.CharField(source="get_priority_display", read_only=True)
    assigned_to = TechnicianSerializer(read_only=True)
    assigned_to_id = serializers.PrimaryKeyRelatedField(
        queryset=Technician.objects.all(), source="assigned_to", write_only=True, required=False, allow_null=True
    )

    class Meta:
        model = InstallationJob
        fields = [
            "id", "branch", "branch_id", "job_number", "title", "customer_name", "location",
            "category", "category_display", "status", "status_display",
            "priority", "priority_display", "assigned_to", "assigned_to_id", "start_date", "created_at",
        ]


class TodoItemSerializer(serializers.ModelSerializer):
    assigned_to = TechnicianSerializer(read_only=True)

    class Meta:
        model = TodoItem
        fields = ["id", "title", "description", "due_date", "assigned_to", "done", "created_at"]


class PayslipSerializer(serializers.ModelSerializer):
    technician = TechnicianSerializer(read_only=True)
    technician_id = serializers.PrimaryKeyRelatedField(
        queryset=Technician.objects.all(), source="technician", write_only=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    net_pay = serializers.ReadOnlyField()

    class Meta:
        model = Payslip
        fields = [
            "id", "technician", "technician_id", "period", "base_salary", "allowances",
            "deductions", "net_pay", "status", "status_display", "paid_date", "created_at",
        ]


class SupplierSerializer(serializers.ModelSerializer):
    purchase_count = serializers.SerializerMethodField()

    class Meta:
        model = Supplier
        fields = ["id", "name", "contact_person", "phone", "email", "notes", "purchase_count", "created_at"]

    def get_purchase_count(self, obj):
        return obj.purchases.count()


class PurchaseSerializer(serializers.ModelSerializer):
    branch = BranchSerializer(read_only=True)
    branch_id = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.all(), source="branch", write_only=True, required=False, allow_null=True
    )
    supplier = SupplierSerializer(read_only=True)
    supplier_id = serializers.PrimaryKeyRelatedField(
        queryset=Supplier.objects.all(), source="supplier", write_only=True, required=False, allow_null=True
    )
    product = ProductSerializer(read_only=True)
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(), source="product", write_only=True, required=False, allow_null=True
    )
    category = CategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(), source="category", write_only=True, required=False, allow_null=True
    )
    payment_method = PaymentMethodSerializer(read_only=True)
    payment_method_id = serializers.PrimaryKeyRelatedField(
        queryset=PaymentMethod.objects.all(), source="payment_method", write_only=True, required=False, allow_null=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    total_cost = serializers.ReadOnlyField()

    class Meta:
        model = Purchase
        fields = [
            "id", "branch", "branch_id", "po_number", "supplier", "supplier_id", "product", "product_id", "item_name",
            "category", "category_id", "quantity", "unit_cost", "total_cost", "payment_method", "payment_method_id",
            "status", "status_display", "purchase_date", "created_at",
        ]


class ExpenseSerializer(serializers.ModelSerializer):
    branch = BranchSerializer(read_only=True)
    branch_id = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.all(), source="branch", write_only=True, required=False, allow_null=True
    )
    category_display = serializers.CharField(source="get_category_display", read_only=True)
    payment_method = PaymentMethodSerializer(read_only=True)
    payment_method_id = serializers.PrimaryKeyRelatedField(
        queryset=PaymentMethod.objects.all(), source="payment_method", write_only=True, required=False, allow_null=True
    )
    recorded_by = TechnicianSerializer(read_only=True)
    recorded_by_id = serializers.PrimaryKeyRelatedField(
        queryset=Technician.objects.all(), source="recorded_by", write_only=True, required=False, allow_null=True
    )

    class Meta:
        model = Expense
        fields = [
            "id", "branch", "branch_id", "category", "category_display", "description", "amount", "expense_date",
            "payment_method", "payment_method_id", "recorded_by", "recorded_by_id", "created_at",
        ]


class CustomerSerializer(serializers.ModelSerializer):
    source_display = serializers.CharField(source="get_source_display", read_only=True)

    class Meta:
        model = Customer
        fields = ["id", "name", "phone", "email", "location", "notes", "source", "source_display", "created_at"]


class SaleSerializer(serializers.ModelSerializer):
    branch = BranchSerializer(read_only=True)
    branch_id = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.all(), source="branch", write_only=True, required=False, allow_null=True
    )
    job = InstallationJobSerializer(read_only=True)
    job_id = serializers.PrimaryKeyRelatedField(
        queryset=InstallationJob.objects.all(), source="job", write_only=True, required=False, allow_null=True
    )
    product = ProductSerializer(read_only=True)
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(), source="product", write_only=True, required=False, allow_null=True
    )
    category_display = serializers.CharField(source="get_category_display", read_only=True)
    payment_status_display = serializers.CharField(source="get_payment_status_display", read_only=True)
    payment_method = PaymentMethodSerializer(read_only=True)
    payment_method_id = serializers.PrimaryKeyRelatedField(
        queryset=PaymentMethod.objects.all(), source="payment_method", write_only=True, required=False, allow_null=True
    )
    amount = serializers.ReadOnlyField()
    balance_due = serializers.ReadOnlyField()
    is_overdue = serializers.ReadOnlyField()

    class Meta:
        model = Sale
        fields = [
            "id", "branch", "branch_id", "invoice_number", "customer_name", "job", "job_id", "product", "product_id",
            "category", "category_display", "description", "quantity", "unit_price", "amount",
            "amount_paid", "balance_due", "payment_status", "payment_status_display",
            "payment_method", "payment_method_id", "payment_due_date", "is_overdue", "sale_date", "created_at",
        ]
