from datetime import timedelta
from decimal import Decimal

from django.test import override_settings
from django.urls import reverse
from rest_framework import status

from apps.finance.models import (
    Account,
    Budget,
    BudgetKind,
    BudgetPeriodType,
    Category,
    Transaction,
    TransactionTemplate,
    TransactionType,
)
from apps.finance.testing import FinanceAPITestCase


CURRENCIES_URL = "/api/v1/finance/currencies/"



@override_settings(CURRENCY_RATES_ENABLED=False)
class FinanceCurrencyIntegrationAPITests(FinanceAPITestCase):
    def get_currency_row(self, code: str):
        response = self.client.get(CURRENCIES_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return next(item for item in response.data["items"] if item["code"] == code)

    def set_primary(self, code: str):
        row = self.get_currency_row(code)
        response = self.client.patch(f"{CURRENCIES_URL}{row['id']}/set-primary/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response

    def set_visibility(self, code: str, is_visible: bool):
        row = self.get_currency_row(code)
        response = self.client.patch(
            f"{CURRENCIES_URL}{row['id']}/visibility/",
            {"isVisible": is_visible},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response

    def test_account_creation_uses_primary_currency_by_default(self):
        self.authenticate()
        self.set_primary("USD")

        response = self.client.post(
            reverse("finance:account-list"),
            data={
                "name": "USD счёт",
                "type": "card",
                "initialBalanceRub": "100.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["currency"], "USD")
        account = Account.objects.get(pk=response.data["id"])
        self.assertEqual(account.currency, "USD")

    def test_hidden_currency_cannot_be_selected_for_new_account(self):
        self.authenticate()
        self.set_visibility("USD", False)

        response = self.client.post(
            reverse("finance:account-list"),
            data={
                "name": "Скрытый USD",
                "type": "card",
                "currency": "USD",
                "initialBalanceRub": "100.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        self.assertIn("currency", response.data["error"]["field_errors"])

    def test_account_meta_returns_primary_and_visible_currencies(self):
        self.authenticate()
        self.set_primary("USD")
        self.set_visibility("EUR", False)

        response = self.client.get(reverse("finance:account-meta"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["primaryCurrencyCode"], "USD")
        values = {item["value"] for item in response.data["currencies"]}
        self.assertIn("USD", values)
        self.assertNotIn("EUR", values)

    def test_budget_uses_primary_currency_by_default_and_rejects_hidden_currency(self):
        self.authenticate()
        self.set_primary("USD")
        period_start = self.today.replace(day=1)
        period_end = period_start + timedelta(days=30)

        create_response = self.client.post(
            reverse("finance:budget-list"),
            data={
                "categoryId": self.expense_category.id,
                "periodType": BudgetPeriodType.MONTH,
                "periodStart": str(period_start),
                "periodEnd": str(period_end),
                "limitRub": 12000,
                "kind": BudgetKind.EXPENSE,
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        budget = Budget.objects.get(pk=create_response.data["id"])
        self.assertEqual(budget.currency, "USD")

        self.set_primary("RUB")
        self.set_visibility("USD", False)
        next_period_start = period_start + timedelta(days=40)
        next_period_end = next_period_start + timedelta(days=30)
        hidden_response = self.client.post(
            reverse("finance:budget-list"),
            data={
                "categoryId": self.transport_category.id,
                "periodType": BudgetPeriodType.MONTH,
                "periodStart": str(next_period_start),
                "periodEnd": str(next_period_end),
                "limitRub": 5000,
                "currency": "USD",
                "kind": BudgetKind.EXPENSE,
            },
            format="json",
        )
        self.assertEqual(hidden_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("currency", hidden_response.data["error"]["field_errors"])

    def test_budget_meta_returns_visible_currencies(self):
        self.authenticate()
        self.set_visibility("EUR", False)

        response = self.client.get(f"{reverse('finance:budget-list')}meta/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        values = {item["value"] for item in response.data["currencies"]}
        self.assertIn("RUB", values)
        self.assertNotIn("EUR", values)

    def test_transaction_list_filters_by_currency(self):
        self.authenticate()
        usd_account = Account.objects.create(
            user=self.user,
            name="USD карта",
            type="card",
            currency="USD",
            initial_balance=Decimal("1000.00"),
            balance=Decimal("1000.00"),
        )
        rub_transaction = self.create_transaction(
            account=self.account,
            category=self.expense_category,
            amount="100.00",
            description="RUB операция",
        )
        usd_transaction = self.create_transaction(
            account=usd_account,
            category=self.expense_category,
            amount="10.00",
            description="USD операция",
        )

        usd_response = self.client.get(
            reverse("finance:transaction-list"),
            data={"currency": "USD"},
        )
        rub_response = self.client.get(
            reverse("finance:transaction-list"),
            data={"currencyCode": "RUB"},
        )

        self.assertEqual(usd_response.status_code, status.HTTP_200_OK)
        self.assertEqual(rub_response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in usd_response.data["results"]], [usd_transaction.id])
        self.assertIn(rub_transaction.id, [item["id"] for item in rub_response.data["results"]])

    def test_dashboard_uses_primary_currency_and_rejects_unavailable_currency(self):
        self.authenticate()
        self.set_primary("USD")

        default_response = self.client.get(reverse("finance:dashboard-summary"))
        self.assertEqual(default_response.status_code, status.HTTP_200_OK)
        self.assertEqual(default_response.data["currency"], "USD")

        self.set_primary("RUB")
        self.set_visibility("USD", False)
        hidden_response = self.client.get(
            reverse("finance:dashboard-summary"),
            data={"currency": "USD"},
        )
        self.assertEqual(hidden_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("currency", hidden_response.data["error"]["field_errors"])

    def test_goal_creation_rejects_account_with_hidden_currency(self):
        self.authenticate()
        usd_account = Account.objects.create(
            user=self.user,
            name="USD накопления",
            type="savings",
            currency="USD",
            initial_balance=Decimal("100.00"),
            balance=Decimal("100.00"),
        )
        self.set_visibility("USD", False)

        response = self.client.post(
            reverse("finance:goal-list"),
            data={
                "name": "Отпуск",
                "accountId": usd_account.id,
                "categoryKey": "travel",
                "priority": "medium",
                "targetRub": "1000.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("account", response.data["error"]["field_errors"])

    def test_transaction_template_meta_uses_primary_currency_and_rejects_hidden_account_currency(self):
        self.authenticate()
        self.set_primary("USD")
        usd_account = Account.objects.create(
            user=self.user,
            name="USD карта",
            type="card",
            currency="USD",
            initial_balance=Decimal("1000.00"),
            balance=Decimal("1000.00"),
        )
        meta_response = self.client.get(f"{reverse('finance:transaction-template-list')}meta/")

        self.assertEqual(meta_response.status_code, status.HTTP_200_OK)
        self.assertEqual(meta_response.data["defaultCurrency"], "USD")
        self.assertIn("currencies", meta_response.data)

        self.set_primary("RUB")
        self.set_visibility("USD", False)
        create_response = self.client.post(
            reverse("finance:transaction-template-list"),
            data={
                "name": "Шаблон USD",
                "kind": TransactionType.EXPENSE,
                "amountRub": 10,
                "accountId": usd_account.id,
                "categoryId": self.expense_category.id,
                "currency": "USD",
            },
            format="json",
        )

        self.assertEqual(create_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(create_response.data["success"])

    def test_existing_data_with_hidden_currency_is_not_lost(self):
        self.authenticate()
        usd_account = Account.objects.create(
            user=self.user,
            name="Старый USD счёт",
            type="card",
            currency="USD",
            initial_balance=Decimal("500.00"),
            balance=Decimal("500.00"),
        )
        old_transaction = Transaction.objects.create(
            user=self.user,
            account=usd_account,
            category=self.expense_category,
            type=TransactionType.EXPENSE,
            amount=Decimal("25.00"),
            description="Старая операция",
            operation_date=self.today,
        )
        self.set_visibility("USD", False)

        account_response = self.client.get(
            reverse("finance:account-detail", kwargs={"pk": usd_account.id})
        )
        transaction_response = self.client.get(
            reverse("finance:transaction-detail", kwargs={"pk": old_transaction.id})
        )

        self.assertEqual(account_response.status_code, status.HTTP_200_OK)
        self.assertEqual(account_response.data["currency"], "USD")
        self.assertEqual(transaction_response.status_code, status.HTTP_200_OK)
        self.assertEqual(transaction_response.data["account"], usd_account.id)
