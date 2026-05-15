from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.finance.models import (
    Account,
    Budget,
    Category,
    Transaction,
    TransactionType,
)


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

    def test_category_put_full_update_success(self):
        self.authenticate()

        response = self.client.put(
            reverse("finance:category-detail", kwargs={"pk": self.expense_category.id}),
            data={
                "parent": None,
                "name": "Полностью обновленная категория",
                "type": TransactionType.EXPENSE,
                "icon": "cart",
                "color": "#4F46E5",
                "sort_order": 7,
                "is_favorite": True,
                "is_archived": False,
                "is_active": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.expense_category.id)
        self.assertEqual(response.data["name"], "Полностью обновленная категория")
        self.assertEqual(response.data["type"], TransactionType.EXPENSE)
        self.assertEqual(response.data["icon"], "cart")
        self.assertEqual(response.data["color"], "#4F46E5")
        self.assertEqual(response.data["sort_order"], 7)
        self.assertTrue(response.data["is_favorite"])
        self.assertFalse(response.data["is_archived"])
        self.assertTrue(response.data["is_active"])

        self.expense_category.refresh_from_db()
        self.assertEqual(self.expense_category.name, "Полностью обновленная категория")
        self.assertEqual(self.expense_category.icon, "cart")
        self.assertEqual(self.expense_category.color, "#4F46E5")
        self.assertEqual(self.expense_category.sort_order, 7)
        self.assertTrue(self.expense_category.is_favorite)

    def test_category_archive_endpoint_archives_category_by_default(self):
        self.authenticate()

        response = self.client.post(
            reverse(
                "finance:category-archive",
                kwargs={"pk": self.expense_category.id},
            ),
            data={},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.expense_category.id)
        self.assertTrue(response.data["is_archived"])
        self.assertFalse(response.data["is_active"])
        self.assertEqual(response.data["detail"], "Категория отправлена в архив.")

        self.expense_category.refresh_from_db()
        self.assertTrue(self.expense_category.is_archived)
        self.assertFalse(self.expense_category.is_active)

    def test_category_archive_endpoint_restores_category(self):
        self.authenticate()

        self.expense_category.is_archived = True
        self.expense_category.is_active = False
        self.expense_category.save(update_fields=["is_archived", "is_active"])

        response = self.client.post(
            reverse(
                "finance:category-archive",
                kwargs={"pk": self.expense_category.id},
            ),
            data={
                "archived": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.expense_category.id)
        self.assertFalse(response.data["is_archived"])
        self.assertTrue(response.data["is_active"])
        self.assertEqual(response.data["detail"], "Категория восстановлена из архива.")

        self.expense_category.refresh_from_db()
        self.assertFalse(self.expense_category.is_archived)
        self.assertTrue(self.expense_category.is_active)

    def test_category_archive_endpoint_does_not_allow_foreign_category(self):
        self.authenticate()

        response = self.client.post(
            reverse(
                "finance:category-archive",
                kwargs={"pk": self.other_category.id},
            ),
            data={},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(response.data["success"])

        self.other_category.refresh_from_db()
        self.assertFalse(self.other_category.is_archived)
        self.assertTrue(self.other_category.is_active)

    def test_delete_empty_category_success(self):
        self.authenticate()

        category = Category.objects.create(
            user=self.user,
            name="Пустая категория",
            type=TransactionType.EXPENSE,
        )

        response = self.client.delete(
            reverse("finance:category-detail", kwargs={"pk": category.id})
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Category.objects.filter(pk=category.id).exists())

    def test_delete_category_with_children_returns_conflict(self):
        self.authenticate()

        parent = Category.objects.create(
            user=self.user,
            name="Родитель для удаления",
            type=TransactionType.EXPENSE,
        )
        Category.objects.create(
            user=self.user,
            parent=parent,
            name="Дочерняя категория для удаления",
            type=TransactionType.EXPENSE,
        )

        response = self.client.delete(
            reverse("finance:category-detail", kwargs={"pk": parent.id})
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"]["code"], "category_has_children")

        self.assertTrue(Category.objects.filter(pk=parent.id).exists())

    def test_delete_category_with_budgets_returns_conflict(self):
        self.authenticate()

        category = Category.objects.create(
            user=self.user,
            name="Категория с бюджетом",
            type=TransactionType.EXPENSE,
        )
        Budget.objects.create(
            user=self.user,
            category=category,
            amount_limit=Decimal("10000.00"),
            period_start=self.today,
            period_end=self.today + timezone.timedelta(days=30),
        )

        response = self.client.delete(
            reverse("finance:category-detail", kwargs={"pk": category.id})
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"]["code"], "category_has_budgets")

        self.assertTrue(Category.objects.filter(pk=category.id).exists())

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
    
    def test_category_create_without_sort_order_appends_to_siblings(self):
        self.authenticate()

        current_max_sort_order = (
            Category.objects
            .filter(
                user=self.user,
                type=TransactionType.EXPENSE,
                parent__isnull=True,
            )
            .order_by("-sort_order")
            .values_list("sort_order", flat=True)
            .first()
        )

        first_expected_sort_order = (
            0 if current_max_sort_order is None else current_max_sort_order + 1
        )

        first_response = self.client.post(
            reverse("finance:category-list"),
            data={
                "parent": None,
                "name": "Первая категория",
                "type": TransactionType.EXPENSE,
                "icon": "cart",
                "color": "#4F46E5",
            },
            format="json",
        )

        second_response = self.client.post(
            reverse("finance:category-list"),
            data={
                "parent": None,
                "name": "Вторая категория",
                "type": TransactionType.EXPENSE,
                "icon": "home",
                "color": "#10B981",
            },
            format="json",
        )

        self.assertEqual(first_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second_response.status_code, status.HTTP_201_CREATED)

        self.assertEqual(first_response.data["sort_order"], first_expected_sort_order)
        self.assertEqual(second_response.data["sort_order"], first_expected_sort_order + 1)

    def test_category_child_create_without_sort_order_appends_to_parent_children(self):
        self.authenticate()

        parent = Category.objects.create(
            user=self.user,
            name="Родитель",
            type=TransactionType.EXPENSE,
            sort_order=0,
        )
        first_child = Category.objects.create(
            user=self.user,
            parent=parent,
            name="Первый ребёнок",
            type=TransactionType.EXPENSE,
            sort_order=0,
        )

        response = self.client.post(
            reverse("finance:category-list"),
            data={
                "parent": parent.id,
                "name": "Второй ребёнок",
                "type": TransactionType.EXPENSE,
                "icon": "cart",
                "color": "#4F46E5",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["parent"], parent.id)
        self.assertEqual(response.data["sort_order"], first_child.sort_order + 1)

    def test_category_tree_is_ordered_by_sort_order_inside_hierarchy(self):
        self.authenticate()

        second_parent = Category.objects.create(
            user=self.user,
            name="Второй родитель",
            type=TransactionType.EXPENSE,
            sort_order=2,
        )
        first_parent = Category.objects.create(
            user=self.user,
            name="Первый родитель",
            type=TransactionType.EXPENSE,
            sort_order=1,
        )
        second_child = Category.objects.create(
            user=self.user,
            parent=first_parent,
            name="Второй ребёнок",
            type=TransactionType.EXPENSE,
            sort_order=2,
        )
        first_child = Category.objects.create(
            user=self.user,
            parent=first_parent,
            name="Первый ребёнок",
            type=TransactionType.EXPENSE,
            sort_order=1,
        )

        response = self.client.get(
            reverse("finance:category-tree"),
            data={
                "type": TransactionType.EXPENSE,
                "is_active": "true",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response_ids = [item["id"] for item in response.data]

        self.assertLess(
            response_ids.index(first_parent.id),
            response_ids.index(second_parent.id),
        )

        first_parent_node = next(
            item for item in response.data if item["id"] == first_parent.id
        )
        child_ids = [item["id"] for item in first_parent_node["children"]]

        self.assertEqual(child_ids, [first_child.id, second_child.id])

    def test_category_update_parent_to_descendant_returns_bad_request(self):
        self.authenticate()

        root = Category.objects.create(
            user=self.user,
            name="Корень",
            type=TransactionType.EXPENSE,
            sort_order=0,
        )
        child = Category.objects.create(
            user=self.user,
            parent=root,
            name="Дочерняя категория",
            type=TransactionType.EXPENSE,
            sort_order=0,
        )
        grandchild = Category.objects.create(
            user=self.user,
            parent=child,
            name="Вложенная категория",
            type=TransactionType.EXPENSE,
            sort_order=0,
        )

        response = self.client.patch(
            reverse("finance:category-detail", kwargs={"pk": root.id}),
            data={
                "parent": grandchild.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        self.assertIn("parent", response.data["error"]["field_errors"])

        root.refresh_from_db()
        self.assertIsNone(root.parent)

    def test_category_move_to_new_parent_without_sort_order_appends_to_new_siblings(self):
        self.authenticate()

        first_parent = Category.objects.create(
            user=self.user,
            name="Первый родитель",
            type=TransactionType.EXPENSE,
            sort_order=0,
        )
        second_parent = Category.objects.create(
            user=self.user,
            name="Второй родитель",
            type=TransactionType.EXPENSE,
            sort_order=1,
        )
        existing_child = Category.objects.create(
            user=self.user,
            parent=second_parent,
            name="Существующий ребёнок",
            type=TransactionType.EXPENSE,
            sort_order=0,
        )
        moved_child = Category.objects.create(
            user=self.user,
            parent=first_parent,
            name="Перемещаемый ребёнок",
            type=TransactionType.EXPENSE,
            sort_order=0,
        )

        response = self.client.patch(
            reverse("finance:category-detail", kwargs={"pk": moved_child.id}),
            data={
                "parent": second_parent.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["parent"], second_parent.id)
        self.assertEqual(response.data["sort_order"], existing_child.sort_order + 1)

    def test_category_can_be_archived_and_hidden(self):
        self.authenticate()

        response = self.client.patch(
            reverse("finance:category-detail", kwargs={"pk": self.expense_category.id}),
            data={
                "is_archived": True,
                "is_active": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["is_archived"])
        self.assertFalse(response.data["is_active"])

        self.expense_category.refresh_from_db()
        self.assertTrue(self.expense_category.is_archived)
        self.assertFalse(self.expense_category.is_active)

    def test_category_list_filters_by_is_archived(self):
        self.authenticate()

        self.expense_category.is_archived = True
        self.expense_category.save(update_fields=["is_archived"])

        archived_response = self.client.get(
            reverse("finance:category-list"),
            data={
                "type": TransactionType.EXPENSE,
                "is_archived": "true",
            },
        )

        self.assertEqual(archived_response.status_code, status.HTTP_200_OK)

        archived_ids = [
            item["id"]
            for item in archived_response.data["results"]
        ]

        self.assertIn(self.expense_category.id, archived_ids)
        self.assertNotIn(self.transport_category.id, archived_ids)

        active_response = self.client.get(
            reverse("finance:category-list"),
            data={
                "type": TransactionType.EXPENSE,
                "is_archived": "false",
            },
        )

        self.assertEqual(active_response.status_code, status.HTTP_200_OK)

        active_ids = [
            item["id"]
            for item in active_response.data["results"]
        ]

        self.assertNotIn(self.expense_category.id, active_ids)
        self.assertIn(self.transport_category.id, active_ids)

    def test_category_tree_filters_archived_categories_and_children(self):
        self.authenticate()

        parent = Category.objects.create(
            user=self.user,
            name="Родитель для архива",
            type=TransactionType.EXPENSE,
            sort_order=10,
        )
        active_child = Category.objects.create(
            user=self.user,
            parent=parent,
            name="Активный ребёнок",
            type=TransactionType.EXPENSE,
            sort_order=0,
            is_archived=False,
        )
        archived_child = Category.objects.create(
            user=self.user,
            parent=parent,
            name="Архивный ребёнок",
            type=TransactionType.EXPENSE,
            sort_order=1,
            is_archived=True,
        )

        response = self.client.get(
            reverse("finance:category-tree"),
            data={
                "type": TransactionType.EXPENSE,
                "is_archived": "false",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        parent_node = next(
            item for item in response.data if item["id"] == parent.id
        )
        child_ids = [item["id"] for item in parent_node["children"]]

        self.assertIn(active_child.id, child_ids)
        self.assertNotIn(archived_child.id, child_ids)

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

    def test_budget_rejects_archived_category(self):
        self.expense_category.is_archived = True
        self.expense_category.save(update_fields=["is_archived"])

        budget = Budget(
            user=self.user,
            category=self.expense_category,
            amount_limit=Decimal("10000.00"),
            period_start=self.today,
            period_end=self.today + timezone.timedelta(days=30),
        )

        with self.assertRaises(ValidationError):
            budget.full_clean()

    def test_budget_rejects_inactive_category(self):
        self.expense_category.is_active = False
        self.expense_category.save(update_fields=["is_active"])

        budget = Budget(
            user=self.user,
            category=self.expense_category,
            amount_limit=Decimal("10000.00"),
            period_start=self.today,
            period_end=self.today + timezone.timedelta(days=30),
        )

        with self.assertRaises(ValidationError):
            budget.full_clean()

    def test_category_favorite_endpoint_sets_category_as_favorite(self):
        self.authenticate()

        response = self.client.patch(
            reverse(
                "finance:category-favorite",
                kwargs={"pk": self.expense_category.id},
            ),
            data={
                "favorite": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.expense_category.id)
        self.assertTrue(response.data["is_favorite"])
        self.assertEqual(response.data["detail"], "Категория добавлена в избранное.")

        self.expense_category.refresh_from_db()
        self.assertTrue(self.expense_category.is_favorite)

    def test_category_favorite_endpoint_removes_category_from_favorites(self):
        self.authenticate()

        self.expense_category.is_favorite = True
        self.expense_category.save(update_fields=["is_favorite"])

        response = self.client.patch(
            reverse(
                "finance:category-favorite",
                kwargs={"pk": self.expense_category.id},
            ),
            data={
                "favorite": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.expense_category.id)
        self.assertFalse(response.data["is_favorite"])
        self.assertEqual(response.data["detail"], "Категория удалена из избранного.")

        self.expense_category.refresh_from_db()
        self.assertFalse(self.expense_category.is_favorite)

    def test_category_favorite_endpoint_requires_favorite_field(self):
        self.authenticate()

        response = self.client.patch(
            reverse(
                "finance:category-favorite",
                kwargs={"pk": self.expense_category.id},
            ),
            data={},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        self.assertIn("favorite", response.data["error"]["field_errors"])

    def test_category_favorite_endpoint_does_not_allow_foreign_category(self):
        self.authenticate()

        response = self.client.patch(
            reverse(
                "finance:category-favorite",
                kwargs={"pk": self.other_category.id},
            ),
            data={
                "favorite": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(response.data["success"])

        self.other_category.refresh_from_db()
        self.assertFalse(self.other_category.is_favorite)

    def test_category_list_filters_by_is_favorite(self):
        self.authenticate()

        self.expense_category.is_favorite = True
        self.expense_category.save(update_fields=["is_favorite"])

        favorite_response = self.client.get(
            reverse("finance:category-list"),
            data={
                "type": TransactionType.EXPENSE,
                "is_favorite": "true",
            },
        )

        self.assertEqual(favorite_response.status_code, status.HTTP_200_OK)

        favorite_ids = [
            item["id"]
            for item in favorite_response.data["results"]
        ]

        self.assertIn(self.expense_category.id, favorite_ids)
        self.assertNotIn(self.transport_category.id, favorite_ids)

        not_favorite_response = self.client.get(
            reverse("finance:category-list"),
            data={
                "type": TransactionType.EXPENSE,
                "is_favorite": "false",
            },
        )

        self.assertEqual(not_favorite_response.status_code, status.HTTP_200_OK)

        not_favorite_ids = [
            item["id"]
            for item in not_favorite_response.data["results"]
        ]

        self.assertNotIn(self.expense_category.id, not_favorite_ids)
        self.assertIn(self.transport_category.id, not_favorite_ids)

    def test_category_tree_filters_favorite_categories_and_children(self):
        self.authenticate()

        parent = Category.objects.create(
            user=self.user,
            name="Избранный родитель",
            type=TransactionType.EXPENSE,
            sort_order=10,
            is_favorite=True,
        )
        favorite_child = Category.objects.create(
            user=self.user,
            parent=parent,
            name="Избранный ребёнок",
            type=TransactionType.EXPENSE,
            sort_order=0,
            is_favorite=True,
        )
        not_favorite_child = Category.objects.create(
            user=self.user,
            parent=parent,
            name="Обычный ребёнок",
            type=TransactionType.EXPENSE,
            sort_order=1,
            is_favorite=False,
        )

        response = self.client.get(
            reverse("finance:category-tree"),
            data={
                "type": TransactionType.EXPENSE,
                "is_favorite": "true",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        parent_node = next(
            item for item in response.data if item["id"] == parent.id
        )
        child_ids = [item["id"] for item in parent_node["children"]]

        self.assertIn(favorite_child.id, child_ids)
        self.assertNotIn(not_favorite_child.id, child_ids)

    def test_category_list_searches_by_name(self):
        self.authenticate()

        target_category = Category.objects.create(
            user=self.user,
            name="Кафе и рестораны",
            type=TransactionType.EXPENSE,
            sort_order=10,
        )

        response = self.client.get(
            reverse("finance:category-list"),
            data={
                "search": "кафе",
                "page_size": 20,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        category_ids = [
            item["id"]
            for item in response.data["results"]
        ]

        self.assertIn(target_category.id, category_ids)
        self.assertNotIn(self.transport_category.id, category_ids)

    def test_category_list_filters_root_categories(self):
        self.authenticate()

        parent = Category.objects.create(
            user=self.user,
            name="Родитель root",
            type=TransactionType.EXPENSE,
            sort_order=10,
        )
        child = Category.objects.create(
            user=self.user,
            parent=parent,
            name="Дочерняя root",
            type=TransactionType.EXPENSE,
            sort_order=0,
        )

        root_response = self.client.get(
            reverse("finance:category-list"),
            data={
                "type": TransactionType.EXPENSE,
                "root": "true",
                "page_size": 50,
            },
        )

        self.assertEqual(root_response.status_code, status.HTTP_200_OK)

        root_ids = [
            item["id"]
            for item in root_response.data["results"]
        ]

        self.assertIn(parent.id, root_ids)
        self.assertIn(self.expense_category.id, root_ids)
        self.assertNotIn(child.id, root_ids)

        child_response = self.client.get(
            reverse("finance:category-list"),
            data={
                "type": TransactionType.EXPENSE,
                "root": "false",
                "page_size": 50,
            },
        )

        self.assertEqual(child_response.status_code, status.HTTP_200_OK)

        child_ids = [
            item["id"]
            for item in child_response.data["results"]
        ]

        self.assertIn(child.id, child_ids)
        self.assertNotIn(parent.id, child_ids)
        self.assertNotIn(self.expense_category.id, child_ids)

    def test_category_list_combines_search_type_hierarchy_and_flags(self):
        self.authenticate()

        matching_category = Category.objects.create(
            user=self.user,
            name="Комбо категория",
            type=TransactionType.EXPENSE,
            sort_order=10,
            is_active=True,
            is_archived=False,
            is_favorite=True,
        )
        archived_category = Category.objects.create(
            user=self.user,
            name="Комбо архив",
            type=TransactionType.EXPENSE,
            sort_order=11,
            is_active=False,
            is_archived=True,
            is_favorite=True,
        )
        not_favorite_category = Category.objects.create(
            user=self.user,
            name="Комбо обычная",
            type=TransactionType.EXPENSE,
            sort_order=12,
            is_active=True,
            is_archived=False,
            is_favorite=False,
        )
        income_category = Category.objects.create(
            user=self.user,
            name="Комбо доход",
            type=TransactionType.INCOME,
            sort_order=13,
            is_active=True,
            is_archived=False,
            is_favorite=True,
        )

        response = self.client.get(
            reverse("finance:category-list"),
            data={
                "type": TransactionType.EXPENSE,
                "root": "true",
                "is_active": "true",
                "is_archived": "false",
                "is_favorite": "true",
                "search": "комбо",
                "page_size": 50,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        category_ids = [
            item["id"]
            for item in response.data["results"]
        ]

        self.assertIn(matching_category.id, category_ids)
        self.assertNotIn(archived_category.id, category_ids)
        self.assertNotIn(not_favorite_category.id, category_ids)
        self.assertNotIn(income_category.id, category_ids)

    def test_category_list_invalid_root_returns_bad_request(self):
        self.authenticate()

        response = self.client.get(
            reverse("finance:category-list"),
            data={
                "root": "wrong",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        self.assertIn("root", response.data["error"]["field_errors"])

    def test_category_list_too_long_search_returns_bad_request(self):
        self.authenticate()

        response = self.client.get(
            reverse("finance:category-list"),
            data={
                "search": "a" * 101,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        self.assertIn("search", response.data["error"]["field_errors"])

    def test_category_tree_searches_root_categories_by_name(self):
        self.authenticate()

        matching_parent = Category.objects.create(
            user=self.user,
            name="Дерево поиск",
            type=TransactionType.EXPENSE,
            sort_order=10,
        )
        Category.objects.create(
            user=self.user,
            parent=matching_parent,
            name="Дерево ребёнок",
            type=TransactionType.EXPENSE,
            sort_order=0,
        )
        not_matching_parent = Category.objects.create(
            user=self.user,
            name="Другая категория",
            type=TransactionType.EXPENSE,
            sort_order=11,
        )

        response = self.client.get(
            reverse("finance:category-tree"),
            data={
                "type": TransactionType.EXPENSE,
                "search": "дерево",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        root_ids = [
            item["id"]
            for item in response.data
        ]

        self.assertIn(matching_parent.id, root_ids)
        self.assertNotIn(not_matching_parent.id, root_ids)

        matching_node = next(
            item for item in response.data if item["id"] == matching_parent.id
        )

        self.assertEqual(len(matching_node["children"]), 1)

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