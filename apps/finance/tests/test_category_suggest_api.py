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


class FinanceCategorySuggestAPITests(FinanceAPITestCase):
    def test_category_suggest_by_expense_keyword_returns_matching_category(self):
            self.authenticate()

            response = self.client.post(
                reverse("finance:category-suggest"),
                data={
                    "description": "Покупка продуктов в пятерочке",
                    "type": TransactionType.EXPENSE,
                },
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertIn("suggestions", response.data)
            self.assertGreaterEqual(len(response.data["suggestions"]), 1)

            suggestion = response.data["suggestions"][0]

            self.assertEqual(suggestion["category"], self.expense_category.id)
            self.assertEqual(suggestion["id"], self.expense_category.id)
            self.assertEqual(suggestion["name"], self.expense_category.name)
            self.assertEqual(suggestion["type"], TransactionType.EXPENSE)
            self.assertEqual(suggestion["icon"], self.expense_category.icon)
            self.assertEqual(suggestion["color"], self.expense_category.color)
            self.assertGreaterEqual(suggestion["confidence"], 0.9)
            self.assertIn("matched_keyword", suggestion)
            self.assertIn("reason", suggestion)

    def test_category_suggest_by_income_name_returns_matching_category(self):
            self.authenticate()

            response = self.client.post(
                reverse("finance:category-suggest"),
                data={
                    "description": "Зарплата за май",
                    "type": TransactionType.INCOME,
                },
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(len(response.data["suggestions"]), 1)

            suggestion = response.data["suggestions"][0]

            self.assertEqual(suggestion["category"], self.income_category.id)
            self.assertEqual(suggestion["name"], "Зарплата")
            self.assertEqual(suggestion["type"], TransactionType.INCOME)
            self.assertGreaterEqual(suggestion["confidence"], 0.9)

    def test_category_suggest_accepts_frontend_kind_field(self):
            self.authenticate()

            response = self.client.post(
                reverse("finance:category-suggest"),
                data={
                    "description": "Такси до университета",
                    "kind": TransactionType.EXPENSE,
                },
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertGreaterEqual(len(response.data["suggestions"]), 1)

            suggestion = response.data["suggestions"][0]

            self.assertEqual(suggestion["category"], self.transport_category.id)
            self.assertEqual(suggestion["name"], "Транспорт")
            self.assertEqual(suggestion["type"], TransactionType.EXPENSE)

    def test_category_suggest_respects_limit(self):
            self.authenticate()

            Category.objects.create(
                user=self.user,
                name="Еда",
                type=TransactionType.EXPENSE,
                icon="utensils",
                color="#10B981",
                sort_order=10,
            )
            Category.objects.create(
                user=self.user,
                name="Супермаркеты",
                type=TransactionType.EXPENSE,
                icon="store",
                color="#4F46E5",
                sort_order=11,
            )

            response = self.client.post(
                reverse("finance:category-suggest"),
                data={
                    "description": "Покупка продуктов в супермаркете",
                    "type": TransactionType.EXPENSE,
                    "limit": 2,
                },
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(len(response.data["suggestions"]), 2)

    def test_category_suggest_does_not_return_archived_category(self):
            self.authenticate()

            self.transport_category.is_archived = True
            self.transport_category.is_active = False
            self.transport_category.save(update_fields=["is_archived", "is_active"])

            response = self.client.post(
                reverse("finance:category-suggest"),
                data={
                    "description": "Такси до университета",
                    "type": TransactionType.EXPENSE,
                },
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["suggestions"], [])

    def test_category_suggest_does_not_return_inactive_category(self):
            self.authenticate()

            self.transport_category.is_active = False
            self.transport_category.save(update_fields=["is_active"])

            response = self.client.post(
                reverse("finance:category-suggest"),
                data={
                    "description": "Такси до университета",
                    "type": TransactionType.EXPENSE,
                },
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["suggestions"], [])

    def test_category_suggest_does_not_return_foreign_user_category(self):
            self.authenticate()

            self.expense_category.is_archived = True
            self.expense_category.is_active = False
            self.expense_category.save(update_fields=["is_archived", "is_active"])

            Category.objects.create(
                user=self.other_user,
                name="Продукты",
                type=TransactionType.EXPENSE,
                icon="shopping-cart",
                color="#10B981",
                is_active=True,
                is_archived=False,
            )

            response = self.client.post(
                reverse("finance:category-suggest"),
                data={
                    "description": "Покупка продуктов в магазине",
                    "type": TransactionType.EXPENSE,
                },
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["suggestions"], [])

    def test_category_suggest_returns_empty_list_without_matches(self):
            self.authenticate()

            response = self.client.post(
                reverse("finance:category-suggest"),
                data={
                    "description": "Неизвестная операция без совпадений",
                    "type": TransactionType.EXPENSE,
                },
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["suggestions"], [])

    def test_category_suggest_without_type_or_kind_returns_bad_request(self):
            self.authenticate()

            response = self.client.post(
                reverse("finance:category-suggest"),
                data={
                    "description": "Покупка продуктов",
                },
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertFalse(response.data["success"])
            self.assertIn("type", response.data["error"]["field_errors"])

    def test_category_suggest_too_short_description_returns_bad_request(self):
            self.authenticate()

            response = self.client.post(
                reverse("finance:category-suggest"),
                data={
                    "description": "а",
                    "type": TransactionType.EXPENSE,
                },
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertFalse(response.data["success"])
            self.assertIn("description", response.data["error"]["field_errors"])

    def test_category_suggest_too_long_description_returns_bad_request(self):
            self.authenticate()

            response = self.client.post(
                reverse("finance:category-suggest"),
                data={
                    "description": "a" * 301,
                    "type": TransactionType.EXPENSE,
                },
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertFalse(response.data["success"])
            self.assertIn("description", response.data["error"]["field_errors"])

    def test_category_suggest_requires_authentication(self):
            response = self.client.post(
                reverse("finance:category-suggest"),
                data={
                    "description": "Покупка продуктов",
                    "type": TransactionType.EXPENSE,
                },
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
            self.assertFalse(response.data["success"])
