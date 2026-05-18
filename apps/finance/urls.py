from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.finance.views import (
    CategoryViewSet,
    DashboardSummaryView,
    TransactionExportView,
    TransactionViewSet,
)


app_name = "finance"

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
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