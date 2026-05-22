from django.urls import reverse
from rest_framework import status

from apps.finance.models import Account, TransactionType

from .base import FinanceAPITestCase


class FinanceAccountValidationAPITests(FinanceAPITestCase):
    def test_create_account_with_duplicate_name_returns_bad_request(self):
        self.authenticate()

        response = self.client.post(
            reverse("finance:account-list"),
            data={
                "name": "Основная карта",
                "type": "card",
                "currency": "RUB",
                "initial_balance": "1000.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        self.assertIn("name", response.data["error"]["field_errors"])

    def test_create_account_with_duplicate_name_case_insensitive_returns_bad_request(self):
        self.authenticate()

        response = self.client.post(
            reverse("finance:account-list"),
            data={
                "name": "основная карта",
                "type": "card",
                "currency": "RUB",
                "initial_balance": "1000.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        self.assertIn("name", response.data["error"]["field_errors"])

    def test_update_account_to_duplicate_name_returns_bad_request(self):
        self.authenticate()

        response = self.client.patch(
            reverse("finance:account-detail", kwargs={"pk": self.cash_account.id}),
            data={
                "name": self.account.name,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        self.assertIn("name", response.data["error"]["field_errors"])

    def test_create_account_with_blank_name_returns_bad_request(self):
        self.authenticate()

        response = self.client.post(
            reverse("finance:account-list"),
            data={
                "name": "   ",
                "type": "card",
                "currency": "RUB",
                "initial_balance": "1000.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        self.assertIn("name", response.data["error"]["field_errors"])

    def test_create_account_normalizes_currency_to_uppercase(self):
        self.authenticate()

        response = self.client.post(
            reverse("finance:account-list"),
            data={
                "name": "USD счёт",
                "type": "card",
                "currency": "usd",
                "initial_balance": "1000.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["currency"], "USD")

        account = Account.objects.get(pk=response.data["id"])
        self.assertEqual(account.currency, "USD")

    def test_create_account_with_unsupported_currency_returns_bad_request(self):
        self.authenticate()

        response = self.client.post(
            reverse("finance:account-list"),
            data={
                "name": "Неподдерживаемая валюта",
                "type": "card",
                "currency": "ZZZ",
                "initial_balance": "1000.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        self.assertIn("currency", response.data["error"]["field_errors"])

    def test_create_account_with_invalid_type_returns_bad_request(self):
        self.authenticate()

        response = self.client.post(
            reverse("finance:account-list"),
            data={
                "name": "Неверный тип",
                "type": "wallet",
                "currency": "RUB",
                "initial_balance": "1000.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        self.assertIn("type", response.data["error"]["field_errors"])

    def test_create_account_with_invalid_color_returns_bad_request(self):
        self.authenticate()

        response = self.client.post(
            reverse("finance:account-list"),
            data={
                "name": "Неверный цвет",
                "type": "card",
                "currency": "RUB",
                "initial_balance": "1000.00",
                "color": "purple",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        self.assertIn("color", response.data["error"]["field_errors"])

    def test_create_account_with_negative_amounts_returns_bad_request(self):
        self.authenticate()

        invalid_cases = [
            ("initial_balance", "-1.00"),
            ("blocked_amount", "-1.00"),
            ("credit_limit", "-1.00"),
        ]

        for field_name, value in invalid_cases:
            with self.subTest(field_name=field_name):
                response = self.client.post(
                    reverse("finance:account-list"),
                    data={
                        "name": f"Неверное значение {field_name}",
                        "type": "card",
                        "currency": "RUB",
                        "initial_balance": "1000.00",
                        field_name: value,
                    },
                    format="json",
                )

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertFalse(response.data["success"])
                self.assertIn(field_name, response.data["error"]["field_errors"])

    def test_create_account_with_blocked_amount_greater_than_available_returns_bad_request(self):
        self.authenticate()

        response = self.client.post(
            reverse("finance:account-list"),
            data={
                "name": "Слишком большая блокировка",
                "type": "card",
                "currency": "RUB",
                "initial_balance": "1000.00",
                "blocked_amount": "1500.00",
                "credit_limit": "0.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        self.assertIn("blocked_amount", response.data["error"]["field_errors"])

    def test_invalid_account_list_filters_return_bad_request(self):
        self.authenticate()

        invalid_status_response = self.client.get(
            reverse("finance:account-list"),
            data={
                "status": "wrong",
            },
        )

        self.assertEqual(
            invalid_status_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertFalse(invalid_status_response.data["success"])
        self.assertIn(
            "status",
            invalid_status_response.data["error"]["field_errors"],
        )

        invalid_type_response = self.client.get(
            reverse("finance:account-list"),
            data={
                "type": "wrong",
            },
        )

        self.assertEqual(
            invalid_type_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertFalse(invalid_type_response.data["success"])
        self.assertIn(
            "type",
            invalid_type_response.data["error"]["field_errors"],
        )

        long_search_response = self.client.get(
            reverse("finance:account-list"),
            data={
                "search": "a" * 101,
            },
        )

        self.assertEqual(
            long_search_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertFalse(long_search_response.data["success"])
        self.assertIn(
            "search",
            long_search_response.data["error"]["field_errors"],
        )

    def test_delete_account_with_transactions_returns_conflict(self):
        self.authenticate()

        self.create_transaction(
            account=self.account,
            category=self.expense_category,
            type=TransactionType.EXPENSE,
            amount="100.00",
            description="Операция по счёту",
            operation_date=self.today,
        )

        response = self.client.delete(
            reverse("finance:account-detail", kwargs={"pk": self.account.id})
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertFalse(response.data["success"])

        error = response.data["error"]

        self.assertEqual(error["status_code"], status.HTTP_409_CONFLICT)
        self.assertEqual(error["code"], "account_has_transactions")
        self.assertEqual(error["detail"]["operations_count"], 1)

        self.account.refresh_from_db()
        self.assertIsNotNone(self.account.pk)

    def test_create_transaction_with_archived_account_returns_bad_request(self):
        self.authenticate()

        self.account.is_archived = True
        self.account.is_active = False
        self.account.save(update_fields=["is_archived", "is_active", "updated_at"])

        response = self.client.post(
            reverse("finance:transaction-list"),
            data={
                "account": self.account.id,
                "category": self.expense_category.id,
                "type": TransactionType.EXPENSE,
                "amount": "500.00",
                "description": "Операция на архивный счёт",
                "operation_date": self.today,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        self.assertIn("account", response.data["error"]["field_errors"])

    def test_update_transaction_to_archived_account_returns_bad_request(self):
        self.authenticate()

        create_response = self.client.post(
            reverse("finance:transaction-list"),
            data={
                "account": self.account.id,
                "category": self.expense_category.id,
                "type": TransactionType.EXPENSE,
                "amount": "500.00",
                "description": "Операция для проверки архива",
                "operation_date": self.today,
            },
            format="json",
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)

        self.cash_account.is_archived = True
        self.cash_account.is_active = False
        self.cash_account.save(
            update_fields=["is_archived", "is_active", "updated_at"]
        )

        response = self.client.patch(
            reverse(
                "finance:transaction-detail",
                kwargs={"pk": create_response.data["id"]},
            ),
            data={
                "account": self.cash_account.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        self.assertIn("account", response.data["error"]["field_errors"])

        self.account.refresh_from_db()
        self.cash_account.refresh_from_db()

        self.assertEqual(self.account.balance, self.account.initial_balance - 500)
        self.assertEqual(self.cash_account.balance, self.cash_account.initial_balance)
