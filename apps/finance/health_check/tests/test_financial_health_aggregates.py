from decimal import Decimal

from django.test import override_settings
from django.utils import timezone

from apps.finance.health_check.constants import (
    FINANCIAL_HEALTH_PERIOD_CUSTOM,
    FINANCIAL_HEALTH_PERIOD_MONTH,
    METRIC_BUDGET_USAGE,
    METRIC_CASH_GAP_RISK,
    METRIC_EMERGENCY_FUND_PROGRESS,
    METRIC_EXPENSE_STABILITY,
    METRIC_INCOME_EXPENSE_RATIO,
    METRIC_PLANNED_PAYMENTS_LOAD,
    METRIC_SAVINGS_RATE,
)
from apps.finance.health_check.services import (
    build_financial_health_aggregates,
    resolve_financial_health_period,
)
from apps.finance.models import (
    Account,
    Budget,
    BudgetKind,
    BudgetPeriodType,
    Category,
    Goal,
    GoalCategory,
    GoalStatus,
    PlannedStatus,
    PlannedTransaction,
    TransactionType,
)
from apps.finance.testing import FinanceAPITestCase


@override_settings(CURRENCY_RATES_ENABLED=False)
class FinancialHealthAggregatesTests(FinanceAPITestCase):
    def test_default_period_is_current_month(self):
        period = resolve_financial_health_period(user=self.user, today=self.today)

        self.assertEqual(period.type, FINANCIAL_HEALTH_PERIOD_MONTH)
        self.assertEqual(period.date_from, self.today.replace(day=1))
        self.assertEqual(period.date_to, self.today)
        self.assertGreaterEqual(period.days, 1)

    def test_custom_period_validation(self):
        with self.assertRaises(Exception):
            resolve_financial_health_period(
                user=self.user,
                period=FINANCIAL_HEALTH_PERIOD_CUSTOM,
                date_from="2026-06-10",
            )

        with self.assertRaises(Exception):
            resolve_financial_health_period(
                user=self.user,
                period=FINANCIAL_HEALTH_PERIOD_CUSTOM,
                date_from="2026-06-10",
                date_to="2026-06-01",
            )

    def test_aggregates_include_cashflow_budgets_goals_and_planned_transactions(self):
        month_start = self.today.replace(day=1)
        self.create_transaction(
            account=self.account,
            category=self.income_category,
            type=TransactionType.INCOME,
            amount="50000.00",
            operation_date=self.today,
        )
        self.create_transaction(
            account=self.account,
            category=self.expense_category,
            type=TransactionType.EXPENSE,
            amount="12000.00",
            operation_date=self.today,
        )
        second_expense_date = (
            self.today - timezone.timedelta(days=1)
            if self.today.day > 1
            else self.today
        )
        expected_expense_days = 2 if self.today.day > 1 else 1
        self.create_transaction(
            account=self.cash_account,
            category=self.transport_category,
            type=TransactionType.EXPENSE,
            amount="3000.00",
            operation_date=second_expense_date,
        )
        self.create_transaction(
            user=self.other_user,
            account=self.other_account,
            category=self.other_category,
            type=TransactionType.EXPENSE,
            amount="99999.00",
            operation_date=self.today,
        )
        Budget.objects.create(
            user=self.user,
            category=self.expense_category,
            period_type=BudgetPeriodType.MONTH,
            period_start=month_start,
            period_end=self.today,
            amount_limit=Decimal("20000.00"),
            currency="RUB",
            kind=BudgetKind.EXPENSE,
        )
        Goal.objects.create(
            user=self.user,
            account=self.account,
            name="Финансовая подушка",
            category=GoalCategory.SAVINGS,
            status=GoalStatus.ACTIVE,
            target_amount=Decimal("100000.00"),
            current_amount=Decimal("25000.00"),
        )
        PlannedTransaction.objects.create(
            user=self.user,
            account=self.account,
            category=self.expense_category,
            name="Плановый платёж",
            type=TransactionType.EXPENSE,
            amount=Decimal("5000.00"),
            planned_date=self.today,
            status=PlannedStatus.PENDING,
            include_in_forecast=True,
        )

        payload = build_financial_health_aggregates(user=self.user)

        self.assertEqual(payload["currency"], "RUB")
        self.assertEqual(payload["totals"]["income"]["amount"], 50000.0)
        self.assertEqual(payload["totals"]["expenses"]["amount"], 15000.0)
        self.assertEqual(payload["totals"]["netBalance"]["amount"], 35000.0)
        self.assertEqual(payload["totals"]["accountsBalance"]["amount"], 13000.0)

        self.assertEqual(payload["metrics"][METRIC_INCOME_EXPENSE_RATIO]["value"], 3.3333)
        self.assertEqual(payload["metrics"][METRIC_SAVINGS_RATE]["value"], 70.0)
        self.assertEqual(payload["metrics"][METRIC_BUDGET_USAGE]["value"], 60.0)
        self.assertEqual(payload["metrics"][METRIC_BUDGET_USAGE]["budgetCount"], 1)
        self.assertEqual(payload["metrics"][METRIC_EMERGENCY_FUND_PROGRESS]["value"], 25.0)
        self.assertEqual(payload["metrics"][METRIC_PLANNED_PAYMENTS_LOAD]["value"], 10.0)
        self.assertFalse(payload["metrics"][METRIC_CASH_GAP_RISK]["hasCashGapRisk"])
        self.assertEqual(
            payload["metrics"][METRIC_EXPENSE_STABILITY]["daysWithExpenses"],
            expected_expense_days,
        )
        self.assertEqual(payload["dataQuality"]["transactionCount"], 3)
        self.assertEqual(payload["dataQuality"]["budgetCount"], 1)
        self.assertEqual(payload["dataQuality"]["goalCount"], 1)
        self.assertEqual(payload["dataQuality"]["plannedTransactionCount"], 1)

    def test_empty_user_returns_zero_aggregates_and_warnings(self):
        user = self.other_user
        Account.objects.filter(user=user).delete()
        Category.objects.filter(user=user).delete()

        payload = build_financial_health_aggregates(user=user)

        self.assertEqual(payload["totals"]["income"]["amount"], 0.0)
        self.assertEqual(payload["totals"]["expenses"]["amount"], 0.0)
        self.assertIsNone(payload["metrics"][METRIC_INCOME_EXPENSE_RATIO]["value"])
        self.assertIsNone(payload["metrics"][METRIC_SAVINGS_RATE]["value"])
        self.assertEqual(payload["dataQuality"]["transactionCount"], 0)
        self.assertGreaterEqual(len(payload["dataQuality"]["warnings"]), 1)

    def test_cash_gap_risk_uses_current_user_only(self):
        current_account = Account.objects.create(
            user=self.user,
            name="Малый остаток",
            initial_balance=Decimal("1000.00"),
            balance=Decimal("1000.00"),
            currency="RUB",
        )
        expense_category = Category.objects.create(
            user=self.user,
            name="Крупный платёж",
            type=TransactionType.EXPENSE,
        )
        PlannedTransaction.objects.create(
            user=self.user,
            account=current_account,
            category=expense_category,
            name="Аренда",
            type=TransactionType.EXPENSE,
            amount=Decimal("20000.00"),
            planned_date=self.today,
            status=PlannedStatus.CONFIRMED,
            include_in_forecast=True,
        )
        PlannedTransaction.objects.create(
            user=self.other_user,
            account=self.other_account,
            category=self.other_category,
            name="Чужой доход",
            type=TransactionType.INCOME,
            amount=Decimal("100000.00"),
            planned_date=self.today,
            status=PlannedStatus.CONFIRMED,
            include_in_forecast=True,
        )

        payload = build_financial_health_aggregates(user=self.user)
        cash_gap = payload["metrics"][METRIC_CASH_GAP_RISK]

        self.assertTrue(cash_gap["hasCashGapRisk"])
        self.assertEqual(cash_gap["projectedBalance"]["amount"], -6000.0)
        self.assertEqual(cash_gap["gapAmount"]["amount"], 6000.0)
