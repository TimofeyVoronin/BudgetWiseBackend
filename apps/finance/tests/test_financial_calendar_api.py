from datetime import date, timedelta
from decimal import Decimal

from django.urls import reverse
from rest_framework import status

from apps.finance.models import PlannedStatus, PlannedTransaction, TransactionType
from apps.finance.tests.base import FinanceAPITestCase
from apps.users.models import AppDateFormat, AppNumberFormat, UserAppSettings


class FinancialCalendarAPITests(FinanceAPITestCase):
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

    def test_calendar_requires_authentication(self):
        response = self.client.get(reverse("finance:financial-calendar-month"))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(response.data["success"])

    def test_calendar_month_returns_cells_events_and_forecasts(self):
        self.authenticate()
        selected_date = date(2026, 5, 15)
        income = self.create_transaction(
            type=TransactionType.INCOME,
            category=self.income_category,
            amount="25000.00",
            description="Подработка",
            operation_date=selected_date,
        )
        planned = self.create_planned(
            name="Оплата интернета",
            amount="850.00",
            planned_date=selected_date,
        )
        self.create_transaction(
            user=self.other_user,
            account=self.other_account,
            category=self.other_category,
            amount="9999.00",
            operation_date=selected_date,
        )

        response = self.client.get(
            reverse("finance:financial-calendar-month"),
            data={"year": 2026, "month": 5},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["year"], 2026)
        self.assertEqual(response.data["month"], 5)
        self.assertIn("cells", response.data)
        self.assertGreaterEqual(len(response.data["cells"]), 35)
        event_ids = {item["id"] for item in response.data["events"]}
        self.assertIn(f"tx-{income.id}", event_ids)
        self.assertIn(f"planned-{planned.id}", event_ids)
        self.assertFalse(any(item.get("sourceId") == self.other_account.id for item in response.data["events"]))

        day_forecast = next(
            item for item in response.data["dayForecasts"] if item["date"] == selected_date.isoformat()
        )
        self.assertEqual(day_forecast["hasEvents"], True)
        self.assertEqual(day_forecast["dateLabel"], "15.05.2026")
        self.assertEqual(Decimal(day_forecast["totalDelta"]), Decimal("24150.00"))
        self.assertEqual(day_forecast["totalDeltaLabel"], "24 150,00 ₽")

        event_labels = {item["id"]: item["amountLabel"] for item in response.data["events"]}
        self.assertEqual(event_labels[f"tx-{income.id}"], "25 000,00 ₽")
        self.assertEqual(event_labels[f"planned-{planned.id}"], "-850,00 ₽")
        self.assertIn("₽", response.data["openingBalanceLabel"])

    def test_calendar_applies_saved_date_and_number_formats_without_breaking_machine_fields(self):
        self.authenticate()
        selected_date = date(2026, 5, 15)
        transaction = self.create_transaction(
            type=TransactionType.EXPENSE,
            category=self.expense_category,
            amount="1250.50",
            description="Покупка",
            operation_date=selected_date,
        )

        settings_response = self.client.patch(
            reverse("app-settings"),
            {
                "timezone": "Europe/Moscow",
                "dateFormat": "YYYY-MM-DD",
                "numberFormat": "en-US",
                "defaultCurrency": "RUB",
            },
            format="json",
        )
        self.assertEqual(settings_response.status_code, status.HTTP_200_OK)

        response = self.client.get(
            reverse("finance:financial-calendar-month"),
            data={"year": 2026, "month": 5},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        event = next(item for item in response.data["events"] if item["id"] == f"tx-{transaction.id}")
        self.assertEqual(event["date"], "2026-05-15")
        self.assertEqual(event["dateLabel"], "2026-05-15")
        self.assertEqual(event["amountRub"], "-1250.50")
        self.assertEqual(event["amountLabel"], "-1,250.50 ₽")

        day_forecast = next(
            item for item in response.data["dayForecasts"] if item["date"] == selected_date.isoformat()
        )
        self.assertEqual(day_forecast["dateLabel"], "2026-05-15")
        self.assertEqual(day_forecast["totalDelta"], "-1250.50")
        self.assertEqual(day_forecast["totalDeltaLabel"], "-1,250.50 ₽")
        self.assertRegex(response.data["todayLabel"], r"^\d{4}-\d{2}-\d{2}$")

    def test_calendar_uses_settings_from_database_when_endpoint_is_called_directly(self):
        self.authenticate()
        selected_date = date(2026, 5, 15)
        transaction = self.create_transaction(
            type=TransactionType.EXPENSE,
            category=self.expense_category,
            amount="1250.50",
            description="Покупка",
            operation_date=selected_date,
        )
        UserAppSettings.objects.update_or_create(
            user=self.user,
            defaults={
                "timezone": "Europe/Moscow",
                "date_format": AppDateFormat.MM_DD_YYYY,
                "number_format": AppNumberFormat.EN_US,
                "default_currency": "RUB",
            },
        )

        response = self.client.get(
            reverse("finance:financial-calendar-events"),
            data={
                "dateFrom": selected_date.isoformat(),
                "dateTo": selected_date.isoformat(),
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["items"]), 1)
        event = response.data["items"][0]
        self.assertEqual(event["id"], f"tx-{transaction.id}")
        self.assertEqual(event["date"], "2026-05-15")
        self.assertEqual(event["dateLabel"], "05/15/2026")
        self.assertEqual(event["amountLabel"], "-1,250.50 ₽")

    def test_calendar_month_filters_by_account_and_event_type(self):
        self.authenticate()
        selected_date = date(2026, 5, 20)
        self.create_transaction(
            account=self.account,
            type=TransactionType.INCOME,
            category=self.income_category,
            amount="1000.00",
            operation_date=selected_date,
        )
        self.create_transaction(
            account=self.cash_account,
            type=TransactionType.EXPENSE,
            category=self.expense_category,
            amount="500.00",
            operation_date=selected_date,
        )

        response = self.client.get(
            reverse("finance:financial-calendar-month"),
            data={
                "year": 2026,
                "month": 5,
                "accountIds": str(self.account.id),
                "eventTypes": "income",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["events"]), 1)
        self.assertEqual(response.data["events"][0]["type"], TransactionType.INCOME)
        self.assertEqual(response.data["events"][0]["accountId"], self.account.id)

    def test_calendar_events_endpoint_returns_range_items(self):
        self.authenticate()
        selected_date = self.today + timedelta(days=3)
        planned = self.create_planned(
            name="Коммуналка",
            amount="2000.00",
            planned_date=selected_date,
        )

        response = self.client.get(
            reverse("finance:financial-calendar-events"),
            data={
                "dateFrom": selected_date.isoformat(),
                "dateTo": selected_date.isoformat(),
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["items"]), 1)
        self.assertEqual(response.data["items"][0]["id"], f"planned-{planned.id}")
        self.assertEqual(response.data["items"][0]["status"], "pending")

    def test_calendar_day_endpoint_returns_day_details(self):
        self.authenticate()
        selected_date = self.today
        transaction = self.create_transaction(
            description="Покупка продуктов",
            amount="350.00",
            operation_date=selected_date,
        )

        response = self.client.get(
            reverse("finance:financial-calendar-day", kwargs={"iso": selected_date.isoformat()}),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["iso"], selected_date.isoformat())
        self.assertEqual(response.data["events"][0]["id"], f"tx-{transaction.id}")
        self.assertIsNotNone(response.data["dayBalance"])

    def test_calendar_meta_returns_accounts_event_types_and_timezones(self):
        self.authenticate()

        response = self.client.get(reverse("finance:financial-calendar-meta"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data["accounts"]), 2)
        self.assertEqual(response.data["defaultTimezone"], "Asia/Krasnoyarsk")
        self.assertIn("openingBalanceLabel", response.data)
        self.assertEqual(
            {item["value"] for item in response.data["eventTypes"]},
            {"income", "expense", "transfer", "reminder"},
        )

    def test_calendar_rejects_invalid_month_and_foreign_account(self):
        self.authenticate()

        invalid_month_response = self.client.get(
            reverse("finance:financial-calendar-month"),
            data={"year": 2026, "month": 13},
        )
        self.assertEqual(invalid_month_response.status_code, status.HTTP_400_BAD_REQUEST)

        foreign_account_response = self.client.get(
            reverse("finance:financial-calendar-month"),
            data={"year": 2026, "month": 5, "accountIds": self.other_account.id},
        )
        self.assertEqual(foreign_account_response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_calendar_rejects_invalid_day_iso(self):
        self.authenticate()

        response = self.client.get(
            reverse("finance:financial-calendar-day", kwargs={"iso": "2026-99-99"}),
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
