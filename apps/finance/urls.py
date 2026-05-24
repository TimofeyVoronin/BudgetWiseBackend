from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.finance.accounts.views import AccountViewSet
from apps.finance.budgets.views import BudgetViewSet
from apps.finance.calculators.views import (
    CalculatorCalculateView,
    CalculatorDefaultsView,
    CalculatorsHubView,
)
from apps.finance.budget_notifications.views import (
    BudgetNotificationCheckView,
    BudgetNotificationMetaView,
    BudgetNotificationPreviewView,
    BudgetNotificationSettingsView,
    BudgetNotificationTestView,
    BudgetNotificationThresholdValidationView,
)
from apps.finance.categories.views import CategoryViewSet
from apps.finance.currencies.views import CurrencyViewSet
from apps.finance.dashboard.views import (
    DashboardAccountsSummaryView,
    DashboardBalanceSummaryView,
    DashboardExpenseDynamicsView,
    DashboardGoalsSummaryView,
    DashboardPeriodCurrencyView,
    DashboardSummaryView,
)
from apps.finance.financial_calendar.views import (
    FinancialCalendarDayView,
    FinancialCalendarExportPreviewView,
    FinancialCalendarExportView,
    FinancialCalendarEventsView,
    FinancialCalendarMetaView,
    FinancialCalendarMonthView,
)
from apps.finance.goals.views import GoalViewSet
from apps.finance.notifications.views import NotificationViewSet
from apps.finance.planned_transactions.views import PlannedTransactionViewSet
from apps.finance.recurring_transactions.views import RecurringTransactionViewSet
from apps.finance.receipts.views import ReceiptCreateTransactionsView, ReceiptImportByQRView
from apps.finance.tags.views import TagViewSet
from apps.finance.transaction_templates.views import TransactionTemplateViewSet
from apps.finance.transactions.views import (
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
        "sync/",
        include("apps.finance.sync.urls"),
        name="sync",
    ),

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
        "dashboard/period-currency/",
        DashboardPeriodCurrencyView.as_view(),
        name="dashboard-period-currency",
    ),
    path(
        "dashboard/balance-summary/",
        DashboardBalanceSummaryView.as_view(),
        name="dashboard-balance-summary",
    ),
    path(
        "dashboard/accounts-summary/",
        DashboardAccountsSummaryView.as_view(),
        name="dashboard-accounts-summary",
    ),
    path(
        "dashboard/goals-summary/",
        DashboardGoalsSummaryView.as_view(),
        name="dashboard-goals-summary",
    ),
    path(
        "dashboard/expense-dynamics/",
        DashboardExpenseDynamicsView.as_view(),
        name="dashboard-expense-dynamics",
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
        "receipts/qr/",
        ReceiptImportByQRView.as_view(),
        name="receipt-qr",
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
