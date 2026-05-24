import csv
from decimal import Decimal
from io import BytesIO, StringIO
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook
from rest_framework import status

from apps.finance.models import Account, Budget, Category, Transaction, TransactionLineItem, TransactionType

from apps.finance.testing import FinanceAPITestCase


class FinanceTransactionAPITests(FinanceAPITestCase):
    def test_transaction_rejects_archived_category(self):
            self.authenticate()

            self.expense_category.is_archived = True
            self.expense_category.save(update_fields=["is_archived"])

            response = self.client.post(
                reverse("finance:transaction-list"),
                data={
                    "account": self.account.id,
                    "category": self.expense_category.id,
                    "type": TransactionType.EXPENSE,
                    "amount": "100.00",
                    "description": "Архивная категория",
                    "operation_date": str(self.today),
                },
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertFalse(response.data["success"])
            self.assertIn("category", response.data["error"]["field_errors"])

    def test_transaction_history_keeps_archived_category(self):
            self.authenticate()

            transaction = self.create_transaction(
                category=self.expense_category,
                amount="250.00",
                description="Операция до архивации",
                operation_date=self.today,
            )

            self.expense_category.is_archived = True
            self.expense_category.save(update_fields=["is_archived"])

            list_response = self.client.get(
                reverse("finance:transaction-list"),
                data={
                    "category": self.expense_category.id,
                    "page_size": 20,
                },
            )

            self.assertEqual(list_response.status_code, status.HTTP_200_OK)
            self.assertEqual(list_response.data["count"], 1)
            self.assertEqual(
                self.get_transaction_ids(list_response),
                [transaction.id],
            )

            detail_response = self.client.get(
                reverse("finance:transaction-detail", kwargs={"pk": transaction.id})
            )

            self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
            self.assertEqual(detail_response.data["category"], self.expense_category.id)

    def test_transaction_with_archived_category_can_update_non_category_fields(self):
            self.authenticate()

            transaction = self.create_transaction(
                category=self.expense_category,
                amount="250.00",
                description="До обновления",
                operation_date=self.today,
            )

            self.expense_category.is_archived = True
            self.expense_category.save(update_fields=["is_archived"])

            response = self.client.patch(
                reverse("finance:transaction-detail", kwargs={"pk": transaction.id}),
                data={
                    "description": "После обновления",
                },
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["description"], "После обновления")

            transaction.refresh_from_db()
            self.assertEqual(transaction.category_id, self.expense_category.id)

    def test_transactions_list_requires_authentication(self):
            response = self.client.get(reverse("finance:transaction-list"))

            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
            self.assertFalse(response.data["success"])
            self.assertEqual(response.data["error"]["status_code"], 401)

    def test_transaction_crud_success_flow(self):
            self.authenticate()

            create_response = self.client.post(
                reverse("finance:transaction-list"),
                data={
                    "account": self.account.id,
                    "category": self.expense_category.id,
                    "type": TransactionType.EXPENSE,
                    "amount": "1500.00",
                    "description": "Тестовая операция",
                    "operation_date": str(self.today),
                },
                format="json",
            )

            self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
            transaction_id = create_response.data["id"]

            list_response = self.client.get(reverse("finance:transaction-list"))

            self.assertEqual(list_response.status_code, status.HTTP_200_OK)
            self.assertEqual(list_response.data["count"], 1)
            self.assertEqual(len(list_response.data["results"]), 1)

            detail_response = self.client.get(
                reverse("finance:transaction-detail", kwargs={"pk": transaction_id})
            )

            self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
            self.assertEqual(detail_response.data["description"], "Тестовая операция")

            update_response = self.client.patch(
                reverse("finance:transaction-detail", kwargs={"pk": transaction_id}),
                data={
                    "description": "Обновленная операция",
                },
                format="json",
            )

            self.assertEqual(update_response.status_code, status.HTTP_200_OK)
            self.assertEqual(update_response.data["description"], "Обновленная операция")

            delete_response = self.client.delete(
                reverse("finance:transaction-detail", kwargs={"pk": transaction_id})
            )

            self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)
            self.assertFalse(Transaction.objects.filter(pk=transaction_id).exists())

    def test_transaction_put_full_update_success(self):
            self.authenticate()

            transaction = self.create_transaction(
                account=self.account,
                category=self.expense_category,
                type=TransactionType.EXPENSE,
                amount="1000.00",
                description="До полного обновления",
                operation_date=self.today,
            )

            response = self.client.put(
                reverse("finance:transaction-detail", kwargs={"pk": transaction.id}),
                data={
                    "account": self.cash_account.id,
                    "category": self.transport_category.id,
                    "type": TransactionType.EXPENSE,
                    "amount": "350.00",
                    "description": "Такси после полного обновления",
                    "operation_date": str(self.today - timezone.timedelta(days=1)),
                },
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["id"], transaction.id)
            self.assertEqual(response.data["account"], self.cash_account.id)
            self.assertEqual(response.data["account_name"], self.cash_account.name)
            self.assertEqual(response.data["category"], self.transport_category.id)
            self.assertEqual(response.data["category_name"], self.transport_category.name)
            self.assertEqual(response.data["type"], TransactionType.EXPENSE)
            self.assertEqual(response.data["kind"], TransactionType.EXPENSE)
            self.assertEqual(response.data["amount"], "350.00")
            self.assertEqual(response.data["amount_abs"], "350.00")
            self.assertEqual(response.data["signed_amount"], "-350.00")
            self.assertEqual(response.data["description"], "Такси после полного обновления")
            self.assertEqual(
                response.data["operation_date"],
                str(self.today - timezone.timedelta(days=1)),
            )

            transaction.refresh_from_db()

            self.assertEqual(transaction.account_id, self.cash_account.id)
            self.assertEqual(transaction.category_id, self.transport_category.id)
            self.assertEqual(transaction.amount, Decimal("350.00"))
            self.assertEqual(transaction.description, "Такси после полного обновления")
            self.assertEqual(
                transaction.operation_date,
                self.today - timezone.timedelta(days=1),
            )

    def test_transaction_put_full_update_does_not_allow_foreign_transaction(self):
            self.authenticate()

            foreign_transaction = self.create_transaction(
                user=self.other_user,
                account=self.other_account,
                category=self.other_category,
                type=TransactionType.EXPENSE,
                amount="999.00",
                description="Чужая операция до PUT",
                operation_date=self.today,
            )

            response = self.client.put(
                reverse(
                    "finance:transaction-detail",
                    kwargs={"pk": foreign_transaction.id},
                ),
                data={
                    "account": self.account.id,
                    "category": self.expense_category.id,
                    "type": TransactionType.EXPENSE,
                    "amount": "100.00",
                    "description": "Попытка изменить чужую операцию",
                    "operation_date": str(self.today),
                },
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
            self.assertFalse(response.data["success"])

            foreign_transaction.refresh_from_db()

            self.assertEqual(foreign_transaction.amount, Decimal("999.00"))
            self.assertEqual(foreign_transaction.description, "Чужая операция до PUT")

    def test_transaction_patch_does_not_allow_foreign_transaction(self):
            self.authenticate()

            foreign_transaction = self.create_transaction(
                user=self.other_user,
                account=self.other_account,
                category=self.other_category,
                type=TransactionType.EXPENSE,
                amount="999.00",
                description="Чужая операция до PATCH",
                operation_date=self.today,
            )

            response = self.client.patch(
                reverse(
                    "finance:transaction-detail",
                    kwargs={"pk": foreign_transaction.id},
                ),
                data={
                    "description": "Попытка изменить чужую операцию",
                },
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
            self.assertFalse(response.data["success"])

            foreign_transaction.refresh_from_db()

            self.assertEqual(foreign_transaction.description, "Чужая операция до PATCH")

    def test_transaction_delete_does_not_allow_foreign_transaction(self):
            self.authenticate()

            foreign_transaction = self.create_transaction(
                user=self.other_user,
                account=self.other_account,
                category=self.other_category,
                type=TransactionType.EXPENSE,
                amount="999.00",
                description="Чужая операция для удаления",
                operation_date=self.today,
            )

            response = self.client.delete(
                reverse(
                    "finance:transaction-detail",
                    kwargs={"pk": foreign_transaction.id},
                )
            )

            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
            self.assertFalse(response.data["success"])
            self.assertTrue(Transaction.objects.filter(pk=foreign_transaction.id).exists())

    def test_transaction_detail_does_not_return_foreign_transaction(self):
            self.authenticate()

            foreign_transaction = self.create_transaction(
                user=self.other_user,
                account=self.other_account,
                category=self.other_category,
                type=TransactionType.EXPENSE,
                amount="999.00",
                description="Чужая операция",
                operation_date=self.today,
            )

            response = self.client.get(
                reverse(
                    "finance:transaction-detail",
                    kwargs={"pk": foreign_transaction.id},
                )
            )

            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
            self.assertFalse(response.data["success"])

    def test_transaction_patch_rejects_foreign_account(self):
            self.authenticate()

            transaction = self.create_transaction(
                account=self.account,
                category=self.expense_category,
                type=TransactionType.EXPENSE,
                amount="100.00",
                description="До смены счёта",
                operation_date=self.today,
            )

            response = self.client.patch(
                reverse("finance:transaction-detail", kwargs={"pk": transaction.id}),
                data={
                    "account": self.other_account.id,
                },
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertFalse(response.data["success"])
            self.assertIn("account", response.data["error"]["field_errors"])

            transaction.refresh_from_db()

            self.assertEqual(transaction.account_id, self.account.id)

    def test_transaction_patch_rejects_foreign_category(self):
            self.authenticate()

            transaction = self.create_transaction(
                account=self.account,
                category=self.expense_category,
                type=TransactionType.EXPENSE,
                amount="100.00",
                description="До смены категории",
                operation_date=self.today,
            )

            response = self.client.patch(
                reverse("finance:transaction-detail", kwargs={"pk": transaction.id}),
                data={
                    "category": self.other_category.id,
                },
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertFalse(response.data["success"])
            self.assertIn("category", response.data["error"]["field_errors"])

            transaction.refresh_from_db()

            self.assertEqual(transaction.category_id, self.expense_category.id)

    def test_transaction_patch_rejects_category_type_mismatch(self):
            self.authenticate()

            transaction = self.create_transaction(
                account=self.account,
                category=self.expense_category,
                type=TransactionType.EXPENSE,
                amount="100.00",
                description="До некорректной категории",
                operation_date=self.today,
            )

            response = self.client.patch(
                reverse("finance:transaction-detail", kwargs={"pk": transaction.id}),
                data={
                    "category": self.income_category.id,
                },
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertFalse(response.data["success"])
            self.assertIn("category", response.data["error"]["field_errors"])

            transaction.refresh_from_db()

            self.assertEqual(transaction.category_id, self.expense_category.id)
            self.assertEqual(transaction.type, TransactionType.EXPENSE)

    def test_transaction_rejects_foreign_account(self):
            self.authenticate()

            response = self.client.post(
                reverse("finance:transaction-list"),
                data={
                    "account": self.other_account.id,
                    "category": self.expense_category.id,
                    "type": TransactionType.EXPENSE,
                    "amount": "100.00",
                    "description": "Попытка использовать чужой счет",
                    "operation_date": str(self.today),
                },
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertFalse(response.data["success"])
            self.assertIn("account", response.data["error"]["field_errors"])

    def test_transaction_rejects_foreign_category(self):
            self.authenticate()

            response = self.client.post(
                reverse("finance:transaction-list"),
                data={
                    "account": self.account.id,
                    "category": self.other_category.id,
                    "type": TransactionType.EXPENSE,
                    "amount": "100.00",
                    "description": "Попытка использовать чужую категорию",
                    "operation_date": str(self.today),
                },
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertFalse(response.data["success"])
            self.assertIn("category", response.data["error"]["field_errors"])

    def test_transaction_rejects_category_type_mismatch(self):
            self.authenticate()

            response = self.client.post(
                reverse("finance:transaction-list"),
                data={
                    "account": self.account.id,
                    "category": self.income_category.id,
                    "type": TransactionType.EXPENSE,
                    "amount": "100.00",
                    "description": "Несовпадение типа категории",
                    "operation_date": str(self.today),
                },
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertFalse(response.data["success"])
            self.assertIn("category", response.data["error"]["field_errors"])

    def test_transaction_rejects_inactive_account(self):
            self.authenticate()
            self.account.is_active = False
            self.account.save(update_fields=["is_active"])

            response = self.client.post(
                reverse("finance:transaction-list"),
                data={
                    "account": self.account.id,
                    "category": self.expense_category.id,
                    "type": TransactionType.EXPENSE,
                    "amount": "100.00",
                    "description": "Неактивный счет",
                    "operation_date": str(self.today),
                },
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertFalse(response.data["success"])
            self.assertIn("account", response.data["error"]["field_errors"])

    def test_transaction_rejects_inactive_category(self):
            self.authenticate()
            self.expense_category.is_active = False
            self.expense_category.save(update_fields=["is_active"])

            response = self.client.post(
                reverse("finance:transaction-list"),
                data={
                    "account": self.account.id,
                    "category": self.expense_category.id,
                    "type": TransactionType.EXPENSE,
                    "amount": "100.00",
                    "description": "Неактивная категория",
                    "operation_date": str(self.today),
                },
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertFalse(response.data["success"])
            self.assertIn("category", response.data["error"]["field_errors"])

    def test_transactions_list_uses_pagination_format(self):
            self.authenticate()

            for index in range(25):
                self.create_transaction(
                    amount=str(Decimal("100.00") + index),
                    description=f"Операция {index}",
                    operation_date=self.today - timezone.timedelta(days=index),
                )

            response = self.client.get(
                reverse("finance:transaction-list"),
                data={
                    "page": 1,
                    "page_size": 10,
                },
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["count"], 25)
            self.assertIsNotNone(response.data["next"])
            self.assertIsNone(response.data["previous"])
            self.assertEqual(len(response.data["results"]), 10)

    def test_transactions_list_limits_page_size_to_max_value(self):
            self.authenticate()

            for index in range(105):
                self.create_transaction(
                    amount=str(Decimal("100.00") + index),
                    description=f"Операция {index}",
                    operation_date=self.today - timezone.timedelta(days=index),
                )

            response = self.client.get(
                reverse("finance:transaction-list"),
                data={
                    "page": 1,
                    "page_size": 1000,
                },
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["count"], 105)
            self.assertEqual(len(response.data["results"]), 100)

    def test_transactions_list_avoids_n_plus_one_queries(self):
            self.authenticate()

            for index in range(20):
                category = (
                    self.expense_category
                    if index % 2 == 0
                    else self.transport_category
                )
                account = (
                    self.account
                    if index % 2 == 0
                    else self.cash_account
                )

                self.create_transaction(
                    account=account,
                    category=category,
                    type=TransactionType.EXPENSE,
                    amount=str(Decimal("100.00") + index),
                    description=f"Операция N+1 {index}",
                    operation_date=self.today - timezone.timedelta(days=index),
                )

            with CaptureQueriesContext(connection) as captured_queries:
                response = self.client.get(
                    reverse("finance:transaction-list"),
                    data={
                        "page": 1,
                        "page_size": 20,
                    },
                )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["count"], 20)
            self.assertEqual(len(response.data["results"]), 20)

            for item in response.data["results"]:
                self.assertIn("account_name", item)
                self.assertIn("account_currency", item)
                self.assertIn("category_name", item)
                self.assertIn("category_icon", item)
                self.assertIn("category_color", item)

            self.assertLessEqual(len(captured_queries), 5)

    def test_transactions_filtered_list_avoids_n_plus_one_queries(self):
            self.authenticate()

            for index in range(30):
                category = (
                    self.expense_category
                    if index % 2 == 0
                    else self.transport_category
                )
                account = (
                    self.account
                    if index % 2 == 0
                    else self.cash_account
                )

                self.create_transaction(
                    account=account,
                    category=category,
                    type=TransactionType.EXPENSE,
                    amount=str(Decimal("100.00") + index),
                    description=(
                        "Магазин продукты"
                        if index % 2 == 0
                        else "Такси транспорт"
                    ),
                    operation_date=self.today - timezone.timedelta(days=index),
                )

            with CaptureQueriesContext(connection) as captured_queries:
                response = self.client.get(
                    reverse("finance:transaction-list"),
                    data={
                        "kind": TransactionType.EXPENSE,
                        "accountId": self.account.id,
                        "categoryId": self.expense_category.id,
                        "dateFrom": str(self.today - timezone.timedelta(days=30)),
                        "dateTo": str(self.today),
                        "amountMin": "100.00",
                        "amountMax": "200.00",
                        "search": "магазин",
                        "sortBy": "date",
                        "sortDir": "desc",
                        "page_size": 20,
                    },
                )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertGreaterEqual(response.data["count"], 1)

            for item in response.data["results"]:
                self.assertEqual(item["account"], self.account.id)
                self.assertEqual(item["category"], self.expense_category.id)
                self.assertEqual(item["type"], TransactionType.EXPENSE)
                self.assertIn("магазин", item["description"].lower())

            self.assertLessEqual(len(captured_queries), 5)

    def test_transaction_detail_uses_related_account_and_category_without_extra_queries(self):
            self.authenticate()

            transaction = self.create_transaction(
                account=self.account,
                category=self.expense_category,
                type=TransactionType.EXPENSE,
                amount="1245.00",
                description="Покупка продуктов",
                operation_date=self.today,
            )

            with CaptureQueriesContext(connection) as captured_queries:
                response = self.client.get(
                    reverse("finance:transaction-detail", kwargs={"pk": transaction.id})
                )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["id"], transaction.id)
            self.assertEqual(response.data["account_name"], self.account.name)
            self.assertEqual(response.data["category_name"], self.expense_category.name)

            self.assertLessEqual(len(captured_queries), 4)

    def test_transaction_filters_by_type_category_account(self):
            self.authenticate()

            expense_transaction = self.create_transaction(
                account=self.account,
                category=self.expense_category,
                type=TransactionType.EXPENSE,
                amount="300.00",
                description="Магазин продукты",
                operation_date=self.today,
            )
            transport_transaction = self.create_transaction(
                account=self.cash_account,
                category=self.transport_category,
                type=TransactionType.EXPENSE,
                amount="500.00",
                description="Такси",
                operation_date=self.today,
            )
            income_transaction = self.create_transaction(
                account=self.account,
                category=self.income_category,
                type=TransactionType.INCOME,
                amount="50000.00",
                description="Зарплата",
                operation_date=self.today,
            )

            self.create_transaction(
                user=self.other_user,
                account=self.other_account,
                category=self.other_category,
                type=TransactionType.EXPENSE,
                amount="999.00",
                description="Чужая операция",
                operation_date=self.today,
            )

            type_response = self.client.get(
                reverse("finance:transaction-list"),
                data={
                    "type": TransactionType.EXPENSE,
                    "page_size": 20,
                },
            )

            self.assertEqual(type_response.status_code, status.HTTP_200_OK)
            self.assertEqual(type_response.data["count"], 2)
            self.assertEqual(
                set(self.get_transaction_ids(type_response)),
                {expense_transaction.id, transport_transaction.id},
            )
            self.assertNotIn(income_transaction.id, self.get_transaction_ids(type_response))

            category_response = self.client.get(
                reverse("finance:transaction-list"),
                data={
                    "category": self.expense_category.id,
                    "page_size": 20,
                },
            )

            self.assertEqual(category_response.status_code, status.HTTP_200_OK)
            self.assertEqual(category_response.data["count"], 1)
            self.assertEqual(
                self.get_transaction_ids(category_response),
                [expense_transaction.id],
            )

            account_response = self.client.get(
                reverse("finance:transaction-list"),
                data={
                    "account": self.cash_account.id,
                    "page_size": 20,
                },
            )

            self.assertEqual(account_response.status_code, status.HTTP_200_OK)
            self.assertEqual(account_response.data["count"], 1)
            self.assertEqual(
                self.get_transaction_ids(account_response),
                [transport_transaction.id],
            )

    def test_transaction_filters_by_dates_amounts_and_search(self):
            self.authenticate()

            old_transaction = self.create_transaction(
                amount="50.00",
                description="Старая операция",
                operation_date=self.today - timezone.timedelta(days=10),
            )
            target_transaction = self.create_transaction(
                amount="250.00",
                description="Магазин продукты",
                operation_date=self.today - timezone.timedelta(days=3),
            )
            expensive_transaction = self.create_transaction(
                amount="700.00",
                description="Магазин техника",
                operation_date=self.today - timezone.timedelta(days=1),
            )

            response = self.client.get(
                reverse("finance:transaction-list"),
                data={
                    "date_from": str(self.today - timezone.timedelta(days=5)),
                    "date_to": str(self.today),
                    "amount_min": "100.00",
                    "amount_max": "500.00",
                    "search": "магазин",
                    "page_size": 20,
                },
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["count"], 1)
            self.assertEqual(self.get_transaction_ids(response), [target_transaction.id])
            self.assertNotIn(old_transaction.id, self.get_transaction_ids(response))
            self.assertNotIn(expensive_transaction.id, self.get_transaction_ids(response))

    def test_transaction_ordering_by_single_and_multiple_fields(self):
            self.authenticate()

            high_today_transaction = self.create_transaction(
                amount="300.00",
                description="B operation",
                operation_date=self.today,
            )
            low_today_transaction = self.create_transaction(
                amount="100.00",
                description="A operation",
                operation_date=self.today,
            )
            old_transaction = self.create_transaction(
                amount="200.00",
                description="C operation",
                operation_date=self.today - timezone.timedelta(days=1),
            )

            amount_response = self.client.get(
                reverse("finance:transaction-list"),
                data={
                    "ordering": "amount",
                    "page_size": 20,
                },
            )

            self.assertEqual(amount_response.status_code, status.HTTP_200_OK)
            self.assertEqual(
                self.get_transaction_ids(amount_response),
                [
                    low_today_transaction.id,
                    old_transaction.id,
                    high_today_transaction.id,
                ],
            )

            multiple_ordering_response = self.client.get(
                reverse("finance:transaction-list"),
                data={
                    "ordering": "-operation_date,amount",
                    "page_size": 20,
                },
            )

            self.assertEqual(multiple_ordering_response.status_code, status.HTTP_200_OK)
            self.assertEqual(
                self.get_transaction_ids(multiple_ordering_response),
                [
                    low_today_transaction.id,
                    high_today_transaction.id,
                    old_transaction.id,
                ],
            )

    def test_transaction_ordering_by_category_name(self):
            self.authenticate()

            alpha_category = Category.objects.create(
                user=self.user,
                name="Alpha",
                type=TransactionType.EXPENSE,
            )
            beta_category = Category.objects.create(
                user=self.user,
                name="Beta",
                type=TransactionType.EXPENSE,
            )

            beta_transaction = self.create_transaction(
                category=beta_category,
                amount="100.00",
                description="Beta category transaction",
            )
            alpha_transaction = self.create_transaction(
                category=alpha_category,
                amount="200.00",
                description="Alpha category transaction",
            )

            response = self.client.get(
                reverse("finance:transaction-list"),
                data={
                    "ordering": "category",
                    "page_size": 20,
                },
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(
                self.get_transaction_ids(response),
                [
                    alpha_transaction.id,
                    beta_transaction.id,
                ],
            )

    def test_transaction_list_response_contains_frontend_read_fields(self):
            self.authenticate()

            expense_transaction = self.create_transaction(
                account=self.account,
                category=self.expense_category,
                type=TransactionType.EXPENSE,
                amount="1245.00",
                description="Покупка продуктов",
                operation_date=self.today,
            )
            income_transaction = self.create_transaction(
                account=self.account,
                category=self.income_category,
                type=TransactionType.INCOME,
                amount="50000.00",
                description="Зарплата за май",
                operation_date=self.today,
            )

            expense_response = self.client.get(
                reverse("finance:transaction-list"),
                data={
                    "category": self.expense_category.id,
                    "page_size": 20,
                },
            )

            self.assertEqual(expense_response.status_code, status.HTTP_200_OK)
            self.assertEqual(expense_response.data["count"], 1)

            expense_item = expense_response.data["results"][0]

            self.assertEqual(expense_item["id"], expense_transaction.id)
            self.assertEqual(expense_item["account"], self.account.id)
            self.assertEqual(expense_item["account_name"], self.account.name)
            self.assertEqual(expense_item["account_currency"], self.account.currency)
            self.assertEqual(expense_item["category"], self.expense_category.id)
            self.assertEqual(expense_item["category_name"], self.expense_category.name)
            self.assertEqual(expense_item["category_icon"], self.expense_category.icon)
            self.assertEqual(expense_item["category_color"], self.expense_category.color)
            self.assertEqual(expense_item["type"], TransactionType.EXPENSE)
            self.assertEqual(expense_item["kind"], TransactionType.EXPENSE)
            self.assertEqual(expense_item["amount"], "1245.00")
            self.assertEqual(expense_item["amount_abs"], "1245.00")
            self.assertEqual(expense_item["signed_amount"], "-1245.00")
            self.assertEqual(expense_item["operation_date"], str(self.today))
            self.assertEqual(expense_item["date"], str(self.today))

            income_response = self.client.get(
                reverse("finance:transaction-list"),
                data={
                    "category": self.income_category.id,
                    "page_size": 20,
                },
            )

            self.assertEqual(income_response.status_code, status.HTTP_200_OK)
            self.assertEqual(income_response.data["count"], 1)

            income_item = income_response.data["results"][0]

            self.assertEqual(income_item["id"], income_transaction.id)
            self.assertEqual(income_item["type"], TransactionType.INCOME)
            self.assertEqual(income_item["kind"], TransactionType.INCOME)
            self.assertEqual(income_item["amount_abs"], "50000.00")
            self.assertEqual(income_item["signed_amount"], "50000.00")

    def test_transactions_list_accepts_limit_as_page_size_alias(self):
            self.authenticate()

            for index in range(7):
                self.create_transaction(
                    amount=str(Decimal("100.00") + index),
                    description=f"Операция limit {index}",
                    operation_date=self.today - timezone.timedelta(days=index),
                )

            response = self.client.get(
                reverse("finance:transaction-list"),
                data={
                    "page": 1,
                    "limit": 3,
                },
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["count"], 7)
            self.assertIsNotNone(response.data["next"])
            self.assertIsNone(response.data["previous"])
            self.assertEqual(len(response.data["results"]), 3)

    def test_transaction_filters_accept_frontend_aliases(self):
            self.authenticate()

            target_transaction = self.create_transaction(
                account=self.cash_account,
                category=self.transport_category,
                type=TransactionType.EXPENSE,
                amount="350.00",
                description="Такси до университета",
                operation_date=self.today - timezone.timedelta(days=2),
            )
            self.create_transaction(
                account=self.account,
                category=self.expense_category,
                type=TransactionType.EXPENSE,
                amount="350.00",
                description="Покупка продуктов",
                operation_date=self.today - timezone.timedelta(days=2),
            )
            self.create_transaction(
                account=self.cash_account,
                category=self.transport_category,
                type=TransactionType.EXPENSE,
                amount="900.00",
                description="Дорогая поездка",
                operation_date=self.today - timezone.timedelta(days=2),
            )
            self.create_transaction(
                account=self.cash_account,
                category=self.income_category,
                type=TransactionType.INCOME,
                amount="350.00",
                description="Возврат денег",
                operation_date=self.today - timezone.timedelta(days=2),
            )

            response = self.client.get(
                reverse("finance:transaction-list"),
                data={
                    "kind": TransactionType.EXPENSE,
                    "accountId": self.cash_account.id,
                    "categoryId": self.transport_category.id,
                    "dateFrom": str(self.today - timezone.timedelta(days=5)),
                    "dateTo": str(self.today),
                    "amountMin": "100.00",
                    "amountMax": "500.00",
                    "page_size": 20,
                },
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["count"], 1)
            self.assertEqual(self.get_transaction_ids(response), [target_transaction.id])

    def test_transaction_kind_all_returns_income_and_expense_transactions(self):
            self.authenticate()

            expense_transaction = self.create_transaction(
                type=TransactionType.EXPENSE,
                amount="100.00",
                description="Расход",
                operation_date=self.today,
            )
            income_transaction = self.create_transaction(
                category=self.income_category,
                type=TransactionType.INCOME,
                amount="50000.00",
                description="Доход",
                operation_date=self.today,
            )
            self.create_transaction(
                user=self.other_user,
                account=self.other_account,
                category=self.other_category,
                type=TransactionType.EXPENSE,
                amount="999.00",
                description="Чужая операция",
                operation_date=self.today,
            )

            response = self.client.get(
                reverse("finance:transaction-list"),
                data={
                    "kind": "all",
                    "page_size": 20,
                },
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["count"], 2)
            self.assertEqual(
                set(self.get_transaction_ids(response)),
                {expense_transaction.id, income_transaction.id},
            )

    def test_transaction_searches_by_description_category_and_account_name(self):
            self.authenticate()

            transport_transaction = self.create_transaction(
                account=self.cash_account,
                category=self.transport_category,
                type=TransactionType.EXPENSE,
                amount="350.00",
                description="Поездка",
                operation_date=self.today,
            )
            product_transaction = self.create_transaction(
                account=self.account,
                category=self.expense_category,
                type=TransactionType.EXPENSE,
                amount="600.00",
                description="Покупка",
                operation_date=self.today,
            )

            account_response = self.client.get(
                reverse("finance:transaction-list"),
                data={
                    "search": "наличные",
                    "page_size": 20,
                },
            )

            self.assertEqual(account_response.status_code, status.HTTP_200_OK)
            self.assertEqual(account_response.data["count"], 1)
            self.assertEqual(
                self.get_transaction_ids(account_response),
                [transport_transaction.id],
            )

            category_response = self.client.get(
                reverse("finance:transaction-list"),
                data={
                    "search": "продукты",
                    "page_size": 20,
                },
            )

            self.assertEqual(category_response.status_code, status.HTTP_200_OK)
            self.assertEqual(category_response.data["count"], 1)
            self.assertEqual(
                self.get_transaction_ids(category_response),
                [product_transaction.id],
            )

    def test_transaction_filters_by_only_with_comment_alias(self):
            self.authenticate()

            described_transaction = self.create_transaction(
                amount="100.00",
                description="Есть описание",
                operation_date=self.today,
            )
            empty_description_transaction = self.create_transaction(
                amount="200.00",
                description="",
                operation_date=self.today,
            )

            with_comment_response = self.client.get(
                reverse("finance:transaction-list"),
                data={
                    "onlyWithComment": "true",
                    "page_size": 20,
                },
            )

            self.assertEqual(with_comment_response.status_code, status.HTTP_200_OK)
            self.assertEqual(with_comment_response.data["count"], 1)
            self.assertEqual(
                self.get_transaction_ids(with_comment_response),
                [described_transaction.id],
            )

            without_comment_response = self.client.get(
                reverse("finance:transaction-list"),
                data={
                    "onlyWithComment": "false",
                    "page_size": 20,
                },
            )

            self.assertEqual(without_comment_response.status_code, status.HTTP_200_OK)
            self.assertEqual(without_comment_response.data["count"], 1)
            self.assertEqual(
                self.get_transaction_ids(without_comment_response),
                [empty_description_transaction.id],
            )

    def test_transaction_sort_by_and_sort_dir_aliases(self):
            self.authenticate()

            high_amount_transaction = self.create_transaction(
                amount="300.00",
                description="B operation",
                operation_date=self.today,
            )
            low_amount_transaction = self.create_transaction(
                amount="100.00",
                description="A operation",
                operation_date=self.today,
            )
            old_transaction = self.create_transaction(
                amount="200.00",
                description="C operation",
                operation_date=self.today - timezone.timedelta(days=1),
            )

            amount_response = self.client.get(
                reverse("finance:transaction-list"),
                data={
                    "sortBy": "amountRub",
                    "sortDir": "desc",
                    "page_size": 20,
                },
            )

            self.assertEqual(amount_response.status_code, status.HTTP_200_OK)
            self.assertEqual(
                self.get_transaction_ids(amount_response),
                [
                    high_amount_transaction.id,
                    old_transaction.id,
                    low_amount_transaction.id,
                ],
            )

            date_response = self.client.get(
                reverse("finance:transaction-list"),
                data={
                    "sortBy": "date",
                    "sortDir": "asc",
                    "page_size": 20,
                },
            )

            self.assertEqual(date_response.status_code, status.HTTP_200_OK)
            self.assertEqual(
                self.get_transaction_ids(date_response),
                [
                    old_transaction.id,
                    low_amount_transaction.id,
                    high_amount_transaction.id,
                ],
            )

    def test_transaction_frontend_alias_invalid_filters_return_bad_request(self):
            self.authenticate()

            invalid_kind_response = self.client.get(
                reverse("finance:transaction-list"),
                data={
                    "kind": "wrong",
                },
            )

            self.assertEqual(
                invalid_kind_response.status_code,
                status.HTTP_400_BAD_REQUEST,
            )
            self.assertFalse(invalid_kind_response.data["success"])
            self.assertIn("kind", invalid_kind_response.data["error"]["field_errors"])

            invalid_sort_by_response = self.client.get(
                reverse("finance:transaction-list"),
                data={
                    "sortBy": "wrong",
                },
            )

            self.assertEqual(
                invalid_sort_by_response.status_code,
                status.HTTP_400_BAD_REQUEST,
            )
            self.assertFalse(invalid_sort_by_response.data["success"])
            self.assertIn("sortBy", invalid_sort_by_response.data["error"]["field_errors"])

            invalid_sort_dir_response = self.client.get(
                reverse("finance:transaction-list"),
                data={
                    "sortBy": "date",
                    "sortDir": "wrong",
                },
            )

            self.assertEqual(
                invalid_sort_dir_response.status_code,
                status.HTTP_400_BAD_REQUEST,
            )
            self.assertFalse(invalid_sort_dir_response.data["success"])
            self.assertIn("sortDir", invalid_sort_dir_response.data["error"]["field_errors"])

    def test_transaction_invalid_filters_return_bad_request(self):
            self.authenticate()

            invalid_account_response = self.client.get(
                reverse("finance:transaction-list"),
                data={
                    "account": "wrong",
                },
            )

            self.assertEqual(
                invalid_account_response.status_code,
                status.HTTP_400_BAD_REQUEST,
            )
            self.assertFalse(invalid_account_response.data["success"])

            invalid_date_response = self.client.get(
                reverse("finance:transaction-list"),
                data={
                    "date_from": "wrong-date",
                },
            )

            self.assertEqual(
                invalid_date_response.status_code,
                status.HTTP_400_BAD_REQUEST,
            )
            self.assertFalse(invalid_date_response.data["success"])

            invalid_amount_response = self.client.get(
                reverse("finance:transaction-list"),
                data={
                    "amount_min": "wrong",
                },
            )

            self.assertEqual(
                invalid_amount_response.status_code,
                status.HTTP_400_BAD_REQUEST,
            )
            self.assertFalse(invalid_amount_response.data["success"])

            invalid_amount_range_response = self.client.get(
                reverse("finance:transaction-list"),
                data={
                    "amount_min": "500.00",
                    "amount_max": "100.00",
                },
            )

            self.assertEqual(
                invalid_amount_range_response.status_code,
                status.HTTP_400_BAD_REQUEST,
            )
            self.assertFalse(invalid_amount_range_response.data["success"])
            self.assertIn(
                "amount_min",
                invalid_amount_range_response.data["error"]["field_errors"],
            )

    def test_transaction_invalid_ordering_returns_bad_request(self):
            self.authenticate()

            response = self.client.get(
                reverse("finance:transaction-list"),
                data={
                    "ordering": "wrong",
                },
            )

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertFalse(response.data["success"])
            self.assertIn("ordering", response.data["error"]["field_errors"])

    def test_transaction_too_long_search_returns_bad_request(self):
            self.authenticate()

            response = self.client.get(
                reverse("finance:transaction-list"),
                data={
                    "search": "a" * 101,
                },
            )

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertFalse(response.data["success"])
            self.assertIn("search", response.data["error"]["field_errors"])

    def test_transactions_list_uses_limited_number_of_queries(self):
            self.authenticate()

            for index in range(30):
                self.create_transaction(
                    amount=str(Decimal("100.00") + index),
                    description=f"Операция {index}",
                    operation_date=self.today - timezone.timedelta(days=index),
                )

            with CaptureQueriesContext(connection) as captured_queries:
                response = self.client.get(
                    reverse("finance:transaction-list"),
                    data={
                        "page": 1,
                        "page_size": 20,
                        "ordering": "-operation_date",
                    },
                )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["count"], 30)
            self.assertEqual(len(response.data["results"]), 20)

            # Запрос списка теперь возвращает позиции операций line_items.
            # Для этого нужен отдельный prefetch-запрос, иначе появится N+1.
            # Нормальная схема: count, page query, tags prefetch, line_items prefetch.
            self.assertLessEqual(len(captured_queries), 4)



class FinanceTransactionLineItemsAPITests(FinanceAPITestCase):
    def test_create_transaction_with_line_items_returns_and_persists_items(self):
            self.authenticate()

            response = self.client.post(
                reverse("finance:transaction-list"),
                data={
                    "account": self.account.id,
                    "category": self.expense_category.id,
                    "type": TransactionType.EXPENSE,
                    "amount": "110.00",
                    "description": "Покупка с позициями",
                    "operation_date": str(self.today),
                    "line_items": [
                        {
                            "name": "1123",
                            "qty": 1,
                            "unit_price_rub": 110,
                            "sum_rub": 110,
                        }
                    ],
                },
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            self.assertIn("line_items", response.data)
            self.assertEqual(len(response.data["line_items"]), 1)
            self.assertEqual(response.data["line_items"][0]["name"], "1123")
            self.assertEqual(Decimal(response.data["line_items"][0]["sum_rub"]), Decimal("110.00"))

            transaction = Transaction.objects.get(pk=response.data["id"])
            self.assertEqual(transaction.line_items.count(), 1)
            line_item = transaction.line_items.get()
            self.assertEqual(line_item.name, "1123")
            self.assertEqual(line_item.quantity, Decimal("1.000"))
            self.assertEqual(line_item.unit_price, Decimal("110.00"))
            self.assertEqual(line_item.amount, Decimal("110.00"))

    def test_transaction_detail_returns_line_items(self):
            self.authenticate()
            transaction = self.create_transaction(
                amount="150.00",
                description="Операция с детализацией",
            )
            TransactionLineItem.objects.create(
                transaction=transaction,
                line_number=1,
                name="Молоко",
                quantity=Decimal("1.000"),
                unit_price=Decimal("90.00"),
                amount=Decimal("90.00"),
            )
            TransactionLineItem.objects.create(
                transaction=transaction,
                line_number=2,
                name="Хлеб",
                quantity=Decimal("1.000"),
                unit_price=Decimal("60.00"),
                amount=Decimal("60.00"),
            )

            response = self.client.get(
                reverse("finance:transaction-detail", kwargs={"pk": transaction.id})
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(len(response.data["line_items"]), 2)
            self.assertEqual(response.data["line_items"][0]["name"], "Молоко")
            self.assertEqual(response.data["line_items"][1]["name"], "Хлеб")

    def test_patch_transaction_replaces_line_items_when_field_is_sent(self):
            self.authenticate()
            transaction = self.create_transaction(
                amount="200.00",
                description="До замены позиций",
            )
            TransactionLineItem.objects.create(
                transaction=transaction,
                line_number=1,
                name="Старая позиция",
                quantity=Decimal("1.000"),
                unit_price=Decimal("200.00"),
                amount=Decimal("200.00"),
            )

            response = self.client.patch(
                reverse("finance:transaction-detail", kwargs={"pk": transaction.id}),
                data={
                    "amount": "110.00",
                    "line_items": [
                        {
                            "name": "Новая позиция",
                            "qty": "1.000",
                            "unit_price_rub": "110.00",
                            "sum_rub": "110.00",
                        }
                    ],
                },
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(len(response.data["line_items"]), 1)
            self.assertEqual(response.data["line_items"][0]["name"], "Новая позиция")
            self.assertEqual(transaction.line_items.count(), 1)
            self.assertEqual(transaction.line_items.get().name, "Новая позиция")

    def test_create_transaction_rejects_line_items_with_wrong_total(self):
            self.authenticate()

            response = self.client.post(
                reverse("finance:transaction-list"),
                data={
                    "account": self.account.id,
                    "category": self.expense_category.id,
                    "type": TransactionType.EXPENSE,
                    "amount": "110.00",
                    "description": "Некорректная сумма позиций",
                    "operation_date": str(self.today),
                    "line_items": [
                        {
                            "name": "Позиция",
                            "qty": "1.000",
                            "unit_price_rub": "90.00",
                            "sum_rub": "90.00",
                        }
                    ],
                },
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertFalse(response.data["success"])
            self.assertIn("line_items", response.data["error"]["field_errors"])
