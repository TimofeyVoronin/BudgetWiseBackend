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

from apps.finance.models import Account, Budget, Category, Transaction, TransactionType

from .base import FinanceAPITestCase


class FinanceCategoryReorderAPITests(FinanceAPITestCase):
    def test_category_reorder_requires_authentication(self):
            response = self.client.put(
                reverse("finance:category-reorder"),
                data={
                    "type": TransactionType.EXPENSE,
                    "order": [
                        {
                            "id": self.expense_category.id,
                            "parent": None,
                            "sort_order": 0,
                        },
                    ],
                },
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
            self.assertFalse(response.data["success"])

    def test_category_reorder_updates_parent_and_sort_order_with_backend_fields(self):
            self.authenticate()

            first_parent = Category.objects.create(
                user=self.user,
                name="Первый родитель reorder",
                type=TransactionType.EXPENSE,
                sort_order=0,
            )
            second_parent = Category.objects.create(
                user=self.user,
                name="Второй родитель reorder",
                type=TransactionType.EXPENSE,
                sort_order=1,
            )
            moved_child = Category.objects.create(
                user=self.user,
                parent=first_parent,
                name="Перемещаемый ребёнок reorder",
                type=TransactionType.EXPENSE,
                sort_order=0,
            )
            existing_child = Category.objects.create(
                user=self.user,
                parent=second_parent,
                name="Существующий ребёнок reorder",
                type=TransactionType.EXPENSE,
                sort_order=0,
            )

            response = self.client.put(
                reverse("finance:category-reorder"),
                data={
                    "type": TransactionType.EXPENSE,
                    "order": [
                        {
                            "id": second_parent.id,
                            "parent": None,
                            "sort_order": 0,
                        },
                        {
                            "id": first_parent.id,
                            "parent": None,
                            "sort_order": 1,
                        },
                        {
                            "id": existing_child.id,
                            "parent": second_parent.id,
                            "sort_order": 0,
                        },
                        {
                            "id": moved_child.id,
                            "parent": second_parent.id,
                            "sort_order": 1,
                        },
                    ],
                },
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["detail"], "Порядок категорий обновлён.")
            self.assertEqual(response.data["updated_count"], 4)

            first_parent.refresh_from_db()
            second_parent.refresh_from_db()
            moved_child.refresh_from_db()
            existing_child.refresh_from_db()

            self.assertIsNone(second_parent.parent)
            self.assertEqual(second_parent.sort_order, 0)

            self.assertIsNone(first_parent.parent)
            self.assertEqual(first_parent.sort_order, 1)

            self.assertEqual(existing_child.parent_id, second_parent.id)
            self.assertEqual(existing_child.sort_order, 0)

            self.assertEqual(moved_child.parent_id, second_parent.id)
            self.assertEqual(moved_child.sort_order, 1)

    def test_category_reorder_accepts_frontend_parent_id_and_position_fields(self):
            self.authenticate()

            parent = Category.objects.create(
                user=self.user,
                name="Родитель frontend reorder",
                type=TransactionType.EXPENSE,
                sort_order=0,
            )
            child = Category.objects.create(
                user=self.user,
                name="Ребёнок frontend reorder",
                type=TransactionType.EXPENSE,
                sort_order=0,
            )

            response = self.client.put(
                reverse("finance:category-reorder"),
                data={
                    "kind": TransactionType.EXPENSE,
                    "order": [
                        {
                            "id": child.id,
                            "parentId": parent.id,
                            "position": 3,
                        },
                    ],
                },
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["updated_count"], 1)

            child.refresh_from_db()

            self.assertEqual(child.parent_id, parent.id)
            self.assertEqual(child.sort_order, 3)

    def test_category_reorder_rejects_foreign_category_id(self):
            self.authenticate()

            old_sort_order = self.expense_category.sort_order
            old_parent_id = self.expense_category.parent_id

            response = self.client.put(
                reverse("finance:category-reorder"),
                data={
                    "type": TransactionType.EXPENSE,
                    "order": [
                        {
                            "id": self.expense_category.id,
                            "parent": None,
                            "sort_order": 0,
                        },
                        {
                            "id": self.other_category.id,
                            "parent": None,
                            "sort_order": 1,
                        },
                    ],
                },
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertFalse(response.data["success"])
            self.assertIn("order", response.data["error"]["field_errors"])

            self.expense_category.refresh_from_db()
            self.other_category.refresh_from_db()

            self.assertEqual(self.expense_category.sort_order, old_sort_order)
            self.assertEqual(self.expense_category.parent_id, old_parent_id)
            self.assertIsNone(self.other_category.parent_id)

    def test_category_reorder_rejects_cycle(self):
            self.authenticate()

            root = Category.objects.create(
                user=self.user,
                name="Корень reorder",
                type=TransactionType.EXPENSE,
                sort_order=0,
            )
            child = Category.objects.create(
                user=self.user,
                parent=root,
                name="Ребёнок reorder",
                type=TransactionType.EXPENSE,
                sort_order=0,
            )

            response = self.client.put(
                reverse("finance:category-reorder"),
                data={
                    "type": TransactionType.EXPENSE,
                    "order": [
                        {
                            "id": root.id,
                            "parent": child.id,
                            "sort_order": 0,
                        },
                        {
                            "id": child.id,
                            "parent": root.id,
                            "sort_order": 0,
                        },
                    ],
                },
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertFalse(response.data["success"])
            self.assertIn("order", response.data["error"]["field_errors"])

            root.refresh_from_db()
            child.refresh_from_db()

            self.assertIsNone(root.parent)
            self.assertEqual(child.parent_id, root.id)

    def test_category_reorder_rejects_wrong_type_category(self):
            self.authenticate()

            response = self.client.put(
                reverse("finance:category-reorder"),
                data={
                    "type": TransactionType.EXPENSE,
                    "order": [
                        {
                            "id": self.income_category.id,
                            "parent": None,
                            "sort_order": 0,
                        },
                    ],
                },
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertFalse(response.data["success"])
            self.assertIn("order", response.data["error"]["field_errors"])

            self.income_category.refresh_from_db()

            self.assertIsNone(self.income_category.parent_id)
