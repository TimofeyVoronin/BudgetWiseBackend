from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.finance.account_views import AccountViewSet
from apps.finance.budget_views import BudgetViewSet
from apps.finance.budget_notification_views import (
    BudgetNotificationCheckView,
    BudgetNotificationMetaView,
    BudgetNotificationPreviewView,
    BudgetNotificationSettingsView,
    BudgetNotificationTestView,
    BudgetNotificationThresholdValidationView,
)
from apps.finance.category_views import CategoryViewSet
from apps.finance.currency_views import CurrencyViewSet
from apps.finance.dashboard_views import DashboardSummaryView
from apps.finance.goal_views import GoalViewSet
from apps.finance.notification_views import NotificationViewSet
from apps.finance.planned_transaction_views import PlannedTransactionViewSet
from apps.finance.recurring_transaction_views import RecurringTransactionViewSet
from apps.finance.tag_views import TagViewSet
from apps.finance.transaction_template_views import TransactionTemplateViewSet
from apps.finance.transaction_views import (
    TransactionExportView,
    TransactionViewSet,
)


app_name = "finance"

router = DefaultRouter()
router.register("accounts", AccountViewSet, basename="account")
router.register("budgets", BudgetViewSet, basename="budget")
router.register("categories", CategoryViewSet, basename="category")
router.register("currencies", CurrencyViewSet, basename="currency")
router.register("goals", GoalViewSet, basename="goal")
router.register("notifications", NotificationViewSet, basename="notification")
router.register("planned-transactions", PlannedTransactionViewSet, basename="planned-transaction")
router.register("recurring-transactions", RecurringTransactionViewSet, basename="recurring-transaction")
router.register("tags", TagViewSet, basename="tag")
router.register("transaction-templates", TransactionTemplateViewSet, basename="transaction-template")
router.register("transactions", TransactionViewSet, basename="transaction")

urlpatterns = [

    path(
        "budget-notifications/settings/",
        BudgetNotificationSettingsView.as_view(),
        name="budget-notification-settings",
    ),
    path(
        "budget-notifications/settings/validate-thresholds/",
        BudgetNotificationThresholdValidationView.as_view(),
        name="budget-notification-validate-thresholds",
    ),
    path(
        "budget-notifications/settings/test/",
        BudgetNotificationTestView.as_view(),
        name="budget-notification-test",
    ),
    path(
        "budget-notifications/settings/preview/",
        BudgetNotificationPreviewView.as_view(),
        name="budget-notification-preview",
    ),
    path(
        "budget-notifications/meta/",
        BudgetNotificationMetaView.as_view(),
        name="budget-notification-meta",
    ),
    path(
        "budget-notifications/check/",
        BudgetNotificationCheckView.as_view(),
        name="budget-notification-check",
    ),
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
