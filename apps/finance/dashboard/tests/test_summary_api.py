import csv
from decimal import Decimal
from io import BytesIO, StringIO
from unittest.mock import patch

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook
from rest_framework import status

from apps.finance.currencies.services import get_user_currency_by_code
from apps.finance.models import Account, Budget, Category, Transaction, TransactionType
from apps.users.app_settings.formatting import get_user_app_today

from apps.finance.testing import FinanceAPITestCase


@override_settings(CURRENCY_RATES_ENABLED=False)
class FinanceDashboardAPITests(FinanceAPITestCase):
    def set_rate(self, code: str, value: str):
        user_currency = get_user_currency_by_code(self.user, code)
        user_currency.rate_to_primary = Decimal(value)
        user_currency.save(update_fields=["rate_to_primary", "updated_at"])

    def test_dashboard_summary_requires_authentication(self):
            response = self.client.get(reverse("finance:dashboard-summary"))

            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
            self.assertFalse(response.data["success"])

    def test_dashboard_summary_returns_default_month_aggregates(self):
            self.authenticate()

            month_start = self.today.replace(day=1)
            previous_month_date = month_start - timezone.timedelta(days=1)

            self.create_transaction(
                account=self.account,
                category=self.income_category,
                type=TransactionType.INCOME,
                amount="50000.00",
                description="Зарплата за месяц",
                operation_date=self.today,
            )
            self.create_transaction(
                account=self.account,
                category=self.expense_category,
                type=TransactionType.EXPENSE,
                amount="1200.00",
                description="Продукты за месяц",
                operation_date=self.today,
            )
            self.create_transaction(
                account=self.cash_account,
                category=self.transport_category,
                type=TransactionType.EXPENSE,
                amount="300.00",
                description="Транспорт за месяц",
                operation_date=self.today,
            )
            self.create_transaction(
                account=self.account,
                category=self.expense_category,
                type=TransactionType.EXPENSE,
                amount="999.00",
                description="Операция прошлого месяца",
                operation_date=previous_month_date,
            )
            self.create_transaction(
                user=self.other_user,
                account=self.other_account,
                category=self.other_category,
                type=TransactionType.EXPENSE,
                amount="777.00",
                description="Чужая операция",
                operation_date=self.today,
            )

            response = self.client.get(reverse("finance:dashboard-summary"))
            expected_today = get_user_app_today(self.user)
            expected_month_start = expected_today.replace(day=1)

            self.assertEqual(response.status_code, status.HTTP_200_OK)

            self.assertEqual(response.data["period"]["type"], "month")
            self.assertEqual(response.data["period"]["date_from"], str(expected_month_start))
            self.assertEqual(response.data["period"]["date_to"], str(expected_today))
            self.assertEqual(response.data["currency"], "RUB")

            self.assertEqual(response.data["totals"]["accounts_balance"], "13000.00")
            self.assertEqual(response.data["totals"]["income"], "50000.00")
            self.assertEqual(response.data["totals"]["expense"], "1500.00")
            self.assertEqual(response.data["totals"]["net"], "48500.00")

            self.assertEqual(len(response.data["recent_transactions"]), 4)

            recent_descriptions = [
                item["description"]
                for item in response.data["recent_transactions"]
            ]

            self.assertIn("Зарплата за месяц", recent_descriptions)
            self.assertIn("Продукты за месяц", recent_descriptions)
            self.assertIn("Транспорт за месяц", recent_descriptions)
            self.assertIn("Операция прошлого месяца", recent_descriptions)
            self.assertNotIn("Чужая операция", recent_descriptions)

            top_categories = response.data["top_expense_categories"]

            self.assertEqual(len(top_categories), 2)
            self.assertEqual(top_categories[0]["category"], self.expense_category.id)
            self.assertEqual(top_categories[0]["total"], "1200.00")
            self.assertEqual(top_categories[1]["category"], self.transport_category.id)
            self.assertEqual(top_categories[1]["total"], "300.00")

            self.assertEqual(response.data["reminders"]["title"], "Напоминания")
            self.assertEqual(response.data["reminders"]["headerIcon"], "bell")
            self.assertEqual(response.data["reminders"]["rows"], [])
            self.assertEqual(
                response.data["reminders"]["footerLinkLabel"],
                "Все напоминания",
            )

    def test_dashboard_summary_supports_custom_period(self):
            self.authenticate()

            self.create_transaction(
                account=self.account,
                category=self.income_category,
                type=TransactionType.INCOME,
                amount="10000.00",
                description="Доход внутри периода",
                operation_date=self.today,
            )
            self.create_transaction(
                account=self.account,
                category=self.expense_category,
                type=TransactionType.EXPENSE,
                amount="1500.00",
                description="Расход внутри периода",
                operation_date=self.today,
            )
            self.create_transaction(
                account=self.account,
                category=self.expense_category,
                type=TransactionType.EXPENSE,
                amount="900.00",
                description="Расход вне периода",
                operation_date=self.today - timezone.timedelta(days=40),
            )

            response = self.client.get(
                reverse("finance:dashboard-summary"),
                data={
                    "period": "custom",
                    "date_from": str(self.today - timezone.timedelta(days=1)),
                    "date_to": str(self.today + timezone.timedelta(days=1)),
                    "currency": "RUB",
                },
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["period"]["type"], "custom")
            self.assertEqual(
                response.data["period"]["date_from"],
                str(self.today - timezone.timedelta(days=1)),
            )
            self.assertEqual(
                response.data["period"]["date_to"],
                str(self.today + timezone.timedelta(days=1)),
            )
            self.assertEqual(response.data["totals"]["income"], "10000.00")
            self.assertEqual(response.data["totals"]["expense"], "1500.00")
            self.assertEqual(response.data["totals"]["net"], "8500.00")

    def test_dashboard_summary_supports_week_and_year_periods(self):
            self.authenticate()

            week_response = self.client.get(
                reverse("finance:dashboard-summary"),
                data={
                    "period": "week",
                },
            )

            self.assertEqual(week_response.status_code, status.HTTP_200_OK)
            self.assertEqual(week_response.data["period"]["type"], "week")

            expected_today = get_user_app_today(self.user)
            expected_week_start = expected_today - timezone.timedelta(days=expected_today.weekday())

            self.assertEqual(
                week_response.data["period"]["date_from"],
                str(expected_week_start),
            )
            self.assertEqual(week_response.data["period"]["date_to"], str(expected_today))

            year_response = self.client.get(
                reverse("finance:dashboard-summary"),
                data={
                    "period": "year",
                },
            )

            self.assertEqual(year_response.status_code, status.HTTP_200_OK)
            self.assertEqual(year_response.data["period"]["type"], "year")
            self.assertEqual(
                year_response.data["period"]["date_from"],
                str(expected_today.replace(month=1, day=1)),
            )
            self.assertEqual(year_response.data["period"]["date_to"], str(expected_today))

    def test_dashboard_summary_converts_totals_to_display_currency(self):
            self.authenticate()
            self.set_rate("USD", "100.00000000")

            usd_account = Account.objects.create(
                user=self.user,
                name="USD account",
                balance=Decimal("100.00"),
                currency="USD",
            )
            usd_income_category = Category.objects.create(
                user=self.user,
                name="USD income",
                type=TransactionType.INCOME,
            )
            usd_expense_category = Category.objects.create(
                user=self.user,
                name="USD expense",
                type=TransactionType.EXPENSE,
            )

            self.create_transaction(
                account=usd_account,
                category=usd_income_category,
                type=TransactionType.INCOME,
                amount="300.00",
                description="USD income transaction",
                operation_date=self.today,
            )
            self.create_transaction(
                account=usd_account,
                category=usd_expense_category,
                type=TransactionType.EXPENSE,
                amount="75.00",
                description="USD expense transaction",
                operation_date=self.today,
            )
            self.create_transaction(
                account=self.account,
                category=self.income_category,
                type=TransactionType.INCOME,
                amount="50000.00",
                description="RUB income transaction",
                operation_date=self.today,
            )

            response = self.client.get(
                reverse("finance:dashboard-summary"),
                data={
                    "currency": "usd",
                },
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["currency"], "USD")
            self.assertEqual(response.data["totals"]["accounts_balance"], "230.00")
            self.assertEqual(
                response.data["totals"]["accountsBalance"],
                {"amount": 230.0, "currency": "USD"},
            )
            self.assertEqual(response.data["totals"]["income"], "800.00")
            self.assertEqual(
                response.data["totals"]["incomeAmount"],
                {"amount": 800.0, "currency": "USD"},
            )
            self.assertEqual(response.data["totals"]["expense"], "75.00")
            self.assertEqual(
                response.data["totals"]["expenseAmount"],
                {"amount": 75.0, "currency": "USD"},
            )
            self.assertEqual(response.data["totals"]["net"], "725.00")
            self.assertEqual(
                response.data["totals"]["netAmount"],
                {"amount": 725.0, "currency": "USD"},
            )

            descriptions = [
                item["description"]
                for item in response.data["recent_transactions"]
            ]

            self.assertIn("USD income transaction", descriptions)
            self.assertIn("USD expense transaction", descriptions)
            self.assertIn("RUB income transaction", descriptions)

    def test_dashboard_summary_limit_controls_recent_transactions(self):
            self.authenticate()

            for index in range(5):
                self.create_transaction(
                    account=self.account,
                    category=self.expense_category,
                    type=TransactionType.EXPENSE,
                    amount=str(Decimal("100.00") + index),
                    description=f"Операция dashboard {index}",
                    operation_date=self.today - timezone.timedelta(days=index),
                )

            response = self.client.get(
                reverse("finance:dashboard-summary"),
                data={
                    "limit": 3,
                },
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(len(response.data["recent_transactions"]), 3)

    def test_dashboard_summary_invalid_params_return_bad_request(self):
            self.authenticate()

            invalid_period_response = self.client.get(
                reverse("finance:dashboard-summary"),
                data={
                    "period": "wrong",
                },
            )

            self.assertEqual(
                invalid_period_response.status_code,
                status.HTTP_400_BAD_REQUEST,
            )
            self.assertFalse(invalid_period_response.data["success"])
            self.assertIn(
                "period",
                invalid_period_response.data["error"]["field_errors"],
            )

            custom_without_dates_response = self.client.get(
                reverse("finance:dashboard-summary"),
                data={
                    "period": "custom",
                },
            )

            self.assertEqual(
                custom_without_dates_response.status_code,
                status.HTTP_400_BAD_REQUEST,
            )
            self.assertFalse(custom_without_dates_response.data["success"])
            self.assertIn(
                "date_from",
                custom_without_dates_response.data["error"]["field_errors"],
            )

            wrong_date_range_response = self.client.get(
                reverse("finance:dashboard-summary"),
                data={
                    "period": "custom",
                    "date_from": str(self.today),
                    "date_to": str(self.today - timezone.timedelta(days=1)),
                },
            )

            self.assertEqual(
                wrong_date_range_response.status_code,
                status.HTTP_400_BAD_REQUEST,
            )
            self.assertFalse(wrong_date_range_response.data["success"])
            self.assertIn(
                "date_from",
                wrong_date_range_response.data["error"]["field_errors"],
            )

            invalid_currency_response = self.client.get(
                reverse("finance:dashboard-summary"),
                data={
                    "currency": "RUBLE",
                },
            )

            self.assertEqual(
                invalid_currency_response.status_code,
                status.HTTP_400_BAD_REQUEST,
            )
            self.assertFalse(invalid_currency_response.data["success"])
            self.assertIn(
                "currency",
                invalid_currency_response.data["error"]["field_errors"],
            )

            invalid_limit_response = self.client.get(
                reverse("finance:dashboard-summary"),
                data={
                    "limit": 1000,
                },
            )

            self.assertEqual(
                invalid_limit_response.status_code,
                status.HTTP_400_BAD_REQUEST,
            )
            self.assertFalse(invalid_limit_response.data["success"])
            self.assertIn(
                "limit",
                invalid_limit_response.data["error"]["field_errors"],
            )

    def test_dashboard_summary_uses_cache_for_same_query_params(self):
            self.authenticate()

            self.create_transaction(
                account=self.account,
                category=self.income_category,
                type=TransactionType.INCOME,
                amount="10000.00",
                description="Доход до кэша",
                operation_date=self.today,
            )

            first_response = self.client.get(
                reverse("finance:dashboard-summary"),
                data={
                    "period": "month",
                    "currency": "RUB",
                    "limit": 5,
                },
            )

            self.assertEqual(first_response.status_code, status.HTTP_200_OK)
            self.assertEqual(first_response.data["totals"]["income"], "10000.00")

            self.create_transaction(
                account=self.account,
                category=self.income_category,
                type=TransactionType.INCOME,
                amount="5000.00",
                description="Доход после кэша",
                operation_date=self.today,
            )

            second_response = self.client.get(
                reverse("finance:dashboard-summary"),
                data={
                    "period": "month",
                    "currency": "RUB",
                    "limit": 5,
                },
            )

            self.assertEqual(second_response.status_code, status.HTTP_200_OK)
            self.assertEqual(second_response.data["totals"]["income"], "10000.00")

            cache.clear()

            third_response = self.client.get(
                reverse("finance:dashboard-summary"),
                data={
                    "period": "month",
                    "currency": "RUB",
                    "limit": 5,
                },
            )

            self.assertEqual(third_response.status_code, status.HTTP_200_OK)
            self.assertEqual(third_response.data["totals"]["income"], "15000.00")

    def test_dashboard_summary_cache_depends_on_query_params(self):
            self.authenticate()

            self.create_transaction(
                account=self.account,
                category=self.income_category,
                type=TransactionType.INCOME,
                amount="10000.00",
                description="Доход для month",
                operation_date=self.today,
            )

            month_response = self.client.get(
                reverse("finance:dashboard-summary"),
                data={
                    "period": "month",
                    "currency": "RUB",
                    "limit": 5,
                },
            )

            self.assertEqual(month_response.status_code, status.HTTP_200_OK)
            self.assertEqual(month_response.data["totals"]["income"], "10000.00")

            week_response = self.client.get(
                reverse("finance:dashboard-summary"),
                data={
                    "period": "week",
                    "currency": "RUB",
                    "limit": 5,
                },
            )

            self.assertEqual(week_response.status_code, status.HTTP_200_OK)
            self.assertEqual(week_response.data["period"]["type"], "week")
