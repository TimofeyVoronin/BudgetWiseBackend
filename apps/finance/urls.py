from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.finance.account_views import AccountViewSet
from apps.finance.category_views import CategoryViewSet
from apps.finance.dashboard_views import DashboardSummaryView
from apps.finance.goal_views import GoalViewSet
from apps.finance.transaction_views import (
    TransactionExportView,
    TransactionViewSet,
)


app_name = "finance"

router = DefaultRouter()
router.register("accounts", AccountViewSet, basename="account")
router.register("categories", CategoryViewSet, basename="category")
router.register("goals", GoalViewSet, basename="goal")
router.register("transactions", TransactionViewSet, basename="transaction")

urlpatterns = [
    path(
        "dashboard/summary/",
        DashboardSummaryView.as_view(),
        name="dashboard-summary",
    ),
    path(
        "transactions/export/",
        TransactionExportView.as_view(),
        name="transaction-export",
    ),
    path("", include(router.urls)),
]
