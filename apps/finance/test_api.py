from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.finance.models import Account, Category, Transaction, TransactionType


User = get_user_model()


class FinanceAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.user = User.objects.create_user(
            username="demo",
            email="demo@example.com",
            password="demo-password-123",
        )
        self.other_user = User.objects.create_user(
            username="other",
            email="other@example.com",
            password="other-password-123",
        )

        self.account = Account.objects.create(
            user=self.user,
            name="Основная карта",
            balance=Decimal("10000.00"),
            currency="RUB",
        )
        self.cash_account = Account.objects.create(
            user=self.user,
            name="Наличные",
            balance=Decimal("3000.00"),
            currency="RUB",
        )
        self.other_account = Account.objects.create(
            user=self.other_user,
            name="Чужая карта",
            balance=Decimal("5000.00"),
            currency="RUB",
        )

        self.expense_category = Category.objects.create(
            user=self.user,
            name="Продукты",
            type=TransactionType.EXPENSE,
        )
        self.transport_category = Category.objects.create(
            user=self.user,
            name="Транспорт",
            type=TransactionType.EXPENSE,
        )
        self.income_category = Category.objects.create(
            user=self.user,
            name="Зарплата",
            type=TransactionType.INCOME,
        )
        self.other_category = Category.objects.create(
            user=self.other_user,
            name="Чужая категория",
            type=TransactionType.EXPENSE,
        )

        self.today = timezone.localdate()

    def authenticate(self):
        self.client.force_authenticate(user=self.user)

    def create_transaction(
        self,
        *,
        user=None,
        account=None,
        category=None,
        type=TransactionType.EXPENSE,
        amount="100.00",
        description="Тестовая операция",
        operation_date=None,
    ):
        return Transaction.objects.create(
            user=user or self.user,
            account=account or self.account,
            category=category or self.expense_category,
            type=type,
            amount=Decimal(amount),
            description=description,
            operation_date=operation_date or self.today,
        )

    def get_transaction_ids(self, response):
        return [item["id"] for item in response.data["results"]]

    def test_categories_list_requires_authentication(self):
        response = self.client.get(reverse("finance:category-list"))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"]["status_code"], 401)

    def test_category_crud_success_flow(self):
        self.authenticate()

        create_response = self.client.post(
            reverse("finance:category-list"),
            data={
                "parent": None,
                "name": "Тестовая категория",
                "type": TransactionType.EXPENSE,
                "is_active": True,
            },
            format="json",
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        category_id = create_response.data["id"]

        child_response = self.client.post(
            reverse("finance:category-list"),
            data={
                "parent": category_id,
                "name": "Дочерняя категория",
                "type": TransactionType.EXPENSE,
                "is_active": True,
            },
            format="json",
        )

        self.assertEqual(child_response.status_code, status.HTTP_201_CREATED)
        child_category_id = child_response.data["id"]
        self.assertEqual(child_response.data["parent"], category_id)

        list_response = self.client.get(reverse("finance:category-list"))

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertIn("results", list_response.data)

        detail_response = self.client.get(
            reverse("finance:category-detail", kwargs={"pk": category_id})
        )

        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.data["name"], "Тестовая категория")

        update_response = self.client.patch(
            reverse("finance:category-detail", kwargs={"pk": category_id}),
            data={
                "name": "Обновленная категория",
            },
            format="json",
        )

        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.data["name"], "Обновленная категория")

        tree_response = self.client.get(reverse("finance:category-tree"))

        self.assertEqual(tree_response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(tree_response.data, list)

        delete_child_response = self.client.delete(
            reverse("finance:category-detail", kwargs={"pk": child_category_id})
        )

        self.assertEqual(delete_child_response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Category.objects.filter(pk=child_category_id).exists())

    def test_category_parent_must_belong_to_current_user(self):
        self.authenticate()

        response = self.client.post(
            reverse("finance:category-list"),
            data={
                "parent": self.other_category.id,
                "name": "Некорректная категория",
                "type": TransactionType.EXPENSE,
                "is_active": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        self.assertIn("parent", response.data["error"]["field_errors"])

    def test_category_parent_must_have_same_type(self):
        self.authenticate()

        response = self.client.post(
            reverse("finance:category-list"),
            data={
                "parent": self.income_category.id,
                "name": "Расход с родителем-доходом",
                "type": TransactionType.EXPENSE,
                "is_active": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        self.assertIn("parent", response.data["error"]["field_errors"])

    def test_delete_category_with_transactions_returns_conflict(self):
        self.authenticate()

        self.create_transaction(
            amount="1200.00",
            operation_date=self.today,
        )

        response = self.client.delete(
            reverse(
                "finance:category-detail",
                kwargs={"pk": self.expense_category.id},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"]["status_code"], 409)

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

        self.assertLessEqual(len(captured_queries), 3)