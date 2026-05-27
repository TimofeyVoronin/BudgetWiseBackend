import base64
from datetime import date
from decimal import Decimal

from django.test import override_settings
from django.urls import reverse
from rest_framework import status

from apps.finance.currencies.services import ensure_user_currencies, get_user_currency_by_code
from apps.finance.models import Account, PlannedStatus, PlannedTransaction, TransactionType
from apps.finance.testing import FinanceAPITestCase
from apps.users.models import AppDateFormat, AppNumberFormat, UserAppSettings


@override_settings(CURRENCY_RATES_ENABLED=False)
class FinancialCalendarExportAPITests(FinanceAPITestCase):
    def create_planned(
        self,
        *,
        name="Плановая операция",
        type=TransactionType.EXPENSE,
        amount="100.00",
        planned_date=None,
        account=None,
        category=None,
        status=PlannedStatus.PENDING,
        include_in_forecast=True,
    ):
        return PlannedTransaction.objects.create(
            user=self.user,
            account=account or self.account,
            category=category or self.expense_category,
            name=name,
            type=type,
            amount=Decimal(amount),
            planned_date=planned_date or self.today,
            status=status,
            include_in_forecast=include_in_forecast,
        )

    def ensure_usd_currency(self):
        ensure_user_currencies(self.user)
        usd_currency = get_user_currency_by_code(self.user, "USD")
        usd_currency.is_visible = True
        usd_currency.rate_to_primary = Decimal("100.00000000")
        usd_currency.save(update_fields=["is_visible", "rate_to_primary", "updated_at"])
        return usd_currency

    def create_usd_account(self, *, balance="100.00"):
        self.ensure_usd_currency()
        return Account.objects.create(
            user=self.user,
            name="USD card",
            initial_balance=Decimal(balance),
            balance=Decimal(balance),
            currency="USD",
        )

    def test_export_preview_requires_authentication(self):
        response = self.client.get(reverse("finance:financial-calendar-export-preview"))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(response.data["success"])

    def test_export_preview_returns_rows_for_selected_month(self):
        self.authenticate()
        selected_date = date(2026, 5, 15)
        self.create_transaction(
            type=TransactionType.INCOME,
            category=self.income_category,
            amount="25000.00",
            description="Подработка",
            operation_date=selected_date,
        )
        self.create_planned(
            name="Оплата интернета",
            amount="850.00",
            planned_date=selected_date,
        )

        response = self.client.get(
            reverse("finance:financial-calendar-export-preview"),
            data={"year": 2026, "month": 5},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["rows"]), 31)
        row = next(item for item in response.data["rows"] if item["iso"] == selected_date.isoformat())
        self.assertEqual(row["date"], "15.05.2026")
        self.assertIn("Подработка", row["eventsSummary"])
        self.assertIn("Оплата интернета", row["eventsSummary"])
        self.assertIn("actualRub", row)
        self.assertIn("forecastRub", row)
        self.assertIn(row["riskLevel"], {"safe", "caution", "risk"})

    def test_export_preview_applies_user_date_format_and_filters(self):
        self.authenticate()
        selected_date = date(2026, 5, 15)
        UserAppSettings.objects.update_or_create(
            user=self.user,
            defaults={
                "timezone": "Europe/Moscow",
                "date_format": AppDateFormat.YYYY_MM_DD,
                "number_format": AppNumberFormat.EN_US,
                "default_currency": "RUB",
            },
        )
        income = self.create_transaction(
            account=self.account,
            type=TransactionType.INCOME,
            category=self.income_category,
            amount="25000.00",
            description="Подработка",
            operation_date=selected_date,
        )
        self.create_transaction(
            account=self.cash_account,
            type=TransactionType.EXPENSE,
            category=self.expense_category,
            amount="500.00",
            description="Продукты",
            operation_date=selected_date,
        )

        response = self.client.get(
            reverse("finance:financial-calendar-export-preview"),
            data={
                "year": 2026,
                "month": 5,
                "accountIds": str(self.account.id),
                "eventTypes": "income",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        row = next(item for item in response.data["rows"] if item["iso"] == selected_date.isoformat())
        self.assertEqual(row["date"], "2026-05-15")
        self.assertIn("Подработка", row["eventsSummary"])
        self.assertNotIn("Продукты", row["eventsSummary"])
        self.assertTrue(
            any(item["eventsSummary"] == "Подработка" for item in response.data["rows"]),
            f"income transaction {income.id} should be present in export preview",
        )

    def test_export_returns_data_url_and_file_name_for_csv(self):
        self.authenticate()
        selected_date = date(2026, 5, 15)
        self.create_transaction(
            type=TransactionType.INCOME,
            category=self.income_category,
            amount="25000.00",
            description="Подработка",
            operation_date=selected_date,
        )

        response = self.client.post(
            reverse("finance:financial-calendar-export"),
            data={
                "year": 2026,
                "month": 5,
                "format": "csv",
                "columns": {
                    "actual": True,
                    "balance": True,
                    "events": True,
                    "risks": False,
                },
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["fileName"].startswith("financial_calendar_2026_05_"))
        self.assertTrue(response.data["fileName"].endswith(".csv"))
        self.assertTrue(response.data["downloadUrl"].startswith("data:text/csv;charset=utf-8;base64,"))

        encoded_content = response.data["downloadUrl"].split(",", 1)[1]
        decoded_content = base64.b64decode(encoded_content).decode("utf-8-sig")
        self.assertIn("Дата", decoded_content)
        self.assertIn("Факт ₽", decoded_content)
        self.assertIn("Баланс ₽", decoded_content)
        self.assertIn("События", decoded_content)
        self.assertNotIn("Риск", decoded_content.splitlines()[0])
        self.assertIn("Подработка", decoded_content)

    def test_export_uses_selected_display_currency_in_csv_headers(self):
        self.authenticate()
        selected_date = date(2026, 5, 15)
        usd_account = self.create_usd_account(balance="100.00")
        self.create_transaction(
            account=usd_account,
            type=TransactionType.EXPENSE,
            category=self.expense_category,
            amount="10.00",
            description="USD expense",
            operation_date=selected_date,
        )

        response = self.client.post(
            reverse("finance:financial-calendar-export"),
            data={
                "year": 2026,
                "month": 5,
                "format": "csv",
                "currency": "USD",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        encoded_content = response.data["downloadUrl"].split(",", 1)[1]
        decoded_content = base64.b64decode(encoded_content).decode("utf-8-sig")
        header = decoded_content.splitlines()[0]
        self.assertIn("Факт $", header)
        self.assertIn("Баланс $", header)
        self.assertNotIn("Факт ₽", header)

    def test_export_supports_xlsx_and_rejects_invalid_format(self):
        self.authenticate()

        xlsx_response = self.client.post(
            reverse("finance:financial-calendar-export"),
            data={"year": 2026, "month": 5, "format": "xlsx"},
            format="json",
        )
        self.assertEqual(xlsx_response.status_code, status.HTTP_200_OK)
        self.assertTrue(xlsx_response.data["fileName"].endswith(".xlsx"))
        self.assertTrue(
            xlsx_response.data["downloadUrl"].startswith(
                "data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,"
            )
        )

        invalid_response = self.client.post(
            reverse("finance:financial-calendar-export"),
            data={"year": 2026, "month": 5, "format": "docx"},
            format="json",
        )
        self.assertEqual(invalid_response.status_code, status.HTTP_400_BAD_REQUEST)
