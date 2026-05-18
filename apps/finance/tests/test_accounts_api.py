from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status

from apps.finance.models import Account, AccountType, TransactionType

from .base import FinanceAPITestCase


User = get_user_model()


class FinanceAccountsAPITests(FinanceAPITestCase):
    def test_account_list_requires_authentication(self):
        response = self.client.get(reverse("finance:account-list"))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(response.data["success"])

    def test_account_list_returns_only_current_user_accounts(self):
        self.authenticate()

        response = self.client.get(reverse("finance:account-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        account_ids = [item["id"] for item in response.data["results"]]

        self.assertIn(self.account.id, account_ids)
        self.assertIn(self.cash_account.id, account_ids)
        self.assertNotIn(self.other_account.id, account_ids)

    def test_account_list_returns_only_active_accounts_by_default(self):
        self.authenticate()

        archive_response = self.client.patch(
            reverse("finance:account-archive", kwargs={"pk": self.cash_account.id}),
            data={
                "archived": True,
            },
            format="json",
        )

        self.assertEqual(archive_response.status_code, status.HTTP_200_OK)

        self.cash_account.refresh_from_db()
        self.assertTrue(self.cash_account.is_archived)
        self.assertFalse(self.cash_account.is_active)

        response = self.client.get(reverse("finance:account-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        account_ids = [
            item["id"]
            for item in response.data["results"]
        ]

        self.assertIn(self.account.id, account_ids)
        self.assertNotIn(self.cash_account.id, account_ids)
        self.assertNotIn(self.other_account.id, account_ids)

    def test_account_list_can_return_archived_accounts(self):
        self.authenticate()

        self.cash_account.is_archived = True
        self.cash_account.is_active = False
        self.cash_account.save(update_fields=["is_archived", "is_active", "updated_at"])

        response = self.client.get(
            reverse("finance:account-list"),
            data={
                "status": "archived",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        account_ids = [item["id"] for item in response.data["results"]]

        self.assertEqual(account_ids, [self.cash_account.id])
        self.assertEqual(response.data["results"][0]["status"], "archived")

    def test_account_list_can_return_all_account_statuses(self):
        self.authenticate()

        self.cash_account.is_archived = True
        self.cash_account.is_active = False
        self.cash_account.save(update_fields=["is_archived", "is_active", "updated_at"])

        response = self.client.get(
            reverse("finance:account-list"),
            data={
                "status": "all",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        account_ids = [item["id"] for item in response.data["results"]]

        self.assertIn(self.account.id, account_ids)
        self.assertIn(self.cash_account.id, account_ids)
        self.assertNotIn(self.other_account.id, account_ids)

    def test_account_list_filters_by_type_currency_and_search(self):
        self.authenticate()

        target_account = Account.objects.create(
            user=self.user,
            name="Долларовая копилка",
            type=AccountType.SAVINGS,
            bank_name="Тинькофф",
            initial_balance=Decimal("1000.00"),
            balance=Decimal("1000.00"),
            currency="USD",
        )
        Account.objects.create(
            user=self.user,
            name="Евро карта",
            type=AccountType.CARD,
            bank_name="Сбербанк",
            initial_balance=Decimal("500.00"),
            balance=Decimal("500.00"),
            currency="EUR",
        )

        response = self.client.get(
            reverse("finance:account-list"),
            data={
                "type": AccountType.SAVINGS,
                "currency": "usd",
                "search": "копилка",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        account_ids = [item["id"] for item in response.data["results"]]

        self.assertEqual(account_ids, [target_account.id])
        self.assertEqual(response.data["results"][0]["currency"], "USD")
        self.assertEqual(response.data["results"][0]["type"], AccountType.SAVINGS)

    def test_create_account_success(self):
        self.authenticate()

        response = self.client.post(
            reverse("finance:account-list"),
            data={
                "name": "Накопительный счёт",
                "type": AccountType.SAVINGS,
                "bankName": "ВТБ",
                "currency": "RUB",
                "initialBalanceRub": "2500.00",
                "blocked_amount": "100.00",
                "credit_limit": "0.00",
                "icon": "bank",
                "color": "#10B981",
                "comment": "Счёт для накоплений",
                "isDefault": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "Накопительный счёт")
        self.assertEqual(response.data["type"], AccountType.SAVINGS)
        self.assertEqual(response.data["bank_name"], "ВТБ")
        self.assertEqual(response.data["bankName"], "ВТБ")
        self.assertEqual(response.data["currency"], "RUB")
        self.assertEqual(response.data["initial_balance"], "2500.00")
        self.assertEqual(response.data["initialBalanceRub"], "2500.00")
        self.assertEqual(response.data["balance"], "2500.00")
        self.assertEqual(response.data["balanceRub"], "2500.00")
        self.assertEqual(response.data["available_balance"], "2400.00")
        self.assertFalse(response.data["is_default"])
        self.assertFalse(response.data["isDefault"])

        created_account = Account.objects.get(pk=response.data["id"])
        self.assertEqual(created_account.user, self.user)
        self.assertEqual(created_account.balance, Decimal("2500.00"))
        self.assertEqual(created_account.initial_balance, Decimal("2500.00"))

    def test_first_created_account_becomes_default(self):
        new_user = User.objects.create_user(
            username="new-user",
            email="new-user@example.com",
            password="new-password-123",
        )
        self.client.force_authenticate(user=new_user)

        response = self.client.post(
            reverse("finance:account-list"),
            data={
                "name": "Первый счёт",
                "type": AccountType.CARD,
                "currency": "RUB",
                "initial_balance": "1000.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["is_default"])
        self.assertTrue(response.data["isDefault"])

        created_account = Account.objects.get(pk=response.data["id"])
        self.assertTrue(created_account.is_default)

    def test_new_default_account_resets_previous_default(self):
        self.authenticate()

        self.account.is_default = True
        self.account.save(update_fields=["is_default", "updated_at"])

        response = self.client.post(
            reverse("finance:account-list"),
            data={
                "name": "Новый основной счёт",
                "type": AccountType.CARD,
                "currency": "RUB",
                "initial_balance": "1000.00",
                "isDefault": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["is_default"])

        self.account.refresh_from_db()
        created_account = Account.objects.get(pk=response.data["id"])

        self.assertFalse(self.account.is_default)
        self.assertTrue(created_account.is_default)

    def test_retrieve_account_detail_success(self):
        self.authenticate()

        self.create_transaction(
            account=self.account,
            category=self.expense_category,
            type=TransactionType.EXPENSE,
            amount="100.00",
            description="Операция для detail",
            operation_date=self.today,
        )

        response = self.client.get(
            reverse("finance:account-detail", kwargs={"pk": self.account.id})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.account.id)
        self.assertEqual(response.data["name"], self.account.name)
        self.assertEqual(response.data["operations_count"], 1)
        self.assertEqual(response.data["operationsCount"], 1)

    def test_retrieve_other_user_account_returns_not_found(self):
        self.authenticate()

        response = self.client.get(
            reverse("finance:account-detail", kwargs={"pk": self.other_account.id})
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(response.data["success"])

    def test_partial_update_account_success(self):
        self.authenticate()

        response = self.client.patch(
            reverse("finance:account-detail", kwargs={"pk": self.cash_account.id}),
            data={
                "name": "Обновлённые наличные",
                "type": AccountType.CASH,
                "bankName": "",
                "comment": "  Деньги дома  ",
                "isDefault": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Обновлённые наличные")
        self.assertEqual(response.data["type"], AccountType.CASH)
        self.assertEqual(response.data["comment"], "Деньги дома")
        self.assertTrue(response.data["is_default"])
        self.assertTrue(response.data["isDefault"])

        self.cash_account.refresh_from_db()
        self.account.refresh_from_db()

        self.assertTrue(self.cash_account.is_default)
        self.assertFalse(self.account.is_default)

    def test_archive_account_and_restore_account_success(self):
        self.authenticate()

        archive_response = self.client.patch(
            reverse("finance:account-archive", kwargs={"pk": self.cash_account.id}),
            data={
                "archived": True,
            },
            format="json",
        )

        self.assertEqual(archive_response.status_code, status.HTTP_200_OK)
        self.assertTrue(archive_response.data["is_archived"])
        self.assertFalse(archive_response.data["is_active"])
        self.assertEqual(archive_response.data["status"], "archived")

        self.cash_account.refresh_from_db()
        self.assertTrue(self.cash_account.is_archived)
        self.assertFalse(self.cash_account.is_active)

        restore_response = self.client.patch(
            reverse("finance:account-archive", kwargs={"pk": self.cash_account.id}),
            data={
                "archived": False,
            },
            format="json",
        )

        self.assertEqual(restore_response.status_code, status.HTTP_200_OK)
        self.assertFalse(restore_response.data["is_archived"])
        self.assertTrue(restore_response.data["is_active"])
        self.assertEqual(restore_response.data["status"], "active")

        self.cash_account.refresh_from_db()
        self.assertFalse(self.cash_account.is_archived)
        self.assertTrue(self.cash_account.is_active)

    def test_account_summary_success(self):
        self.authenticate()

        self.cash_account.is_archived = True
        self.cash_account.is_active = False
        self.cash_account.save(update_fields=["is_archived", "is_active", "updated_at"])

        response = self.client.get(
            reverse("finance:account-summary"),
            data={
                "currency": "RUB",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_balance"], "10000.00")
        self.assertEqual(response.data["totalBalanceRub"], "10000.00")
        self.assertEqual(response.data["active_count"], 1)
        self.assertEqual(response.data["archived_count"], 1)
        self.assertEqual(response.data["currency"], "RUB")

    def test_account_meta_success(self):
        self.authenticate()

        response = self.client.get(reverse("finance:account-meta"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("types", response.data)
        self.assertIn("banks", response.data)
        self.assertIn("currencies", response.data)

        type_values = [item["value"] for item in response.data["types"]]
        currency_values = [item["value"] for item in response.data["currencies"]]

        self.assertIn(AccountType.CARD, type_values)
        self.assertIn(AccountType.SAVINGS, type_values)
        self.assertIn("RUB", currency_values)
        self.assertIn("USD", currency_values)
        self.assertIn("EUR", currency_values)

    def test_account_history_returns_only_selected_account_transactions(self):
        self.authenticate()

        target_transaction = self.create_transaction(
            account=self.account,
            category=self.expense_category,
            type=TransactionType.EXPENSE,
            amount="100.00",
            description="Операция выбранного счёта",
            operation_date=self.today,
        )
        self.create_transaction(
            account=self.cash_account,
            category=self.transport_category,
            type=TransactionType.EXPENSE,
            amount="200.00",
            description="Операция другого счёта",
            operation_date=self.today,
        )
        self.create_transaction(
            user=self.other_user,
            account=self.other_account,
            category=self.other_category,
            type=TransactionType.EXPENSE,
            amount="300.00",
            description="Чужая операция",
            operation_date=self.today,
        )

        response = self.client.get(
            reverse("finance:account-history", kwargs={"pk": self.account.id})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        history_ids = [item["id"] for item in response.data["results"]]

        self.assertEqual(history_ids, [target_transaction.id])
        self.assertEqual(
            response.data["results"][0]["description"],
            "Операция выбранного счёта",
        )
        self.assertEqual(response.data["results"][0]["category_name"], "Продукты")
        self.assertEqual(response.data["results"][0]["signed_amount"], "-100.00")

    def test_destroy_account_without_transactions_success(self):
        self.authenticate()

        account = Account.objects.create(
            user=self.user,
            name="Пустой счёт",
            type=AccountType.CARD,
            initial_balance=Decimal("0.00"),
            balance=Decimal("0.00"),
            currency="RUB",
        )

        response = self.client.delete(
            reverse("finance:account-detail", kwargs={"pk": account.id})
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Account.objects.filter(pk=account.id).exists())

    def test_destroy_other_user_account_returns_not_found(self):
        self.authenticate()

        response = self.client.delete(
            reverse("finance:account-detail", kwargs={"pk": self.other_account.id})
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(response.data["success"])
