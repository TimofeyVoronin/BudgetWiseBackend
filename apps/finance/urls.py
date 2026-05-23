from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.finance.account_views import AccountViewSet
from apps.finance.budget_views import BudgetViewSet
from apps.finance.calculator_views import (
    CalculatorCalculateView,
    CalculatorDefaultsView,
    CalculatorsHubView,
)
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
from apps.finance.financial_calendar_views import (
    FinancialCalendarDayView,
    FinancialCalendarExportPreviewView,
    FinancialCalendarExportView,
    FinancialCalendarEventsView,
    FinancialCalendarMetaView,
    FinancialCalendarMonthView,
)
from apps.finance.goal_views import GoalViewSet
from apps.finance.notification_views import NotificationViewSet
from apps.finance.planned_transaction_views import PlannedTransactionViewSet
from apps.finance.recurring_transaction_views import RecurringTransactionViewSet
from apps.finance.receipt_transaction_views import ReceiptCreateTransactionsView
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
        "calculators/",
        CalculatorsHubView.as_view(),
        name="calculators-hub",
    ),
    path(
        "calculators/<str:calc_id>/defaults/",
        CalculatorDefaultsView.as_view(),
        name="calculator-defaults",
    ),
    path(
        "calculators/<str:calc_id>/calculate/",
        CalculatorCalculateView.as_view(),
        name="calculator-calculate",
    ),
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
        "financial-calendar/",
        FinancialCalendarMonthView.as_view(),
        name="financial-calendar-month",
    ),
    path(
        "financial-calendar/events/",
        FinancialCalendarEventsView.as_view(),
        name="financial-calendar-events",
    ),
    path(
        "financial-calendar/days/<str:iso>/",
        FinancialCalendarDayView.as_view(),
        name="financial-calendar-day",
    ),
    path(
        "financial-calendar/meta/",
        FinancialCalendarMetaView.as_view(),
        name="financial-calendar-meta",
    ),
    path(
        "financial-calendar/export/preview/",
        FinancialCalendarExportPreviewView.as_view(),
        name="financial-calendar-export-preview",
    ),
    path(
        "financial-calendar/export/",
        FinancialCalendarExportView.as_view(),
        name="financial-calendar-export",
    ),
    path(
        "receipts/<int:receipt_id>/create-transactions/",
        ReceiptCreateTransactionsView.as_view(),
        name="receipt-create-transactions",
    ),
    path(
        "transactions/export/",
        TransactionExportView.as_view(),
        name="transaction-export",
    ),
    path("", include(router.urls)),
]
