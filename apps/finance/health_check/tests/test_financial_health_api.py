from decimal import Decimal

from django.test import override_settings

from apps.finance.health_check.constants import (
    FINANCIAL_HEALTH_DEFAULT_PERIOD,
    FINANCIAL_HEALTH_TAG,
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


@override_settings(CURRENCY_RATES_ENABLED=False)
class FinancialHealthApiTests(FinanceAPITestCase):
    meta_url = "/api/v1/finance/health-check/meta/"
    summary_url = "/api/v1/finance/health-check/summary/"

    def test_meta_requires_authentication(self):
        response = self.client.get(self.meta_url)

        self.assertEqual(response.status_code, 401)

    def test_meta_returns_contract_for_authenticated_user(self):
        self.authenticate()

        response = self.client.get(self.meta_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["defaultPeriod"], FINANCIAL_HEALTH_DEFAULT_PERIOD)
        self.assertEqual(len(response.data["metrics"]), 7)
        self.assertEqual(len(response.data["levels"]), 5)
        self.assertIn("summaryContract", response.data)
        self.assertTrue(
            any(metric["id"] == "savingsRate" for metric in response.data["metrics"])
        )

    def test_summary_requires_authentication(self):
        response = self.client.get(self.summary_url)

        self.assertEqual(response.status_code, 401)

    def test_summary_returns_score_metrics_and_recommendations(self):
        self.authenticate()
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
            amount="65000.00",
            operation_date=self.today,
        )
        Budget.objects.create(
            user=self.user,
            category=self.expense_category,
            period_type=BudgetPeriodType.MONTH,
            period_start=month_start,
            period_end=self.today,
            amount_limit=Decimal("30000.00"),
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
            current_amount=Decimal("5000.00"),
        )
        PlannedTransaction.objects.create(
            user=self.user,
            account=self.account,
            category=self.expense_category,
            name="Плановый платёж",
            type=TransactionType.EXPENSE,
            amount=Decimal("40000.00"),
            planned_date=self.today,
            status=PlannedStatus.PENDING,
            include_in_forecast=True,
        )
        self.create_transaction(
            user=self.other_user,
            account=self.other_account,
            category=self.other_category,
            type=TransactionType.INCOME,
            amount="999999.00",
            operation_date=self.today,
        )

        response = self.client.get(self.summary_url, {"period": "month", "currency": "RUB"})

        self.assertEqual(response.status_code, 200)
        self.assertIn(response.data["level"], {"critical", "risk", "warning", "good", "excellent"})
        self.assertGreaterEqual(response.data["score"], 0)
        self.assertLessEqual(response.data["score"], 100)
        self.assertEqual(response.data["currency"], "RUB")
        self.assertEqual(response.data["totals"]["income"]["amount"], 50000.0)
        self.assertEqual(response.data["totals"]["expenses"]["amount"], 65000.0)
        self.assertEqual(len(response.data["metrics"]), 7)
        self.assertGreaterEqual(len(response.data["recommendations"]), 1)
        self.assertEqual(response.data["dataQuality"]["transactionCount"], 2)

    def test_summary_supports_custom_period(self):
        self.authenticate()
        self.create_transaction(
            account=self.account,
            category=self.income_category,
            type=TransactionType.INCOME,
            amount="10000.00",
            operation_date=self.today,
        )

        response = self.client.get(
            self.summary_url,
            {
                "period": "custom",
                "date_from": self.today.isoformat(),
                "date_to": self.today.isoformat(),
                "currency": "RUB",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["period"]["type"], "custom")
        self.assertEqual(response.data["period"]["dateFrom"], self.today.isoformat())
        self.assertEqual(response.data["period"]["dateTo"], self.today.isoformat())

    def test_summary_rejects_invalid_query_params(self):
        self.authenticate()

        invalid_period_response = self.client.get(self.summary_url, {"period": "wrong"})
        invalid_currency_response = self.client.get(self.summary_url, {"currency": "RU"})
        invalid_custom_response = self.client.get(
            self.summary_url,
            {"period": "custom", "date_from": "2026-06-10"},
        )

        self.assertEqual(invalid_period_response.status_code, 400)
        self.assertEqual(invalid_currency_response.status_code, 400)
        self.assertEqual(invalid_custom_response.status_code, 400)

    def test_financial_health_tag_constant_matches_swagger_tag(self):
        self.assertEqual(FINANCIAL_HEALTH_TAG, "finance-health-check")
