from datetime import timedelta
from decimal import Decimal

from django.test import override_settings
from django.urls import reverse
from rest_framework import status

from apps.finance.models import Account, PlannedStatus, PlannedTransaction, TransactionType
from apps.finance.testing import FinanceAPITestCase


@override_settings(CURRENCY_RATES_ENABLED=False)
class FinancialCalendarFlowTests(FinanceAPITestCase):
    def create_planned(
        self,
        *,
        user=None,
        account=None,
        category=None,
        name="Плановая операция",
        type=TransactionType.EXPENSE,
        amount="100.00",
        planned_date=None,
        status=PlannedStatus.PENDING,
        include_in_forecast=True,
    ):
        resolved_user = user or self.user
        resolved_account = account or self.account
        resolved_category = category or (
            self.income_category if type == TransactionType.INCOME else self.expense_category
        )
        return PlannedTransaction.objects.create(
            user=resolved_user,
            account=resolved_account,
            category=resolved_category,
            name=name,
            type=type,
            amount=Decimal(amount),
            planned_date=planned_date or self.today,
            status=status,
            include_in_forecast=include_in_forecast,
        )

    def forecast_for(self, response, target_date):
        return next(
            item for item in response.data["dayForecasts"] if item["date"] == target_date.isoformat()
        )

    def test_month_endpoint_returns_grid_events_and_projected_balances(self):
        self.authenticate()
        self.account.balance = Decimal("10000.00")
        self.account.save(update_fields=["balance"])

        start_date = self.today + timedelta(days=1)
        expense_date = start_date + timedelta(days=1)
        income_date = start_date + timedelta(days=2)

        expense = self.create_planned(
            name="Аренда квартиры",
            amount="3000.00",
            planned_date=expense_date,
        )
        income = self.create_planned(
            name="Подработка",
            type=TransactionType.INCOME,
            amount="1000.00",
            planned_date=income_date,
        )
        self.create_planned(
            name="Не учитывать",
            amount="9999.00",
            planned_date=expense_date,
            include_in_forecast=False,
        )
        self.create_planned(
            name="Отменённая операция",
            amount="8888.00",
            planned_date=expense_date,
            status=PlannedStatus.CANCELLED,
        )
        self.create_planned(
            user=self.other_user,
            account=self.other_account,
            category=self.other_category,
            name="Чужая операция",
            amount="7777.00",
            planned_date=expense_date,
        )

        response = self.client.get(
            reverse("finance:financial-calendar-month"),
            data={
                "year": expense_date.year,
                "month": expense_date.month,
                "dateFrom": start_date.isoformat(),
                "dateTo": income_date.isoformat(),
                "accountIds": str(self.account.id),
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["cells"]), 3)
        self.assertEqual(len(response.data["dayForecasts"]), 3)
        self.assertEqual(
            {event["id"] for event in response.data["events"]},
            {f"planned-{expense.id}", f"planned-{income.id}"},
        )

        expense_forecast = self.forecast_for(response, expense_date)
        income_forecast = self.forecast_for(response, income_date)
        self.assertEqual(Decimal(str(response.data["openingBalanceRub"])), Decimal("10000.00"))
        self.assertEqual(Decimal(str(expense_forecast["totalDelta"])), Decimal("-3000.00"))
        self.assertEqual(Decimal(str(expense_forecast["forecastBalanceRub"])), Decimal("7000.00"))
        self.assertIsNone(expense_forecast["actualBalanceRub"])
        self.assertEqual(Decimal(str(income_forecast["totalDelta"])), Decimal("1000.00"))
        self.assertEqual(Decimal(str(income_forecast["forecastBalanceRub"])), Decimal("8000.00"))

    def test_day_endpoint_combines_confirmed_and_pending_events(self):
        self.authenticate()
        selected_date = self.today
        self.account.balance = Decimal("10500.00")
        self.account.save(update_fields=["balance"])

        transaction = self.create_transaction(
            description="Пятёрочка",
            amount="500.00",
            operation_date=selected_date,
            account=self.account,
            category=self.expense_category,
            type=TransactionType.EXPENSE,
        )
        planned = self.create_planned(
            name="Плановая подработка",
            type=TransactionType.INCOME,
            amount="1200.00",
            planned_date=selected_date,
        )

        response = self.client.get(
            reverse("finance:financial-calendar-day", kwargs={"iso": selected_date.isoformat()}),
            data={"accountIds": str(self.account.id)},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["iso"], selected_date.isoformat())
        self.assertEqual(
            {event["id"] for event in response.data["events"]},
            {f"tx-{transaction.id}", f"planned-{planned.id}"},
        )
        self.assertEqual(Decimal(str(response.data["dayBalance"]["totalDelta"])), Decimal("700.00"))
        self.assertEqual(response.data["dayBalance"]["hasEvents"], True)

    def test_events_endpoint_supports_account_and_event_type_filters(self):
        self.authenticate()
        selected_date = self.today + timedelta(days=4)
        expense_on_main = self.create_planned(
            name="Основной счёт",
            amount="100.00",
            planned_date=selected_date,
            account=self.account,
        )
        expense_on_cash = self.create_planned(
            name="Наличные",
            amount="200.00",
            planned_date=selected_date,
            account=self.cash_account,
        )
        income_on_cash = self.create_planned(
            name="Доход наличными",
            type=TransactionType.INCOME,
            amount="300.00",
            planned_date=selected_date,
            account=self.cash_account,
        )

        cash_only_response = self.client.get(
            reverse("finance:financial-calendar-events"),
            data={
                "dateFrom": selected_date.isoformat(),
                "dateTo": selected_date.isoformat(),
                "accountIds": str(self.cash_account.id),
            },
        )
        self.assertEqual(cash_only_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {event["id"] for event in cash_only_response.data["items"]},
            {f"planned-{expense_on_cash.id}", f"planned-{income_on_cash.id}"},
        )

        expense_only_response = self.client.get(
            reverse("finance:financial-calendar-events"),
            data={
                "dateFrom": selected_date.isoformat(),
                "dateTo": selected_date.isoformat(),
                "accountIds": f"{self.account.id},{self.cash_account.id}",
                "eventTypes": "expense",
            },
        )
        self.assertEqual(expense_only_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {event["id"] for event in expense_only_response.data["items"]},
            {f"planned-{expense_on_main.id}", f"planned-{expense_on_cash.id}"},
        )

    def test_calendar_detects_cash_gap_and_sharp_change(self):
        self.authenticate()
        self.account.balance = Decimal("2000.00")
        self.account.save(update_fields=["balance"])
        gap_date = self.today + timedelta(days=6)
        planned = self.create_planned(
            name="Крупная оплата",
            amount="120000.00",
            planned_date=gap_date,
        )

        response = self.client.get(
            reverse("finance:financial-calendar-month"),
            data={
                "year": gap_date.year,
                "month": gap_date.month,
                "dateFrom": gap_date.isoformat(),
                "dateTo": gap_date.isoformat(),
                "accountIds": str(self.account.id),
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        forecast = self.forecast_for(response, gap_date)
        event = next(event for event in response.data["events"] if event["id"] == f"planned-{planned.id}")
        self.assertEqual(forecast["riskLevel"], "risk")
        self.assertEqual(response.data["cashGap"], {"startIso": gap_date.isoformat(), "endIso": gap_date.isoformat()})
        self.assertTrue(event["isSharpChange"])

    def test_actual_balance_for_past_day_uses_confirmed_transactions_only(self):
        self.authenticate()
        past_date = self.today - timedelta(days=2)
        self.account.balance = Decimal("9000.00")
        self.account.save(update_fields=["balance"])
        self.create_transaction(
            description="Прошлый расход",
            amount="1000.00",
            operation_date=past_date,
            account=self.account,
            category=self.expense_category,
            type=TransactionType.EXPENSE,
        )
        self.create_planned(
            name="Прошлый план",
            amount="5000.00",
            planned_date=past_date,
        )

        response = self.client.get(
            reverse("finance:financial-calendar-day", kwargs={"iso": past_date.isoformat()}),
            data={"accountIds": str(self.account.id)},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(str(response.data["dayBalance"]["totalDelta"])), Decimal("-6000.00"))
        self.assertEqual(Decimal(str(response.data["dayBalance"]["actualBalanceRub"])), Decimal("9000.00"))
        self.assertEqual(Decimal(str(response.data["dayBalance"]["forecastBalanceRub"])), Decimal("4000.00"))

    def test_meta_excludes_inactive_and_archived_accounts(self):
        self.authenticate()
        Account.objects.create(
            user=self.user,
            name="Архивный счёт",
            initial_balance=Decimal("1000.00"),
            balance=Decimal("1000.00"),
            currency="RUB",
            is_active=False,
            is_archived=True,
        )

        response = self.client.get(reverse("finance:financial-calendar-meta"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        account_titles = {item["title"] for item in response.data["accounts"]}
        self.assertIn(self.account.name, account_titles)
        self.assertIn(self.cash_account.name, account_titles)
        self.assertNotIn("Архивный счёт", account_titles)

    def test_calendar_validation_errors_are_user_scoped_and_predictable(self):
        self.authenticate()
        too_long_end = self.today + timedelta(days=371)

        invalid_range_response = self.client.get(
            reverse("finance:financial-calendar-month"),
            data={
                "year": self.today.year,
                "month": self.today.month,
                "dateFrom": too_long_end.isoformat(),
                "dateTo": self.today.isoformat(),
            },
        )
        self.assertEqual(invalid_range_response.status_code, status.HTTP_400_BAD_REQUEST)

        invalid_event_type_response = self.client.get(
            reverse("finance:financial-calendar-events"),
            data={
                "dateFrom": self.today.isoformat(),
                "dateTo": self.today.isoformat(),
                "eventTypes": "wrong",
            },
        )
        self.assertEqual(invalid_event_type_response.status_code, status.HTTP_400_BAD_REQUEST)

        foreign_account_response = self.client.get(
            reverse("finance:financial-calendar-events"),
            data={
                "dateFrom": self.today.isoformat(),
                "dateTo": self.today.isoformat(),
                "accountIds": str(self.other_account.id),
            },
        )
        self.assertEqual(foreign_account_response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthorized_user_cannot_access_calendar_endpoints(self):
        month_response = self.client.get(reverse("finance:financial-calendar-month"))
        events_response = self.client.get(
            reverse("finance:financial-calendar-events"),
            data={"dateFrom": self.today.isoformat(), "dateTo": self.today.isoformat()},
        )
        day_response = self.client.get(
            reverse("finance:financial-calendar-day", kwargs={"iso": self.today.isoformat()}),
        )
        meta_response = self.client.get(reverse("finance:financial-calendar-meta"))

        self.assertEqual(month_response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(events_response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(day_response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(meta_response.status_code, status.HTTP_401_UNAUTHORIZED)
