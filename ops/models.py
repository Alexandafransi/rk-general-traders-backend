from django.db import models
from django.db.models import F
from django.db.models.signals import post_save
from django.dispatch import receiver


class Branch(models.Model):
    """A physical RK General Traders shop. Sales, purchases, expenses, jobs,
    leads and inventory are all recorded independently per branch."""

    name = models.CharField(max_length=120)
    location = models.CharField(max_length=160, blank=True, help_text="e.g. Kariakoo, Dar es Salaam")
    phone = models.CharField(max_length=30, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class AuditLog(models.Model):
    """A silent, append-only trail of who changed what and when, across every
    feature. Nothing in the regular API/UI exposes this to the acting user —
    it's only ever surfaced through the superadmin-only audit log endpoint.

    `actor_username` is a point-in-time snapshot (not just the `actor` FK)
    so the record stays meaningful even after that account is deleted."""

    class Action(models.TextChoices):
        CREATE = "create", "Created"
        UPDATE = "update", "Updated"
        DELETE = "deleted", "Deleted"
        LOGIN = "login", "Logged In"
        LOGIN_FAILED = "login_failed", "Failed Login"
        LOGOUT = "logout", "Logged Out"

    actor = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_logs"
    )
    actor_username = models.CharField(max_length=150, blank=True)
    action = models.CharField(max_length=15, choices=Action.choices)
    model_name = models.CharField(max_length=60)
    object_id = models.CharField(max_length=40, blank=True)
    object_repr = models.CharField(max_length=200, blank=True)
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_logs")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.actor_username or 'system'} {self.action} {self.model_name} #{self.object_id}"


class Technician(models.Model):
    """A staff directory / HR entry. `access_role` mirrors a dynamic Role.key
    (never 'admin'/'superadmin' — those are login-account-only concepts) and
    is purely descriptive when the technician has no login `account`. When
    `account` is set, access_role is kept in sync automatically from it."""

    account = models.OneToOneField(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="technician_profile"
    )
    name = models.CharField(max_length=120)
    role = models.CharField(max_length=120, default="Field Technician", help_text="Job title, e.g. Field Technician")
    access_role = models.CharField(max_length=30, blank=True, help_text="A Role.key, or blank for none")
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    tint = models.PositiveSmallIntegerField(default=1, help_text="1-6, controls avatar color")
    active = models.BooleanField(default=True)
    monthly_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text="Base monthly salary in TZS")
    date_joined = models.DateField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def initials(self):
        parts = self.name.split()
        return "".join(p[0] for p in parts[:2]).upper()


class Payslip(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PAID = "paid", "Paid"

    technician = models.ForeignKey(Technician, on_delete=models.CASCADE, related_name="payslips")
    period = models.DateField(help_text="First day of the pay period's month")
    base_salary = models.DecimalField(max_digits=12, decimal_places=2)
    allowances = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.DRAFT)
    paid_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-period", "technician__name"]
        unique_together = ["technician", "period"]

    def __str__(self):
        return f"{self.technician.name} — {self.period:%B %Y}"

    @property
    def net_pay(self):
        return self.base_salary + self.allowances - self.deductions


class Lead(models.Model):
    class Source(models.TextChoices):
        WEBSITE = "website", "Website"
        WHATSAPP = "whatsapp", "WhatsApp"
        PHONE = "phone", "Phone Call"
        REFERRAL = "referral", "Referral"
        WALK_IN = "walk_in", "Walk-in"

    class Status(models.TextChoices):
        NEW = "new", "New"
        CONTACTED = "contacted", "Contacted"
        QUOTED = "quoted", "Quoted"
        CONVERTED = "converted", "Converted"
        LOST = "lost", "Lost"

    class Interest(models.TextChoices):
        FIBER = "fiber_installation", "Fiber Installation"
        ROUTER = "router_setup", "Router Setup"
        EXTENDER = "wifi_extender", "Wi-Fi Extender"
        MIKROTIK = "mikrotik_voucher", "Mikrotik Voucher System"
        ACCESS_POINT = "access_point", "Access Point"
        ONU = "fiber_onu_ont", "Fiber ONU/ONT"
        UPS = "power_backup", "Power Backup (UPS)"
        SUPPORT = "support", "Maintenance & Support"

    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name="leads")
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    location = models.CharField(max_length=120, blank=True, help_text="e.g. Mikocheni, Dar es Salaam")
    interest = models.CharField(max_length=32, choices=Interest.choices, default=Interest.ROUTER)
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.WEBSITE)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.NEW)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.get_interest_display()})"


class InstallationJob(models.Model):
    class Status(models.TextChoices):
        NOT_STARTED = "not_started", "To do"
        IN_PROGRESS = "in_progress", "In progress"
        REVIEW = "review", "Review"
        ON_HOLD = "on_hold", "On hold"
        CANCELLED = "cancelled", "Cancelled"
        DONE = "done", "Done"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"

    class Category(models.TextChoices):
        FIBER = "fiber_installation", "Fiber Installation"
        ROUTER = "router_setup", "Router Setup"
        EXTENDER = "wifi_extender", "Wi-Fi Extender"
        MIKROTIK = "mikrotik_voucher", "Mikrotik Voucher"
        ACCESS_POINT = "access_point", "Access Point"
        ONU = "fiber_onu_ont", "Fiber ONU/ONT"
        UPS = "power_backup", "Power Backup"
        SUPPORT = "support", "Support"

    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name="jobs")
    job_number = models.CharField(max_length=12, unique=True, editable=False)
    title = models.CharField(max_length=160)
    customer_name = models.CharField(max_length=120)
    location = models.CharField(max_length=120, blank=True)
    category = models.CharField(max_length=32, choices=Category.choices, default=Category.ROUTER)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.NOT_STARTED)
    priority = models.CharField(max_length=8, choices=Priority.choices, default=Priority.MEDIUM)
    assigned_to = models.ForeignKey(
        Technician, on_delete=models.SET_NULL, null=True, blank=True, related_name="jobs"
    )
    start_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.job_number} · {self.title}"

    def save(self, *args, **kwargs):
        if not self.job_number:
            last = InstallationJob.objects.order_by("-id").first()
            next_id = (last.id + 1) if last else 1
            self.job_number = f"{next_id:03d}"
        super().save(*args, **kwargs)


class TodoItem(models.Model):
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    assigned_to = models.ForeignKey(
        Technician, on_delete=models.SET_NULL, null=True, blank=True, related_name="todos"
    )
    done = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["done", "due_date"]

    def __str__(self):
        return self.title


class Supplier(models.Model):
    name = models.CharField(max_length=120)
    contact_person = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Category(models.Model):
    """A stock/purchase category, managed by staff rather than hard-coded."""

    name = models.CharField(max_length=80, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Product(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name="products")
    name = models.CharField(max_length=160)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="products")
    unit = models.CharField(max_length=20, default="pcs", help_text="e.g. pcs, box, meter")
    quantity_on_hand = models.IntegerField(default=0)
    reorder_level = models.PositiveIntegerField(default=0, help_text="Flag as low stock at or below this quantity")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def is_out_of_stock(self):
        return self.quantity_on_hand <= 0

    @property
    def is_low_stock(self):
        return self.quantity_on_hand <= self.reorder_level


class StockMovement(models.Model):
    class Reason(models.TextChoices):
        PURCHASE = "purchase", "Stock Received"
        SALE = "sale", "Stock Sold"
        ADJUSTMENT = "adjustment", "Manual Adjustment"

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="movements")
    change = models.IntegerField(help_text="Positive = stock in, negative = stock out")
    reason = models.CharField(max_length=12, choices=Reason.choices)
    reference = models.CharField(max_length=20, blank=True, help_text="PO/invoice number, if applicable")
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.product.name} {self.change:+d} ({self.reason})"


def _apply_stock_change(product_id, change, reason, reference="", note=""):
    if not product_id or not change:
        return
    Product.objects.filter(pk=product_id).update(quantity_on_hand=F("quantity_on_hand") + change)
    StockMovement.objects.create(product_id=product_id, change=change, reason=reason, reference=reference, note=note)


class Purchase(models.Model):
    class Status(models.TextChoices):
        ORDERED = "ordered", "Ordered"
        RECEIVED = "received", "Received"
        CANCELLED = "cancelled", "Cancelled"

    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name="purchases")
    po_number = models.CharField(max_length=12, unique=True, editable=False)
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name="purchases")
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, related_name="purchases")
    item_name = models.CharField(max_length=160)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="purchases")
    quantity = models.PositiveIntegerField(default=1)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ORDERED)
    purchase_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-purchase_date", "-created_at"]

    def __str__(self):
        return f"{self.po_number} · {self.item_name}"

    @property
    def total_cost(self):
        return self.unit_cost * self.quantity

    def save(self, *args, **kwargs):
        if not self.po_number:
            last = Purchase.objects.order_by("-id").first()
            next_id = (last.id + 1) if last else 1
            self.po_number = f"PO-{next_id:04d}"

        previous = Purchase.objects.filter(pk=self.pk).first() if self.pk else None
        old_product_id = previous.product_id if previous else None
        old_contribution = (
            previous.quantity if (previous and previous.product_id and previous.status == Purchase.Status.RECEIVED) else 0
        )

        super().save(*args, **kwargs)

        new_contribution = self.quantity if (self.product_id and self.status == Purchase.Status.RECEIVED) else 0

        if old_product_id and old_product_id != self.product_id:
            _apply_stock_change(
                old_product_id, -old_contribution, StockMovement.Reason.PURCHASE,
                reference=self.po_number, note="Purchase relinked to a different product",
            )
            _apply_stock_change(self.product_id, new_contribution, StockMovement.Reason.PURCHASE, reference=self.po_number)
        else:
            delta = new_contribution - old_contribution
            _apply_stock_change(self.product_id, delta, StockMovement.Reason.PURCHASE, reference=self.po_number)

    def delete(self, *args, **kwargs):
        contribution = self.quantity if (self.product_id and self.status == Purchase.Status.RECEIVED) else 0
        product_id = self.product_id
        po_number = self.po_number
        super().delete(*args, **kwargs)
        _apply_stock_change(product_id, -contribution, StockMovement.Reason.PURCHASE, reference=po_number, note="Purchase deleted")


class Expense(models.Model):
    class Category(models.TextChoices):
        FUEL_TRANSPORT = "fuel_transport", "Fuel & Transport"
        RENT = "rent", "Rent"
        UTILITIES = "utilities", "Utilities"
        MARKETING = "marketing", "Marketing"
        MAINTENANCE = "maintenance", "Equipment Maintenance"
        OFFICE_SUPPLIES = "office_supplies", "Office Supplies"
        OTHER = "other", "Other"

    class PaymentMethod(models.TextChoices):
        CASH = "cash", "Cash"
        MOBILE_MONEY = "mobile_money", "Mobile Money"
        BANK_TRANSFER = "bank_transfer", "Bank Transfer"
        CARD = "card", "Card"

    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name="expenses")
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER)
    description = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    expense_date = models.DateField()
    payment_method = models.CharField(max_length=16, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    recorded_by = models.ForeignKey(
        Technician, on_delete=models.SET_NULL, null=True, blank=True, related_name="expenses"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-expense_date", "-created_at"]

    def __str__(self):
        return f"{self.description} — {self.amount}"


class Sale(models.Model):
    class PaymentStatus(models.TextChoices):
        UNPAID = "unpaid", "Unpaid"
        PARTIAL = "partial", "Partially Paid"
        PAID = "paid", "Paid"

    class Category(models.TextChoices):
        FIBER = "fiber_installation", "Fiber Installation"
        ROUTER = "router_setup", "Router Setup"
        EXTENDER = "wifi_extender", "Wi-Fi Extender"
        MIKROTIK = "mikrotik_voucher", "Mikrotik Voucher"
        ACCESS_POINT = "access_point", "Access Point"
        ONU = "fiber_onu_ont", "Fiber ONU/ONT"
        UPS = "power_backup", "Power Backup (UPS)"
        SUPPORT = "support", "Support"
        PRODUCT = "product_sale", "Product Sale"
        OTHER = "other", "Other"

    class PaymentMethod(models.TextChoices):
        CASH = "cash", "Cash"
        MOBILE_MONEY = "mobile_money", "Mobile Money"
        BANK_TRANSFER = "bank_transfer", "Bank Transfer"
        CARD = "card", "Card"

    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name="sales")
    invoice_number = models.CharField(max_length=12, unique=True, editable=False)
    customer_name = models.CharField(max_length=120)
    job = models.ForeignKey(
        InstallationJob, on_delete=models.SET_NULL, null=True, blank=True, related_name="sales"
    )
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, related_name="sales")
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER)
    description = models.CharField(max_length=200)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    payment_status = models.CharField(max_length=8, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID)
    payment_method = models.CharField(max_length=16, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    sale_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-sale_date", "-created_at"]

    def __str__(self):
        return f"{self.invoice_number} · {self.customer_name}"

    @property
    def amount(self):
        return self.unit_price * self.quantity

    @property
    def balance_due(self):
        return self.amount - self.amount_paid

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            last = Sale.objects.order_by("-id").first()
            next_id = (last.id + 1) if last else 1
            self.invoice_number = f"INV-{next_id:04d}"

        previous = Sale.objects.filter(pk=self.pk).first() if self.pk else None
        old_product_id = previous.product_id if previous else None
        old_contribution = previous.quantity if (previous and previous.product_id) else 0

        super().save(*args, **kwargs)

        new_contribution = self.quantity if self.product_id else 0

        if old_product_id and old_product_id != self.product_id:
            _apply_stock_change(
                old_product_id, old_contribution, StockMovement.Reason.SALE,
                reference=self.invoice_number, note="Sale relinked to a different product",
            )
            _apply_stock_change(self.product_id, -new_contribution, StockMovement.Reason.SALE, reference=self.invoice_number)
        else:
            delta = new_contribution - old_contribution
            _apply_stock_change(self.product_id, -delta, StockMovement.Reason.SALE, reference=self.invoice_number)

    def delete(self, *args, **kwargs):
        contribution = self.quantity if self.product_id else 0
        product_id = self.product_id
        invoice_number = self.invoice_number
        super().delete(*args, **kwargs)
        _apply_stock_change(product_id, contribution, StockMovement.Reason.SALE, reference=invoice_number, note="Sale deleted")


class Customer(models.Model):
    class Source(models.TextChoices):
        MANUAL = "manual", "Added Manually"
        SALE = "sale", "From a Sale"
        JOB = "job", "From an Installation Job"

    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    location = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.MANUAL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


def _sync_customer(name, phone="", location="", source=Customer.Source.MANUAL):
    name = (name or "").strip()
    if not name:
        return
    customer = Customer.objects.filter(name__iexact=name).first()
    if customer is None:
        Customer.objects.create(name=name, phone=phone, location=location, source=source)
        return
    updated_fields = []
    if phone and not customer.phone:
        customer.phone = phone
        updated_fields.append("phone")
    if location and not customer.location:
        customer.location = location
        updated_fields.append("location")
    if updated_fields:
        customer.save(update_fields=updated_fields)


@receiver(post_save, sender=Sale)
def _sale_syncs_customer(sender, instance, created, **kwargs):
    if created:
        _sync_customer(instance.customer_name, source=Customer.Source.SALE)


@receiver(post_save, sender=InstallationJob)
def _job_syncs_customer(sender, instance, created, **kwargs):
    if created:
        _sync_customer(instance.customer_name, location=instance.location, source=Customer.Source.JOB)
