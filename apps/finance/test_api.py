from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
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
        self.assertIn("parent", response.data["error"]["detail"])

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
        self.assertIn("parent", response.data["error"]["detail"])

    def test_delete_category_with_transactions_returns_conflict(self):
        self.authenticate()

        Transaction.objects.create(
            user=self.user,
            account=self.account,
            category=self.expense_category,
            type=TransactionType.EXPENSE,
            amount=Decimal("1200.00"),
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
        self.assertIn("account", response.data["error"]["detail"])

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
        self.assertIn("category", response.data["error"]["detail"])

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
        self.assertIn("category", response.data["error"]["detail"])

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
        self.assertIn("account", response.data["error"]["detail"])

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
        self.assertIn("category", response.data["error"]["detail"])

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