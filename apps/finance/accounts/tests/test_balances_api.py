from decimal import Decimal

from django.urls import reverse
from rest_framework import status

from apps.finance.models import TransactionType

from apps.finance.testing import FinanceAPITestCase


class FinanceAccountBalanceAPITests(FinanceAPITestCase):
    def test_create_expense_transaction_decreases_account_balance(self):
        self.authenticate()

        response = self.client.post(
            reverse("finance:transaction-list"),
            data={
                "account": self.account.id,
                "category": self.expense_category.id,
                "type": TransactionType.EXPENSE,
                "amount": "1500.00",
                "description": "Покупка продуктов",
                "operation_date": self.today,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal("8500.00"))

    def test_create_income_transaction_increases_account_balance(self):
        self.authenticate()

        response = self.client.post(
            reverse("finance:transaction-list"),
            data={
                "account": self.account.id,
                "category": self.income_category.id,
                "type": TransactionType.INCOME,
                "amount": "5000.00",
                "description": "Зарплата",
                "operation_date": self.today,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal("15000.00"))

    def test_update_transaction_recalculates_balance_on_same_account(self):
        self.authenticate()

        create_response = self.client.post(
            reverse("finance:transaction-list"),
            data={
                "account": self.account.id,
                "category": self.expense_category.id,
                "type": TransactionType.EXPENSE,
                "amount": "1000.00",
                "description": "Первичная сумма",
                "operation_date": self.today,
            },
            format="json",
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)

        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal("9000.00"))

        transaction_id = create_response.data["id"]

        update_response = self.client.patch(
            reverse("finance:transaction-detail", kwargs={"pk": transaction_id}),
            data={
                "amount": "1500.00",
                "description": "Обновлённая сумма",
            },
            format="json",
        )

        self.assertEqual(update_response.status_code, status.HTTP_200_OK)

        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal("8500.00"))

    def test_update_transaction_moves_balance_between_accounts(self):
        self.authenticate()

        create_response = self.client.post(
            reverse("finance:transaction-list"),
            data={
                "account": self.account.id,
                "category": self.expense_category.id,
                "type": TransactionType.EXPENSE,
                "amount": "1000.00",
                "description": "Операция для переноса",
                "operation_date": self.today,
            },
            format="json",
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)

        self.account.refresh_from_db()
        self.cash_account.refresh_from_db()

        self.assertEqual(self.account.balance, Decimal("9000.00"))
        self.assertEqual(self.cash_account.balance, Decimal("3000.00"))

        transaction_id = create_response.data["id"]

        update_response = self.client.patch(
            reverse("finance:transaction-detail", kwargs={"pk": transaction_id}),
            data={
                "account": self.cash_account.id,
                "amount": "500.00",
            },
            format="json",
        )

        self.assertEqual(update_response.status_code, status.HTTP_200_OK)

        self.account.refresh_from_db()
        self.cash_account.refresh_from_db()

        self.assertEqual(self.account.balance, Decimal("10000.00"))
        self.assertEqual(self.cash_account.balance, Decimal("2500.00"))

    def test_update_transaction_type_recalculates_balance(self):
        self.authenticate()

        create_response = self.client.post(
            reverse("finance:transaction-list"),
            data={
                "account": self.account.id,
                "category": self.expense_category.id,
                "type": TransactionType.EXPENSE,
                "amount": "1000.00",
                "description": "Расход для смены типа",
                "operation_date": self.today,
            },
            format="json",
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)

        transaction_id = create_response.data["id"]

        update_response = self.client.patch(
            reverse("finance:transaction-detail", kwargs={"pk": transaction_id}),
            data={
                "category": self.income_category.id,
                "type": TransactionType.INCOME,
                "amount": "2000.00",
            },
            format="json",
        )

        self.assertEqual(update_response.status_code, status.HTTP_200_OK)

        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal("12000.00"))

    def test_delete_transaction_rolls_back_account_balance(self):
        self.authenticate()

        create_response = self.client.post(
            reverse("finance:transaction-list"),
            data={
                "account": self.account.id,
                "category": self.income_category.id,
                "type": TransactionType.INCOME,
                "amount": "3000.00",
                "description": "Доход для удаления",
                "operation_date": self.today,
            },
            format="json",
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)

        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal("13000.00"))

        transaction_id = create_response.data["id"]

        delete_response = self.client.delete(
            reverse("finance:transaction-detail", kwargs={"pk": transaction_id})
        )

        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)

        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal("10000.00"))

    def test_accounts_summary_reflects_transaction_balance_updates(self):
        self.authenticate()

        self.client.post(
            reverse("finance:transaction-list"),
            data={
                "account": self.account.id,
                "category": self.expense_category.id,
                "type": TransactionType.EXPENSE,
                "amount": "500.00",
                "description": "Расход для сводки",
                "operation_date": self.today,
            },
            format="json",
        )
        self.client.post(
            reverse("finance:transaction-list"),
            data={
                "account": self.cash_account.id,
                "category": self.income_category.id,
                "type": TransactionType.INCOME,
                "amount": "1000.00",
                "description": "Доход для сводки",
                "operation_date": self.today,
            },
            format="json",
        )

        response = self.client.get(
            reverse("finance:account-summary"),
            data={
                "currency": "RUB",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_balance"], "13500.00")
        self.assertEqual(response.data["totalBalanceRub"], "13500.00")

    def test_dashboard_summary_reflects_transaction_balance_updates(self):
        self.authenticate()

        self.client.post(
            reverse("finance:transaction-list"),
            data={
                "account": self.account.id,
                "category": self.expense_category.id,
                "type": TransactionType.EXPENSE,
                "amount": "500.00",
                "description": "Расход для dashboard",
                "operation_date": self.today,
            },
            format="json",
        )
        self.client.post(
            reverse("finance:transaction-list"),
            data={
                "account": self.cash_account.id,
                "category": self.income_category.id,
                "type": TransactionType.INCOME,
                "amount": "1000.00",
                "description": "Доход для dashboard",
                "operation_date": self.today,
            },
            format="json",
        )

        response = self.client.get(
            reverse("finance:dashboard-summary"),
            data={
                "currency": "RUB",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["totals"]["accounts_balance"],
            "13500.00",
        )
