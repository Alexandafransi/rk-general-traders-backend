from datetime import date

from django.db.models import Count, F, Q, Sum
from django.utils import timezone
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from accounts.models import Role, User

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
from .permissions import (
    BranchReadPermission,
    IsAdminOrSuperAdmin,
    IsSuperAdmin,
    ModulePermission,
    ReadOpenModulePermission,
    RoleReadPermission,
    assignable_roles_for,
    can_access_module,
)
from .serializers import (
    AuditLogSerializer,
    BranchSerializer,
    CategorySerializer,
    CustomerSerializer,
    ExpenseSerializer,
    InstallationJobSerializer,
    LeadSerializer,
    PayslipSerializer,
    PaymentMethodSerializer,
    ProductSerializer,
    PurchaseSerializer,
    RoleSerializer,
    SaleSerializer,
    StockMovementSerializer,
    SupplierSerializer,
    TechnicianSerializer,
    TodoItemSerializer,
    UserSerializer,
    UserWriteSerializer,
    role_display_for,
)


class AuditMixin:
    """Silently records who did what and when for every mutation on this
    viewset — invisible to the acting user and everyone except superadmin,
    who reads it back via AuditLogViewSet. Set `audit_label` to override the
    default (the model's class name) when a friendlier name reads better."""

    audit_label = None

    def _record(self, action, instance):
        user = self.request.user if self.request.user.is_authenticated else None
        AuditLog.objects.create(
            actor=user,
            actor_username=user.username if user else "",
            action=action,
            model_name=self.audit_label or instance.__class__.__name__,
            object_id=str(instance.pk),
            object_repr=str(instance)[:200],
            branch=getattr(instance, "branch", None),
        )

    def perform_create(self, serializer):
        # chain via super() rather than calling serializer.save() directly,
        # so BranchFilteredMixin's own-branch auto-assignment (when present
        # earlier in the MRO) actually runs before we log the result
        super().perform_create(serializer)
        self._record(AuditLog.Action.CREATE, serializer.instance)

    def perform_update(self, serializer):
        super().perform_update(serializer)
        self._record(AuditLog.Action.UPDATE, serializer.instance)

    def perform_destroy(self, instance):
        self._record(AuditLog.Action.DELETE, instance)
        super().perform_destroy(instance)


def _month_start(d, months_back):
    month = d.month - months_back
    year = d.year
    while month <= 0:
        month += 12
        year -= 1
    return d.replace(year=year, month=month, day=1)


def _branch_param(request):
    """The effective branch id to filter by, or None for the all-branches aggregate view.

    Superadmin/admin may pick any branch (or "all") via `?branch=`. Every other
    role is locked to the branch they were registered under, regardless of
    what the query string asks for — they never see another shop's data.
    """
    user = getattr(request, "user", None)
    if user and user.is_authenticated and user.role not in ("superadmin", "admin"):
        # "0" never matches a real branch (ids start at 1), so this correctly
        # yields zero rows everywhere without crashing filter(branch_id=...)
        # calls the way a non-numeric sentinel like "__none__" would.
        return str(user.branch_id) if user.branch_id else "0"
    branch = request.query_params.get("branch")
    if not branch or branch == "all":
        return None
    return branch


def _own_branch_kwargs(request):
    """kwargs that force a new/edited record onto the caller's own branch.
    Non-admin roles never choose a branch — they only ever work within the
    one they were registered under — so their own branch is applied
    automatically instead of trusting (or even offering) a branch field in
    the request. Admin/superadmin pass through untouched: {} changes nothing,
    leaving whatever branch they submitted (or none)."""
    user = request.user
    if user.is_authenticated and user.role not in ("superadmin", "admin") and user.branch_id:
        return {"branch_id": user.branch_id}
    return {}


class BranchFilteredMixin:
    """Applies `?branch=<id>` filtering to a ViewSet's list/detail queryset,
    and auto-assigns the caller's own branch on create/update for non-admin
    roles (see `_own_branch_kwargs`)."""

    def get_queryset(self):
        queryset = super().get_queryset()
        branch_id = _branch_param(self.request)
        if branch_id:
            queryset = queryset.filter(branch_id=branch_id)
        return queryset

    def perform_create(self, serializer):
        serializer.save(**_own_branch_kwargs(self.request))

    def perform_update(self, serializer):
        serializer.save(**_own_branch_kwargs(self.request))


class BranchViewSet(AuditMixin, ModelViewSet):
    queryset = Branch.objects.all()
    serializer_class = BranchSerializer
    permission_classes = [BranchReadPermission]


class TechnicianViewSet(AuditMixin, ModelViewSet):
    audit_label = "Technician"
    queryset = Technician.objects.all()
    serializer_class = TechnicianSerializer
    permission_classes = [ReadOpenModulePermission("staff")]


class UserViewSet(AuditMixin, ModelViewSet):
    """Admin/superadmin manage login accounts here: registration, role, and
    branch assignment. Only superadmin may create or edit admin/superadmin
    accounts, so an admin can't escalate their own privileges."""

    audit_label = "Account"
    queryset = User.objects.select_related("branch").all()
    permission_classes = [IsAdminOrSuperAdmin]

    def get_serializer_class(self):
        if self.action in ("list", "retrieve"):
            return UserSerializer
        return UserWriteSerializer

    def _check_role_assignment(self, requested_role):
        allowed = assignable_roles_for(self.request.user)
        if requested_role not in allowed:
            raise PermissionDenied("You aren't allowed to assign that role.")

    def perform_create(self, serializer):
        self._check_role_assignment(serializer.validated_data.get("role", "sales"))
        instance = serializer.save()
        self._record(AuditLog.Action.CREATE, instance)

    def perform_update(self, serializer):
        new_role = serializer.validated_data.get("role", serializer.instance.role)
        if new_role != serializer.instance.role or serializer.instance.role in ("admin", "superadmin"):
            self._check_role_assignment(new_role)
        instance = serializer.save()
        self._record(AuditLog.Action.UPDATE, instance)

    def perform_destroy(self, instance):
        if instance.pk == self.request.user.pk:
            raise PermissionDenied("You can't delete your own account.")
        self._record(AuditLog.Action.DELETE, instance)
        instance.delete()


class RoleViewSet(AuditMixin, ModelViewSet):
    """Dynamic access levels (Manager, Accountant, Sales, or custom ones a
    superadmin adds). Reads are open to any authenticated account — they
    power the Accounts role picker and each account's own permission
    checks — but only superadmin may create, edit, or delete a role."""

    audit_label = "Role"
    queryset = Role.objects.all()
    serializer_class = RoleSerializer
    permission_classes = [RoleReadPermission]

    def perform_destroy(self, instance):
        in_use = User.objects.filter(role=instance.key).exists() or Technician.objects.filter(access_role=instance.key).exists()
        if in_use:
            raise PermissionDenied("This role is still assigned to one or more accounts or staff records and can't be deleted.")
        self._record(AuditLog.Action.DELETE, instance)
        instance.delete()


class LeadViewSet(AuditMixin, BranchFilteredMixin, ModelViewSet):
    queryset = Lead.objects.select_related("branch").all()
    serializer_class = LeadSerializer
    permission_classes = [ModulePermission("leads")]


class InstallationJobViewSet(AuditMixin, BranchFilteredMixin, ModelViewSet):
    audit_label = "Job"
    queryset = InstallationJob.objects.select_related("assigned_to", "branch").all()
    serializer_class = InstallationJobSerializer
    permission_classes = [ModulePermission("jobs")]


class TodoItemViewSet(AuditMixin, ModelViewSet):
    audit_label = "Todo"
    queryset = TodoItem.objects.select_related("assigned_to").all()
    serializer_class = TodoItemSerializer
    permission_classes = [ModulePermission("jobs")]


class PayslipViewSet(AuditMixin, ModelViewSet):
    audit_label = "Payslip"
    queryset = Payslip.objects.select_related("technician").all()
    serializer_class = PayslipSerializer
    permission_classes = [ModulePermission("payroll")]

    @action(detail=False, methods=["post"])
    def bulk_generate(self, request):
        """Record a payment run for a period: either every active staff
        member, or a specific chosen set. Skips anyone who already has a
        payslip for that period rather than erroring out."""
        period_str = request.data.get("period")
        try:
            period = date.fromisoformat(period_str).replace(day=1)
        except (TypeError, ValueError):
            return Response({"detail": "period must be an ISO date (e.g. 2026-08-01)."}, status=400)

        technician_ids = request.data.get("technician_ids")
        technicians = Technician.objects.filter(active=True)
        if technician_ids:
            technicians = technicians.filter(pk__in=technician_ids)

        created, skipped = [], []
        for tech in technicians:
            if Payslip.objects.filter(technician=tech, period=period).exists():
                skipped.append(tech.name)
                continue
            payslip = Payslip.objects.create(
                technician=tech, period=period, base_salary=tech.monthly_salary,
                allowances=0, deductions=0, status=Payslip.Status.DRAFT,
            )
            self._record(AuditLog.Action.CREATE, payslip)
            created.append(payslip)

        return Response(
            {
                "created_count": len(created),
                "skipped_count": len(skipped),
                "skipped_names": skipped,
                "payslips": PayslipSerializer(created, many=True).data,
            }
        )


class SupplierViewSet(AuditMixin, ModelViewSet):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    permission_classes = [ReadOpenModulePermission("suppliers")]


class PurchaseViewSet(AuditMixin, BranchFilteredMixin, ModelViewSet):
    queryset = Purchase.objects.select_related("supplier", "product", "category", "branch", "payment_method").all()
    serializer_class = PurchaseSerializer
    permission_classes = [ModulePermission("purchases")]


class CategoryViewSet(AuditMixin, ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [ReadOpenModulePermission("categories")]


class PaymentMethodViewSet(AuditMixin, ModelViewSet):
    audit_label = "Payment Method"
    queryset = PaymentMethod.objects.all()
    serializer_class = PaymentMethodSerializer
    permission_classes = [ReadOpenModulePermission("payment_methods")]


class ExpenseViewSet(AuditMixin, BranchFilteredMixin, ModelViewSet):
    queryset = Expense.objects.select_related("recorded_by", "branch", "payment_method").all()
    serializer_class = ExpenseSerializer
    permission_classes = [ModulePermission("expenses")]


class SaleViewSet(AuditMixin, BranchFilteredMixin, ModelViewSet):
    queryset = Sale.objects.select_related("job", "product", "branch", "payment_method").all()
    serializer_class = SaleSerializer
    permission_classes = [ModulePermission("sales")]


class ProductViewSet(AuditMixin, BranchFilteredMixin, ModelViewSet):
    queryset = Product.objects.select_related("category", "branch").all()
    serializer_class = ProductSerializer
    permission_classes = [ReadOpenModulePermission("inventory")]

    def perform_create(self, serializer):
        product = serializer.save(**_own_branch_kwargs(self.request))
        if product.quantity_on_hand:
            StockMovement.objects.create(
                product=product,
                change=product.quantity_on_hand,
                reason=StockMovement.Reason.ADJUSTMENT,
                note="Initial stock",
            )
        self._record(AuditLog.Action.CREATE, product)

    def perform_update(self, serializer):
        # quantity_on_hand only ever moves through purchases, sales, or the adjust action below —
        # never directly through an edit form — so pin it back to its current value on every update.
        product = serializer.save(quantity_on_hand=serializer.instance.quantity_on_hand, **_own_branch_kwargs(self.request))
        self._record(AuditLog.Action.UPDATE, product)

    @action(detail=True, methods=["post"])
    def adjust(self, request, pk=None):
        product = self.get_object()
        try:
            delta = int(request.data.get("delta"))
        except (TypeError, ValueError):
            return Response({"detail": "delta must be an integer."}, status=400)
        if delta == 0:
            return Response({"detail": "delta must be non-zero."}, status=400)
        note = (request.data.get("note") or "").strip()
        Product.objects.filter(pk=product.pk).update(quantity_on_hand=F("quantity_on_hand") + delta)
        StockMovement.objects.create(product=product, change=delta, reason=StockMovement.Reason.ADJUSTMENT, note=note)
        product.refresh_from_db()
        self._record(AuditLog.Action.UPDATE, product)
        return Response(ProductSerializer(product).data)


class CustomerViewSet(AuditMixin, ModelViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = [ModulePermission("customers")]


class AuditLogViewSet(ReadOnlyModelViewSet):
    """Superadmin-only read access to the full audit trail. Nobody else can
    see this exists — not even Admin — since the whole point is that regular
    users, including Admins, never know their actions are being recorded."""

    queryset = AuditLog.objects.select_related("branch").all()
    serializer_class = AuditLogSerializer
    permission_classes = [IsSuperAdmin]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if actor := params.get("actor"):
            qs = qs.filter(actor_username__icontains=actor)
        if model_name := params.get("model"):
            qs = qs.filter(model_name=model_name)
        if action := params.get("action"):
            qs = qs.filter(action=action)
        if branch_id := params.get("branch"):
            qs = qs.filter(branch_id=branch_id)
        return qs


JOB_STATUS_LABELS = dict(InstallationJob.Status.choices)


@api_view(["GET"])
@permission_classes([ModulePermission("dashboard")])
def dashboard_summary(request):
    can_leads = can_access_module(request.user, "leads")
    can_jobs = can_access_module(request.user, "jobs")

    branch_id = _branch_param(request)
    leads = Lead.objects.all()
    jobs = InstallationJob.objects.all()
    if branch_id:
        leads = leads.filter(branch_id=branch_id)
        jobs = jobs.filter(branch_id=branch_id)

    total_leads = leads.count()
    converted_leads = leads.filter(status=Lead.Status.CONVERTED).count()
    lost_leads = leads.filter(status=Lead.Status.LOST).count()
    open_leads = total_leads - converted_leads - lost_leads

    active_jobs = jobs.filter(
        status__in=[InstallationJob.Status.IN_PROGRESS, InstallationJob.Status.REVIEW]
    ).count()
    total_jobs = jobs.count()
    unfinished_jobs = jobs.exclude(
        status__in=[InstallationJob.Status.DONE, InstallationJob.Status.CANCELLED]
    ).count()

    conversion_base = converted_leads + lost_leads
    conversion_rate = round((converted_leads / conversion_base) * 100) if conversion_base else 0

    status_counts = jobs.values("status").annotate(count=Count("id")).order_by("status")
    job_status_breakdown = [
        {"status": row["status"], "label": JOB_STATUS_LABELS.get(row["status"], row["status"]), "count": row["count"]}
        for row in status_counts
    ]

    recent_jobs = jobs.select_related("assigned_to").order_by("-created_at")[:6] if can_jobs else []
    todos = (
        TodoItem.objects.select_related("assigned_to").order_by("done", "due_date")[:6] if can_jobs else []
    )

    return Response(
        {
            "access": {"leads": can_leads, "jobs": can_jobs},
            "kpis": {
                "converted_leads": converted_leads if can_leads else 0,
                "converted_leads_pct": (round((converted_leads / total_leads) * 100) if total_leads else 0) if can_leads else 0,
                "active_jobs": active_jobs if can_jobs else 0,
                "total_jobs": total_jobs if can_jobs else 0,
                "unfinished_jobs": unfinished_jobs if can_jobs else 0,
                "unfinished_jobs_pct": (round((unfinished_jobs / total_jobs) * 100) if total_jobs else 0) if can_jobs else 0,
            },
            "lead_conversion": {
                "converted": converted_leads,
                "lost": lost_leads,
                "open": max(open_leads, 0),
                "conversion_rate": conversion_rate,
            }
            if can_leads
            else None,
            "job_status_breakdown": job_status_breakdown if can_jobs else [],
            "recent_jobs": InstallationJobSerializer(recent_jobs, many=True).data,
            "todos": TodoItemSerializer(todos, many=True).data,
        }
    )


@api_view(["GET"])
@permission_classes([ModulePermission("dashboard")])
def dashboard_trends(request):
    """Month-by-month comparison of the business's own money-moving activity:
    what came in from sales vs. what went out on purchases, expenses and payroll.
    This is financial data, so it's withheld from any role without finance access,
    even though the dashboard page itself only requires the 'dashboard' module."""
    if not can_access_module(request.user, "finance"):
        return Response({"months": 0, "series": [], "access": False})

    try:
        months = int(request.query_params.get("months", 6))
    except (TypeError, ValueError):
        months = 6
    months = max(1, min(months, 24))
    branch_id = _branch_param(request)

    today = timezone.localdate()
    series = []
    for i in range(months - 1, -1, -1):
        start = _month_start(today, i)
        end = _month_start(today, i - 1) if i > 0 else _month_start(today, -1)

        sales_qs = Sale.objects.filter(sale_date__gte=start, sale_date__lt=end)
        purchases_qs = Purchase.objects.filter(
            purchase_date__gte=start, purchase_date__lt=end
        ).exclude(status=Purchase.Status.CANCELLED)
        expenses_qs = Expense.objects.filter(expense_date__gte=start, expense_date__lt=end)
        if branch_id:
            sales_qs = sales_qs.filter(branch_id=branch_id)
            purchases_qs = purchases_qs.filter(branch_id=branch_id)
            expenses_qs = expenses_qs.filter(branch_id=branch_id)

        sales_total = sum((s.amount for s in sales_qs), start=0)
        purchases_total = sum((p.total_cost for p in purchases_qs), start=0)
        expenses_total = expenses_qs.aggregate(total=Sum("amount"))["total"] or 0
        payroll_total = sum(
            (p.net_pay for p in Payslip.objects.filter(period=start)), start=0
        )
        costs = purchases_total + expenses_total + payroll_total

        series.append(
            {
                "month": start,
                "sales": str(sales_total),
                "purchases": str(purchases_total),
                "expenses": str(expenses_total),
                "payroll": str(payroll_total),
                "profit": str(sales_total - costs),
            }
        )

    return Response({"months": months, "series": series, "access": True})


LEAD_STATUS_LABELS = dict(Lead.Status.choices)
LEAD_SOURCE_LABELS = dict(Lead.Source.choices)


@api_view(["GET"])
@permission_classes([ModulePermission("leads")])
def leads_summary(request):
    leads = Lead.objects.select_related("branch").all()
    branch_id = _branch_param(request)
    if branch_id:
        leads = leads.filter(branch_id=branch_id)
    total = leads.count()
    converted = leads.filter(status=Lead.Status.CONVERTED).count()
    lost = leads.filter(status=Lead.Status.LOST).count()
    open_leads = total - converted - lost
    conversion_base = converted + lost
    conversion_rate = round((converted / conversion_base) * 100) if conversion_base else 0

    today = timezone.localdate()
    month_start = today.replace(day=1)
    new_this_month = leads.filter(created_at__gte=month_start).count()

    status_counts = leads.values("status").annotate(count=Count("id")).order_by("status")
    status_breakdown = [
        {"status": row["status"], "label": LEAD_STATUS_LABELS.get(row["status"], row["status"]), "count": row["count"]}
        for row in status_counts
    ]

    source_rows = (
        leads.values("source")
        .annotate(count=Count("id"), converted=Count("id", filter=Q(status=Lead.Status.CONVERTED)))
        .order_by("-count")
    )
    source_breakdown = [
        {
            "source": row["source"],
            "label": LEAD_SOURCE_LABELS.get(row["source"], row["source"]),
            "count": row["count"],
            "converted": row["converted"],
        }
        for row in source_rows
    ]

    return Response(
        {
            "kpis": {
                "total_leads": total,
                "new_this_month": new_this_month,
                "open_leads": max(open_leads, 0),
                "conversion_rate": conversion_rate,
            },
            "status_breakdown": status_breakdown,
            "source_breakdown": source_breakdown,
            "leads": LeadSerializer(leads.order_by("-created_at"), many=True).data,
        }
    )


JOB_CATEGORY_LABELS = dict(InstallationJob.Category.choices)


@api_view(["GET"])
@permission_classes([ModulePermission("jobs")])
def jobs_summary(request):
    jobs = InstallationJob.objects.select_related("assigned_to", "branch").all()
    branch_id = _branch_param(request)
    if branch_id:
        jobs = jobs.filter(branch_id=branch_id)
    total = jobs.count()
    active = jobs.filter(
        status__in=[InstallationJob.Status.IN_PROGRESS, InstallationJob.Status.REVIEW]
    ).count()

    today = timezone.localdate()
    month_start = today.replace(day=1)
    done_this_month = jobs.filter(status=InstallationJob.Status.DONE, start_date__gte=month_start).count()
    unassigned_jobs = jobs.filter(assigned_to__isnull=True).exclude(
        status__in=[InstallationJob.Status.DONE, InstallationJob.Status.CANCELLED]
    ).count()

    status_counts = jobs.values("status").annotate(count=Count("id")).order_by("status")
    status_breakdown = [
        {"status": row["status"], "label": JOB_STATUS_LABELS.get(row["status"], row["status"]), "count": row["count"]}
        for row in status_counts
    ]

    technician_rows = (
        jobs.filter(status=InstallationJob.Status.DONE, assigned_to__isnull=False)
        .values("assigned_to__id", "assigned_to__name", "assigned_to__tint")
        .annotate(jobs_completed=Count("id"))
        .order_by("-jobs_completed")
    )
    by_technician = [
        {
            "technician_id": row["assigned_to__id"],
            "name": row["assigned_to__name"],
            "tint": row["assigned_to__tint"],
            "jobs_completed": row["jobs_completed"],
        }
        for row in technician_rows
    ]

    return Response(
        {
            "kpis": {
                "total_jobs": total,
                "active_jobs": active,
                "done_this_month": done_this_month,
                "unassigned_jobs": unassigned_jobs,
            },
            "status_breakdown": status_breakdown,
            "by_technician": by_technician,
            "jobs": InstallationJobSerializer(jobs.order_by("-created_at"), many=True).data,
        }
    )


@api_view(["GET"])
@permission_classes([ModulePermission("staff")])
def users_summary(request):
    technicians = Technician.objects.select_related("account").all()
    total = technicians.count()
    active = technicians.filter(active=True).count()

    role_counts = technicians.values("access_role").annotate(count=Count("id")).order_by("access_role")
    role_breakdown = [
        {"role": row["access_role"], "label": role_display_for(row["access_role"]) or "—", "count": row["count"]}
        for row in role_counts
    ]

    return Response(
        {
            "kpis": {
                "total_users": total,
                "active_users": active,
                "inactive_users": total - active,
                "with_login": technicians.filter(account__isnull=False).count(),
            },
            "role_breakdown": role_breakdown,
            "users": TechnicianSerializer(technicians, many=True).data,
        }
    )


@api_view(["GET"])
@permission_classes([ModulePermission("payroll")])
def payroll_summary(request):
    latest_period = Payslip.objects.order_by("-period").values_list("period", flat=True).first()

    this_month_qs = Payslip.objects.filter(period=latest_period) if latest_period else Payslip.objects.none()
    total_this_month = sum((p.net_pay for p in this_month_qs), start=0)
    paid_this_month = this_month_qs.filter(status=Payslip.Status.PAID).count()
    pending_this_month = this_month_qs.filter(status=Payslip.Status.DRAFT).count()

    all_time_paid = Payslip.objects.filter(status=Payslip.Status.PAID).aggregate(
        total=Sum("base_salary")
    )["total"] or 0

    payslips = Payslip.objects.select_related("technician").order_by("-period", "technician__name")

    return Response(
        {
            "kpis": {
                "total_this_month": str(total_this_month),
                "paid_this_month": paid_this_month,
                "pending_this_month": pending_this_month,
                "staff_on_payroll": Technician.objects.filter(active=True).count(),
                "all_time_paid": str(all_time_paid),
            },
            "latest_period": latest_period,
            "payslips": PayslipSerializer(payslips, many=True).data,
        }
    )


EXPENSE_CATEGORY_LABELS = dict(Expense.Category.choices)


@api_view(["GET"])
@permission_classes([ModulePermission("purchases")])
def purchases_summary(request):
    today = timezone.localdate()
    month_start = today.replace(day=1)

    purchases = Purchase.objects.select_related("supplier", "product", "category", "branch", "payment_method").all()
    branch_id = _branch_param(request)
    if branch_id:
        purchases = purchases.filter(branch_id=branch_id)
    this_month = purchases.filter(purchase_date__gte=month_start)
    this_month_not_cancelled = this_month.exclude(status=Purchase.Status.CANCELLED)

    total_spend_this_month = sum((p.total_cost for p in this_month_not_cancelled), start=0)
    pending_count = purchases.filter(status=Purchase.Status.ORDERED).count()
    received_this_month = this_month.filter(status=Purchase.Status.RECEIVED).count()

    return Response(
        {
            "kpis": {
                "total_spend_this_month": str(total_spend_this_month),
                "pending_orders": pending_count,
                "received_this_month": received_this_month,
                "total_purchases": purchases.count(),
            },
            "purchases": PurchaseSerializer(purchases, many=True).data,
        }
    )


@api_view(["GET"])
@permission_classes([ModulePermission("expenses")])
def expenses_summary(request):
    today = timezone.localdate()
    month_start = today.replace(day=1)

    expenses = Expense.objects.select_related("recorded_by", "branch", "payment_method").all()
    branch_id = _branch_param(request)
    if branch_id:
        expenses = expenses.filter(branch_id=branch_id)
    this_month = expenses.filter(expense_date__gte=month_start)
    total_this_month = this_month.aggregate(total=Sum("amount"))["total"] or 0

    category_counts = (
        this_month.values("category").annotate(total=Sum("amount")).order_by("-total")
    )
    category_breakdown = [
        {"category": row["category"], "label": EXPENSE_CATEGORY_LABELS.get(row["category"], row["category"]), "total": str(row["total"])}
        for row in category_counts
    ]

    return Response(
        {
            "kpis": {
                "total_this_month": str(total_this_month),
                "count_this_month": this_month.count(),
                "total_expenses": expenses.count(),
            },
            "category_breakdown": category_breakdown,
            "expenses": ExpenseSerializer(expenses, many=True).data,
        }
    )


SALE_CATEGORY_LABELS = dict(Sale.Category.choices)


@api_view(["GET"])
@permission_classes([ModulePermission("sales")])
def sales_summary(request):
    today = timezone.localdate()
    month_start = today.replace(day=1)

    sales = Sale.objects.select_related("job", "product", "branch", "payment_method").all()
    branch_id = _branch_param(request)
    if branch_id:
        sales = sales.filter(branch_id=branch_id)
    this_month = sales.filter(sale_date__gte=month_start)

    revenue_this_month = sum((s.amount for s in this_month), start=0)
    collected_this_month = this_month.aggregate(total=Sum("amount_paid"))["total"] or 0
    outstanding_balance = sum(
        (s.balance_due for s in sales.exclude(payment_status=Sale.PaymentStatus.PAID)), start=0
    )

    category_counts = {}
    for s in this_month:
        category_counts[s.category] = category_counts.get(s.category, 0) + s.amount
    category_breakdown = [
        {"category": cat, "label": SALE_CATEGORY_LABELS.get(cat, cat), "total": str(total)}
        for cat, total in sorted(category_counts.items(), key=lambda kv: kv[1], reverse=True)
    ]

    return Response(
        {
            "kpis": {
                "revenue_this_month": str(revenue_this_month),
                "collected_this_month": str(collected_this_month),
                "outstanding_balance": str(outstanding_balance),
                "count_this_month": this_month.count(),
            },
            "category_breakdown": category_breakdown,
            "sales": SaleSerializer(sales, many=True).data,
        }
    )


@api_view(["GET"])
@permission_classes([ModulePermission("finance")])
def finance_summary(request):
    today = timezone.localdate()
    month_start = today.replace(day=1)
    branch_id = _branch_param(request)

    payroll_qs = Payslip.objects.filter(period=month_start)
    payroll_total = sum((p.net_pay for p in payroll_qs), start=0)

    purchases_qs = Purchase.objects.filter(purchase_date__gte=month_start).exclude(status=Purchase.Status.CANCELLED)
    expenses_qs = Expense.objects.filter(expense_date__gte=month_start)
    sales_qs = Sale.objects.filter(sale_date__gte=month_start)
    if branch_id:
        purchases_qs = purchases_qs.filter(branch_id=branch_id)
        expenses_qs = expenses_qs.filter(branch_id=branch_id)
        sales_qs = sales_qs.filter(branch_id=branch_id)

    purchases_total = sum((p.total_cost for p in purchases_qs), start=0)
    expenses_total = expenses_qs.aggregate(total=Sum("amount"))["total"] or 0
    revenue_total = sum((s.amount for s in sales_qs), start=0)

    total_costs = payroll_total + purchases_total + expenses_total
    net_profit = revenue_total - total_costs

    recent_purchases_qs = Purchase.objects.select_related("supplier", "payment_method")
    recent_expenses_qs = Expense.objects.select_related("recorded_by", "payment_method")
    recent_sales_qs = Sale.objects.select_related("job", "payment_method")
    if branch_id:
        recent_purchases_qs = recent_purchases_qs.filter(branch_id=branch_id)
        recent_expenses_qs = recent_expenses_qs.filter(branch_id=branch_id)
        recent_sales_qs = recent_sales_qs.filter(branch_id=branch_id)
    recent_purchases = recent_purchases_qs.order_by("-purchase_date", "-created_at")[:5]
    recent_expenses = recent_expenses_qs.order_by("-expense_date", "-created_at")[:5]
    recent_sales = recent_sales_qs.order_by("-sale_date", "-created_at")[:5]

    return Response(
        {
            "month": month_start,
            "kpis": {
                "revenue_total": str(revenue_total),
                "total_costs": str(total_costs),
                "net_profit": str(net_profit),
                "payroll_total": str(payroll_total),
                "purchases_total": str(purchases_total),
                "expenses_total": str(expenses_total),
            },
            "breakdown": [
                {"label": "Payroll", "value": str(payroll_total)},
                {"label": "Purchases", "value": str(purchases_total)},
                {"label": "Expenses", "value": str(expenses_total)},
            ],
            "recent_purchases": PurchaseSerializer(recent_purchases, many=True).data,
            "recent_expenses": ExpenseSerializer(recent_expenses, many=True).data,
            "recent_sales": SaleSerializer(recent_sales, many=True).data,
        }
    )


@api_view(["GET"])
@permission_classes([ModulePermission("customers")])
def customers_summary(request):
    customers = Customer.objects.all().order_by("name")
    total = customers.count()

    today = timezone.localdate()
    month_start = today.replace(day=1)
    new_this_month = customers.filter(created_at__gte=month_start).count()
    manual_count = customers.filter(source=Customer.Source.MANUAL).count()

    sales_by_customer = {}
    for s in Sale.objects.all():
        key = s.customer_name.strip().lower()
        agg = sales_by_customer.setdefault(key, {"count": 0, "total_paid": 0})
        agg["count"] += 1
        agg["total_paid"] += s.amount_paid

    jobs_by_customer = {}
    for j in InstallationJob.objects.all():
        key = j.customer_name.strip().lower()
        jobs_by_customer[key] = jobs_by_customer.get(key, 0) + 1

    customer_rows = []
    for c in customers:
        key = c.name.strip().lower()
        sales_agg = sales_by_customer.get(key, {"count": 0, "total_paid": 0})
        customer_rows.append(
            {
                **CustomerSerializer(c).data,
                "sales_count": sales_agg["count"],
                "total_paid": str(sales_agg["total_paid"]),
                "jobs_count": jobs_by_customer.get(key, 0),
            }
        )

    return Response(
        {
            "kpis": {
                "total_customers": total,
                "new_this_month": new_this_month,
                "manual_count": manual_count,
                "auto_count": total - manual_count,
            },
            "customers": customer_rows,
        }
    )


@api_view(["GET"])
@permission_classes([ModulePermission("inventory")])
def inventory_summary(request):
    products_qs = Product.objects.select_related("category", "branch").all()
    movements_qs = StockMovement.objects.select_related("product")
    branch_id = _branch_param(request)
    if branch_id:
        products_qs = products_qs.filter(branch_id=branch_id)
        movements_qs = movements_qs.filter(product__branch_id=branch_id)

    products = list(products_qs)
    low_stock = [p for p in products if p.is_low_stock]
    out_of_stock = [p for p in products if p.is_out_of_stock]
    total_units = sum((p.quantity_on_hand for p in products), start=0)

    recent_movements = movements_qs.order_by("-created_at")[:30]

    return Response(
        {
            "kpis": {
                "total_products": len(products),
                "low_stock_count": len(low_stock),
                "out_of_stock_count": len(out_of_stock),
                "total_units_on_hand": total_units,
            },
            "products": ProductSerializer(products, many=True).data,
            "recent_movements": StockMovementSerializer(recent_movements, many=True).data,
        }
    )
