from accounts.models import Role, User
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

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


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Role & Branch", {"fields": ("role", "branch", "phone")}),
    )
    list_display = ("username", "email", "role", "branch", "is_active", "is_staff")
    list_filter = DjangoUserAdmin.list_filter + ("role", "branch")


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "key", "modules", "created_at")
    search_fields = ("name", "key")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor_username", "action", "model_name", "object_id", "object_repr", "branch")
    list_filter = ("action", "model_name", "branch")
    search_fields = ("actor_username", "object_repr")
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ("name", "location", "phone", "active", "created_at")
    list_filter = ("active",)
    search_fields = ("name", "location")


@admin.register(Technician)
class TechnicianAdmin(admin.ModelAdmin):
    list_display = ("name", "role", "access_role", "account", "email", "phone", "monthly_salary", "active", "date_joined")
    list_filter = ("active", "access_role")
    search_fields = ("name", "email")


@admin.register(Payslip)
class PayslipAdmin(admin.ModelAdmin):
    list_display = ("technician", "period", "base_salary", "allowances", "deductions", "net_pay", "status", "paid_date")
    list_filter = ("status", "period")
    search_fields = ("technician__name",)


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ("name", "branch", "interest", "status", "source", "location", "created_at")
    list_filter = ("branch", "status", "interest", "source")
    search_fields = ("name", "phone", "email", "location")


@admin.register(InstallationJob)
class InstallationJobAdmin(admin.ModelAdmin):
    list_display = (
        "job_number",
        "branch",
        "title",
        "customer_name",
        "category",
        "status",
        "priority",
        "assigned_to",
        "start_date",
    )
    list_filter = ("branch", "status", "priority", "category")
    search_fields = ("job_number", "title", "customer_name", "location")


@admin.register(TodoItem)
class TodoItemAdmin(admin.ModelAdmin):
    list_display = ("title", "assigned_to", "due_date", "done")
    list_filter = ("done",)
    search_fields = ("title",)


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "contact_person", "phone", "email")
    search_fields = ("name", "contact_person", "email")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)


@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "branch", "category", "quantity_on_hand", "reorder_level", "unit", "created_at")
    list_filter = ("branch", "category")
    search_fields = ("name",)


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ("product", "change", "reason", "reference", "created_at")
    list_filter = ("reason",)
    search_fields = ("product__name", "reference")


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ("po_number", "branch", "item_name", "supplier", "product", "category", "quantity", "unit_cost", "total_cost", "status", "purchase_date")
    list_filter = ("branch", "status", "category")
    search_fields = ("po_number", "item_name", "supplier__name")


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("description", "branch", "category", "amount", "payment_method", "recorded_by", "expense_date")
    list_filter = ("branch", "category", "payment_method")
    search_fields = ("description",)


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = (
        "invoice_number", "branch", "customer_name", "product", "category", "amount", "amount_paid",
        "balance_due", "payment_status", "sale_date",
    )
    list_filter = ("branch", "payment_status", "category")
    search_fields = ("invoice_number", "customer_name")


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "email", "location", "source", "created_at")
    list_filter = ("source",)
    search_fields = ("name", "phone", "email", "location")
