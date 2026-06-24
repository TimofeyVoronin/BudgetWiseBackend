from decimal import Decimal

from django.test import override_settings

from apps.finance.health_check.constants import (
    METRIC_BUDGET_USAGE,
    METRIC_CASH_GAP_RISK,
    METRIC_EMERGENCY_FUND_PROGRESS,
    METRIC_EXPENSE_STABILITY,
    METRIC_INCOME_EXPENSE_RATIO,
    METRIC_PLANNED_PAYMENTS_LOAD,
    METRIC_SAVINGS_RATE,
)
from apps.finance.health_check.scoring import (
    build_financial_health_score,
    build_financial_health_summary,
    score_financial_health_metric,
)
from apps.finance.models import (
    Budget,
    BudgetKind,
    BudgetPeriodType,
    Goal,
    GoalCategory,
    GoalStatus,
    PlannedStatus,
    PlannedTransaction,
    TransactionType,
)
from apps.finance.testing import FinanceAPITestCase


class FinancialHealthScoreUnitTests(FinanceAPITestCase):
    def test_metric_scoring_boundaries_are_stable(self):
        cases = [
            (METRIC_INCOME_EXPENSE_RATIO, {"value": 2.0}, 100),
            (METRIC_INCOME_EXPENSE_RATIO, {"value": 0.7}, 35),
            (METRIC_SAVINGS_RATE, {"value": 25.0}, 90),
            (METRIC_BUDGET_USAGE, {"value": 80.0, "budgetCount": 1}, 85),
            (METRIC_EMERGENCY_FUND_PROGRESS, {"value": 50.0, "goalCount": 1}, 75),
            (METRIC_CASH_GAP_RISK, {"hasCashGapRisk": False}, 100),
            (
                METRIC_PLANNED_PAYMENTS_LOAD,
                {"value": 20.0, "plannedExpenses": {"amount": 1000.0, "currency": "RUB"}},
                85,
            ),
            (METRIC_EXPENSE_STABILITY, {"daysWithExpenses": 3, "concentrationRatio": 2.0}, 100),
        ]

        for metric_id, aggregate, expected_score in cases:
            with self.subTest(metric_id=metric_id):
                self.assertEqual(
                    score_financial_health_metric(metric_id, aggregate),
                    expected_score,
                )

    def test_weighted_overall_score_is_calculated_from_metric_weights(self):
        payload = build_financial_health_score(
            {
                "metrics": {
                    METRIC_INCOME_EXPENSE_RATIO: {"value": 1.5},
                    METRIC_SAVINGS_RATE: {"value": 25.0},
                    METRIC_BUDGET_USAGE: {"value": 80.0, "budgetCount": 1},
                    METRIC_EMERGENCY_FUND_PROGRESS: {"value": 50.0, "goalCount": 1},
                    METRIC_CASH_GAP_RISK: {"hasCashGapRisk": False},
                    METRIC_PLANNED_PAYMENTS_LOAD: {
                        "value": 20.0,
                        "plannedExpenses": {"amount": 1000.0, "currency": "RUB"},
                    },
                    METRIC_EXPENSE_STABILITY: {
                        "daysWithExpenses": 5,
                        "concentrationRatio": 2.0,
                    },
                }
            }
        )

        self.assertEqual(payload["score"], 88)
        self.assertEqual(payload["level"], "good")
        self.assertEqual(len(payload["metrics"]), 7)
        self.assertEqual(
            [item["id"] for item in payload["metrics"]],
            [
                METRIC_INCOME_EXPENSE_RATIO,
                METRIC_SAVINGS_RATE,
                METRIC_BUDGET_USAGE,
                METRIC_EMERGENCY_FUND_PROGRESS,
                METRIC_CASH_GAP_RISK,
                METRIC_PLANNED_PAYMENTS_LOAD,
                METRIC_EXPENSE_STABILITY,
            ],
        )
        self.assertTrue(all(0 <= item["score"] <= 100 for item in payload["metrics"]))
        self.assertTrue(all(item["level"] for item in payload["metrics"]))


@override_settings(CURRENCY_RATES_ENABLED=False)
class FinancialHealthSummaryTests(FinanceAPITestCase):
    def test_summary_adds_score_level_and_metric_breakdown_to_aggregates(self):
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
        self.create_transaction(
            account=self.cash_account,
            category=self.transport_category,
            type=TransactionType.EXPENSE,
            amount="3000.00",
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

        payload = build_financial_health_summary(user=self.user)

        self.assertGreaterEqual(payload["score"], 75)
        self.assertIn(payload["level"], {"good", "excellent"})
        self.assertEqual(payload["currency"], "RUB")
        self.assertEqual(len(payload["metrics"]), 7)
        self.assertEqual(payload["recommendations"], [])
        self.assertEqual(payload["dataQuality"]["transactionCount"], 3)
        self.assertEqual(payload["totals"]["income"]["amount"], 50000.0)

    def test_empty_user_gets_low_score_without_creating_finance_data(self):
        user = self.other_user
        before_budget_count = Budget.objects.filter(user=user).count()
        before_goal_count = Goal.objects.filter(user=user).count()

        payload = build_financial_health_summary(user=user)

        self.assertEqual(payload["level"], "critical")
        self.assertLessEqual(payload["score"], 39)
        self.assertEqual(payload["dataQuality"]["transactionCount"], 0)
        self.assertEqual(Budget.objects.filter(user=user).count(), before_budget_count)
        self.assertEqual(Goal.objects.filter(user=user).count(), before_goal_count)
