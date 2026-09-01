from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from . import auth_views, views

router = DefaultRouter()
router.register("accounts", views.UserViewSet)
router.register("roles", views.RoleViewSet)
router.register("technicians", views.TechnicianViewSet)
router.register("leads", views.LeadViewSet)
router.register("jobs", views.InstallationJobViewSet)
router.register("todos", views.TodoItemViewSet)
router.register("payslips", views.PayslipViewSet)
router.register("suppliers", views.SupplierViewSet)
router.register("purchases", views.PurchaseViewSet)
router.register("expenses", views.ExpenseViewSet)
router.register("sales", views.SaleViewSet)
router.register("customers", views.CustomerViewSet)
router.register("products", views.ProductViewSet)
router.register("categories", views.CategoryViewSet)
router.register("branches", views.BranchViewSet)
router.register("audit-log", views.AuditLogViewSet)

urlpatterns = [
    path("auth/login/", auth_views.LoginView.as_view(), name="auth-login"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="auth-refresh"),
    path("auth/me/", auth_views.me, name="auth-me"),
    path("auth/logout/", auth_views.logout, name="auth-logout"),
    path("dashboard/summary/", views.dashboard_summary, name="dashboard-summary"),
    path("dashboard/trends/", views.dashboard_trends, name="dashboard-trends"),
    path("users/summary/", views.users_summary, name="users-summary"),
    path("payroll/summary/", views.payroll_summary, name="payroll-summary"),
    path("purchases/summary/", views.purchases_summary, name="purchases-summary"),
    path("expenses/summary/", views.expenses_summary, name="expenses-summary"),
    path("sales/summary/", views.sales_summary, name="sales-summary"),
    path("finance/summary/", views.finance_summary, name="finance-summary"),
    path("leads/summary/", views.leads_summary, name="leads-summary"),
    path("jobs/summary/", views.jobs_summary, name="jobs-summary"),
    path("customers/summary/", views.customers_summary, name="customers-summary"),
    path("inventory/summary/", views.inventory_summary, name="inventory-summary"),
] + router.urls
