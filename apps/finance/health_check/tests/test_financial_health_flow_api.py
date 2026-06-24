from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone

from apps.finance.health_check.constants import (
    METRIC_BUDGET_USAGE,
    METRIC_CASH_GAP_RISK,
    METRIC_EMERGENCY_FUND_PROGRESS,
    METRIC_EXPENSE_STABILITY,
    METRIC_SAVINGS_RATE,
    RECOMMENDATION_BUDGET_OVER_LIMIT,
    RECOMMENDATION_CASH_GAP_RISK,
    RECOMMENDATION_LOW_SAVINGS_RATE,
    RECOMMENDATION_NEGATIVE_NET_BALANCE,
    RECOMMENDATION_UNSTABLE_EXPENSES,
    RECOMMENDATION_WEAK_EMERGENCY_FUND,
)
from apps.finance.models import (
    Account,
    Budget,
    BudgetKind,
    BudgetPeriodType,
    Goal,
    GoalCategory,
    GoalStatus,
    PlannedStatus,
    PlannedTransaction,
    Transaction,
    TransactionType,
)
from apps.finance.testing import FinanceAPITestCase


User = get_user_model()


@override_settings(CURRENCY_RATES_ENABLED=False)
class FinancialHealthFlowApiTests(FinanceAPITestCase):
    meta_url = "/api/v1/finance/health-check/meta/"
    summary_url = "/api/v1/finance/health-check/summary/"

    def test_full_health_check_happy_path_returns_metrics_recommendations_and_isolated_data(self):
        self.authenticate()
        month_start = self.today.replace(day=1)
        previous_day = self.today - timezone.timedelta(days=1) if self.today.day > 1 else self.today

        self.create_transaction(
            account=self.account,
            category=self.income_category,
            type=TransactionType.INCOME,
            amount="100000.00",
            operation_date=self.today,
        )
        self.create_transaction(
            account=self.account,
            category=self.expense_category,
            type=TransactionType.EXPENSE,
            amount="90000.00",
            operation_date=self.today,
        )
        self.create_transaction(
            account=self.cash_account,
            category=self.transport_category,
            type=TransactionType.EXPENSE,
            amount="30000.00",
            operation_date=previous_day,
        )
        self.create_transaction(
            user=self.other_user,
            account=self.other_account,
            category=self.other_category,
            type=TransactionType.INCOME,
            amount="999999.00",
            operation_date=self.today,
        )

        Budget.objects.create(
            user=self.user,
            category=self.expense_category,
            period_type=BudgetPeriodType.MONTH,
            period_start=month_start,
            period_end=self.today,
            amount_limit=Decimal("10000.00"),
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
            name="Крупный плановый платёж",
            type=TransactionType.EXPENSE,
            amount=Decimal("40000.00"),
            planned_date=self.today,
            status=PlannedStatus.CONFIRMED,
            include_in_forecast=True,
        )

        meta_response = self.client.get(self.meta_url)
        summary_response = self.client.get(
            self.summary_url,
            {
                "period": "month",
                "currency": "RUB",
            },
        )

        self.assertEqual(meta_response.status_code, 200)
        self.assertEqual(summary_response.status_code, 200)
        self.assertEqual(meta_response.data["scoreRange"], {"min": 0, "max": 100})
        self.assertEqual(len(meta_response.data["metrics"]), 7)

        payload = summary_response.data
        self.assertEqual(payload["currency"], "RUB")
        self.assertEqual(payload["totals"]["income"]["amount"], 100000.0)
        self.assertEqual(payload["totals"]["expenses"]["amount"], 120000.0)
        self.assertEqual(payload["totals"]["netBalance"]["amount"], -20000.0)
        self.assertGreaterEqual(payload["score"], 0)
        self.assertLessEqual(payload["score"], 100)
        self.assertIn(payload["level"], {"critical", "risk", "warning", "good", "excellent"})
        self.assertEqual(payload["dataQuality"]["transactionCount"], 3)
        self.assertEqual(payload["dataQuality"]["budgetCount"], 1)
        self.assertEqual(payload["dataQuality"]["goalCount"], 1)
        self.assertEqual(payload["dataQuality"]["plannedTransactionCount"], 1)

        metrics = {metric["id"]: metric for metric in payload["metrics"]}
        self.assertEqual(metrics[METRIC_BUDGET_USAGE]["details"]["budgetCount"], 1)
        self.assertTrue(metrics[METRIC_BUDGET_USAGE]["details"]["overLimit"])
        self.assertEqual(metrics[METRIC_EMERGENCY_FUND_PROGRESS]["details"]["goalCount"], 1)
        self.assertTrue(metrics[METRIC_CASH_GAP_RISK]["details"]["hasCashGapRisk"])
        self.assertLess(metrics[METRIC_SAVINGS_RATE]["score"], 75)

        recommendation_codes = {item["code"] for item in payload["recommendations"]}
        self.assertTrue(
            {
                RECOMMENDATION_NEGATIVE_NET_BALANCE,
                RECOMMENDATION_CASH_GAP_RISK,
                RECOMMENDATION_BUDGET_OVER_LIMIT,
                RECOMMENDATION_LOW_SAVINGS_RATE,
                RECOMMENDATION_WEAK_EMERGENCY_FUND,
            }.issubset(recommendation_codes)
        )
        self.assertLessEqual(len(payload["recommendations"]), 6)

    def test_empty_user_summary_returns_stable_payload_and_quality_warnings(self):
        empty_user = User.objects.create_user(
            username="empty-health-user",
            email="empty-health-user@example.com",
            password="empty-password-123",
        )
        self.client.force_authenticate(user=empty_user)

        response = self.client.get(self.summary_url, {"period": "month", "currency": "RUB"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["totals"]["income"]["amount"], 0.0)
        self.assertEqual(response.data["totals"]["expenses"]["amount"], 0.0)
        self.assertFalse(response.data["dataQuality"]["hasEnoughData"])
        self.assertEqual(response.data["dataQuality"]["transactionCount"], 0)
        self.assertEqual(response.data["dataQuality"]["accountCount"], 0)
        self.assertGreaterEqual(len(response.data["dataQuality"]["warnings"]), 3)
        self.assertEqual(len(response.data["metrics"]), 7)

    def test_summary_custom_period_uses_current_user_and_requested_dates_only(self):
        self.authenticate()
        custom_start = self.today.replace(day=1)
        custom_end = self.today
        outside_date = custom_start - timezone.timedelta(days=1)

        self.create_transaction(
            account=self.account,
            category=self.income_category,
            type=TransactionType.INCOME,
            amount="15000.00",
            operation_date=custom_start,
        )
        self.create_transaction(
            account=self.account,
            category=self.expense_category,
            type=TransactionType.EXPENSE,
            amount="4000.00",
            operation_date=custom_end,
        )
        self.create_transaction(
            account=self.account,
            category=self.expense_category,
            type=TransactionType.EXPENSE,
            amount="9999.00",
            operation_date=outside_date,
        )
        self.create_transaction(
            user=self.other_user,
            account=self.other_account,
            category=self.other_category,
            type=TransactionType.EXPENSE,
            amount="8888.00",
            operation_date=custom_end,
        )

        response = self.client.get(
            self.summary_url,
            {
                "period": "custom",
                "date_from": custom_start.isoformat(),
                "date_to": custom_end.isoformat(),
                "currency": "RUB",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["period"]["type"], "custom")
        self.assertEqual(response.data["period"]["dateFrom"], custom_start.isoformat())
        self.assertEqual(response.data["period"]["dateTo"], custom_end.isoformat())
        self.assertEqual(response.data["totals"]["income"]["amount"], 15000.0)
        self.assertEqual(response.data["totals"]["expenses"]["amount"], 4000.0)
        self.assertEqual(response.data["dataQuality"]["transactionCount"], 2)

    def test_summary_rejects_invalid_filters(self):
        self.authenticate()

        cases = [
            {"period": "wrong"},
            {"period": "custom", "date_from": self.today.isoformat()},
            {
                "period": "custom",
                "date_from": self.today.isoformat(),
                "date_to": (self.today - timezone.timedelta(days=1)).isoformat(),
            },
            {"period": "month", "currency": "RU"},
        ]

        for query in cases:
            with self.subTest(query=query):
                response = self.client.get(self.summary_url, query)
                self.assertEqual(response.status_code, 400)

    def test_summary_is_read_only(self):
        self.authenticate()
        self.create_transaction(
            account=self.account,
            category=self.income_category,
            type=TransactionType.INCOME,
            amount="20000.00",
            operation_date=self.today,
        )
        self.create_transaction(
            account=self.account,
            category=self.expense_category,
            type=TransactionType.EXPENSE,
            amount="5000.00",
            operation_date=self.today,
        )
        counts_before = self._finance_counts()
        account_balance_before = self.account.balance

        first_response = self.client.get(self.summary_url, {"period": "month", "currency": "RUB"})
        second_response = self.client.get(self.summary_url, {"period": "month", "currency": "RUB"})

        self.account.refresh_from_db()
        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(self._finance_counts(), counts_before)
        self.assertEqual(self.account.balance, account_balance_before)
        self.assertEqual(first_response.data["totals"], second_response.data["totals"])
        self.assertEqual(first_response.data["score"], second_response.data["score"])

    def test_regular_user_cannot_access_without_authentication(self):
        meta_response = self.client.get(self.meta_url)
        summary_response = self.client.get(self.summary_url)

        self.assertEqual(meta_response.status_code, 401)
        self.assertEqual(summary_response.status_code, 401)

    def test_expense_stability_recommendation_is_returned_for_concentrated_expenses(self):
        self.authenticate()
        self.create_transaction(
            account=self.account,
            category=self.income_category,
            type=TransactionType.INCOME,
            amount="80000.00",
            operation_date=self.today,
        )
        self.create_transaction(
            account=self.account,
            category=self.expense_category,
            type=TransactionType.EXPENSE,
            amount="60000.00",
            operation_date=self.today,
        )

        response = self.client.get(self.summary_url, {"period": "month", "currency": "RUB"})

        self.assertEqual(response.status_code, 200)
        metrics = {metric["id"]: metric for metric in response.data["metrics"]}
        recommendation_codes = {item["code"] for item in response.data["recommendations"]}

        self.assertLess(metrics[METRIC_EXPENSE_STABILITY]["score"], 65)
        self.assertIn(RECOMMENDATION_UNSTABLE_EXPENSES, recommendation_codes)

    def _finance_counts(self):
        return {
            "accounts": Account.objects.filter(user=self.user).count(),
            "transactions": Transaction.objects.filter(user=self.user).count(),
            "budgets": Budget.objects.filter(user=self.user).count(),
            "goals": Goal.objects.filter(user=self.user).count(),
            "planned_transactions": PlannedTransaction.objects.filter(user=self.user).count(),
        }
