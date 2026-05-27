import csv
from decimal import Decimal
from io import BytesIO, StringIO
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook
from rest_framework import status

from apps.finance.currencies.services import ensure_user_currencies, get_user_currency_by_code
from apps.finance.models import Account, Budget, Category, Transaction, TransactionType

from apps.finance.testing import FinanceAPITestCase


@override_settings(CURRENCY_RATES_ENABLED=False)
class FinanceTransactionExportAPITests(FinanceAPITestCase):
    def setUp(self):
            super().setUp()
            ensure_user_currencies(self.user)

    def ensure_usd_currency(self):
            ensure_user_currencies(self.user)
            usd_currency = get_user_currency_by_code(self.user, "USD")
            usd_currency.is_visible = True
            usd_currency.rate_to_primary = Decimal("100.00000000")
            usd_currency.save(update_fields=["is_visible", "rate_to_primary", "updated_at"])
            return usd_currency

    def create_usd_account(self):
            self.ensure_usd_currency()
            return Account.objects.create(
                user=self.user,
                name="USD card",
                initial_balance=Decimal("1000.00"),
                balance=Decimal("1000.00"),
                currency="USD",
            )

    def test_transaction_export_requires_authentication(self):
            response = self.client.get(
                reverse("finance:transaction-export"),
                data={
                    "format": "csv",
                },
            )

            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
            self.assertFalse(response.data["success"])

    def test_transaction_export_csv_success(self):
            self.authenticate()

            own_transaction = self.create_transaction(
                account=self.account,
                category=self.expense_category,
                type=TransactionType.EXPENSE,
                amount="1245.00",
                description="Покупка продуктов для CSV",
                operation_date=self.today,
            )
            self.create_transaction(
                user=self.other_user,
                account=self.other_account,
                category=self.other_category,
                type=TransactionType.EXPENSE,
                amount="999.00",
                description="Чужая операция CSV",
                operation_date=self.today,
            )

            response = self.client.get(
                reverse("finance:transaction-export"),
                data={
                    "format": "csv",
                },
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
            self.assertIn("attachment;", response["Content-Disposition"])
            self.assertIn(".csv", response["Content-Disposition"])

            decoded_content = response.content.decode("utf-8-sig")
            csv_reader = csv.DictReader(StringIO(decoded_content))
            rows = list(csv_reader)

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["Дата"], own_transaction.operation_date.isoformat())
            self.assertEqual(rows[0]["Тип"], "Расход")
            self.assertEqual(rows[0]["Сумма"], "-1245.00")
            self.assertEqual(rows[0]["Валюта"], self.account.currency)
            self.assertEqual(rows[0]["Исходная сумма"], "-1245.00")
            self.assertEqual(rows[0]["Исходная валюта"], self.account.currency)
            self.assertEqual(response["X-Currency-Code"], "RUB")
            self.assertEqual(rows[0]["Описание"], "Покупка продуктов для CSV")
            self.assertEqual(rows[0]["Категория"], self.expense_category.name)
            self.assertEqual(rows[0]["Счёт"], self.account.name)

            self.assertNotIn("Чужая операция CSV", decoded_content)

    def test_transaction_export_converts_amounts_to_display_currency(self):
            self.authenticate()
            usd_account = self.create_usd_account()
            rub_transaction = self.create_transaction(
                account=self.account,
                category=self.expense_category,
                type=TransactionType.EXPENSE,
                amount="1000.00",
                description="RUB expense for export",
                operation_date=self.today,
            )
            usd_transaction = self.create_transaction(
                account=usd_account,
                category=self.expense_category,
                type=TransactionType.EXPENSE,
                amount="10.00",
                description="USD expense for export",
                operation_date=self.today,
            )

            response = self.client.get(
                reverse("finance:transaction-export"),
                data={
                    "format": "csv",
                    "currency": "USD",
                },
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response["X-Currency-Code"], "USD")
            decoded_content = response.content.decode("utf-8-sig")
            rows = list(csv.DictReader(StringIO(decoded_content)))
            rows_by_description = {row["Описание"]: row for row in rows}

            rub_row = rows_by_description["RUB expense for export"]
            usd_row = rows_by_description["USD expense for export"]

            self.assertEqual(rub_row["Сумма"], "-10.00")
            self.assertEqual(rub_row["Валюта"], "USD")
            self.assertEqual(rub_row["Исходная сумма"], "-1000.00")
            self.assertEqual(rub_row["Исходная валюта"], "RUB")
            self.assertEqual(usd_row["Сумма"], "-10.00")
            self.assertEqual(usd_row["Валюта"], "USD")
            self.assertEqual(usd_row["Исходная сумма"], "-10.00")
            self.assertEqual(usd_row["Исходная валюта"], "USD")
            self.assertIn(rub_transaction.description, rows_by_description)
            self.assertIn(usd_transaction.description, rows_by_description)

    def test_transaction_export_filters_by_source_currency_with_account_currency(self):
            self.authenticate()
            usd_account = self.create_usd_account()
            usd_transaction = self.create_transaction(
                account=usd_account,
                category=self.expense_category,
                type=TransactionType.EXPENSE,
                amount="10.00",
                description="Only USD source export",
                operation_date=self.today,
            )
            self.create_transaction(
                account=self.account,
                category=self.expense_category,
                type=TransactionType.EXPENSE,
                amount="1000.00",
                description="RUB source should be filtered out",
                operation_date=self.today,
            )

            response = self.client.get(
                reverse("finance:transaction-export"),
                data={
                    "format": "csv",
                    "currency": "RUB",
                    "accountCurrency": "USD",
                },
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            decoded_content = response.content.decode("utf-8-sig")
            rows = list(csv.DictReader(StringIO(decoded_content)))

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["Описание"], usd_transaction.description)
            self.assertEqual(rows[0]["Сумма"], "-1000.00")
            self.assertEqual(rows[0]["Валюта"], "RUB")
            self.assertEqual(rows[0]["Исходная валюта"], "USD")
            self.assertNotIn("RUB source should be filtered out", decoded_content)

    def test_transaction_export_xlsx_success(self):
            self.authenticate()

            self.create_transaction(
                account=self.account,
                category=self.income_category,
                type=TransactionType.INCOME,
                amount="50000.00",
                description="Зарплата для XLSX",
                operation_date=self.today,
            )

            response = self.client.get(
                reverse("finance:transaction-export"),
                data={
                    "format": "xlsx",
                },
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(
                response["Content-Type"],
                (
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
            )
            self.assertIn("attachment;", response["Content-Disposition"])
            self.assertIn(".xlsx", response["Content-Disposition"])

            workbook = load_workbook(BytesIO(response.content))
            worksheet = workbook.active

            self.assertEqual(worksheet.title, "Операции")
            self.assertEqual(worksheet["A1"].value, "Дата")
            self.assertEqual(worksheet["B1"].value, "Тип")
            self.assertEqual(worksheet["C1"].value, "Сумма")
            self.assertEqual(worksheet["E1"].value, "Описание")

            self.assertEqual(worksheet["B2"].value, "Доход")
            self.assertEqual(worksheet["C2"].value, "50000.00")
            self.assertEqual(worksheet["E2"].value, "Зарплата для XLSX")

    def test_transaction_export_pdf_success(self):
            self.authenticate()

            self.create_transaction(
                account=self.account,
                category=self.expense_category,
                type=TransactionType.EXPENSE,
                amount="700.00",
                description="Покупка для PDF",
                operation_date=self.today,
            )

            response = self.client.get(
                reverse("finance:transaction-export"),
                data={
                    "format": "pdf",
                },
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response["Content-Type"], "application/pdf")
            self.assertIn("attachment;", response["Content-Disposition"])
            self.assertIn(".pdf", response["Content-Disposition"])
            self.assertTrue(response.content.startswith(b"%PDF"))
            self.assertGreater(len(response.content), 1000)

    def test_transaction_export_uses_list_filters(self):
            self.authenticate()

            target_transaction = self.create_transaction(
                account=self.cash_account,
                category=self.transport_category,
                type=TransactionType.EXPENSE,
                amount="350.00",
                description="Такси для экспорта",
                operation_date=self.today,
            )
            self.create_transaction(
                account=self.account,
                category=self.expense_category,
                type=TransactionType.EXPENSE,
                amount="1200.00",
                description="Продукты не должны попасть",
                operation_date=self.today,
            )
            self.create_transaction(
                account=self.account,
                category=self.income_category,
                type=TransactionType.INCOME,
                amount="50000.00",
                description="Доход не должен попасть",
                operation_date=self.today,
            )

            response = self.client.get(
                reverse("finance:transaction-export"),
                data={
                    "format": "csv",
                    "kind": TransactionType.EXPENSE,
                    "accountId": self.cash_account.id,
                    "categoryId": self.transport_category.id,
                    "dateFrom": str(self.today - timezone.timedelta(days=1)),
                    "dateTo": str(self.today),
                    "amountMin": "100.00",
                    "amountMax": "500.00",
                    "search": "такси",
                },
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)

            decoded_content = response.content.decode("utf-8-sig")
            csv_reader = csv.DictReader(StringIO(decoded_content))
            rows = list(csv_reader)

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["Дата"], target_transaction.operation_date.isoformat())
            self.assertEqual(rows[0]["Описание"], "Такси для экспорта")
            self.assertEqual(rows[0]["Категория"], self.transport_category.name)
            self.assertEqual(rows[0]["Счёт"], self.cash_account.name)

            self.assertNotIn("Продукты не должны попасть", decoded_content)
            self.assertNotIn("Доход не должен попасть", decoded_content)

    def test_transaction_export_invalid_format_returns_bad_request(self):
            self.authenticate()

            response = self.client.get(
                reverse("finance:transaction-export"),
                data={
                    "format": "xml",
                },
            )

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertFalse(response.data["success"])
            self.assertIn("format", response.data["error"]["field_errors"])

    def test_transaction_export_limit_returns_bad_request(self):
            self.authenticate()

            for index in range(3):
                self.create_transaction(
                    amount=str(Decimal("100.00") + index),
                    description=f"Операция для лимита экспорта {index}",
                    operation_date=self.today,
                )

            with patch("apps.finance.transactions.views.MAX_TRANSACTION_EXPORT_ROWS", 2):
                response = self.client.get(
                    reverse("finance:transaction-export"),
                    data={
                        "format": "csv",
                    },
                )

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertFalse(response.data["success"])
            self.assertIn("detail", response.data["error"]["field_errors"])
