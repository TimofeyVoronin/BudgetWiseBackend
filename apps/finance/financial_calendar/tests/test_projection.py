from datetime import timedelta
from decimal import Decimal

from django.test import override_settings
from django.urls import reverse
from rest_framework import status

from apps.finance.models import PlannedStatus, PlannedTransaction, TransactionType
from apps.finance.testing import FinanceAPITestCase


@override_settings(CURRENCY_RATES_ENABLED=False)
class FinancialCalendarProjectionTests(FinanceAPITestCase):
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
            category=category or (
                self.income_category if type == TransactionType.INCOME else self.expense_category
            ),
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

    def test_projected_balance_uses_future_planned_income_and_expense(self):
        self.authenticate()
        self.account.balance = Decimal("10000.00")
        self.account.save(update_fields=["balance"])

        expense_date = self.today + timedelta(days=10)
        income_date = expense_date + timedelta(days=1)
        self.create_planned(
            name="Аренда",
            amount="3000.00",
            planned_date=expense_date,
        )
        self.create_planned(
            name="Подработка",
            type=TransactionType.INCOME,
            amount="1500.00",
            planned_date=income_date,
        )

        response = self.client.get(
            reverse("finance:financial-calendar-month"),
            data={
                "year": expense_date.year,
                "month": expense_date.month,
                "accountIds": self.account.id,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        expense_forecast = self.forecast_for(response, expense_date)
        income_forecast = self.forecast_for(response, income_date)
        self.assertEqual(Decimal(expense_forecast["totalDelta"]), Decimal("-3000.00"))
        self.assertEqual(Decimal(expense_forecast["forecastBalanceRub"]), Decimal("7000.00"))
        self.assertIsNone(expense_forecast["actualBalanceRub"])
        self.assertEqual(Decimal(income_forecast["forecastBalanceRub"]), Decimal("8500.00"))

    def test_actual_balance_for_past_day_is_derived_from_current_account_balance(self):
        self.authenticate()
        past_date = self.today - timedelta(days=3)
        self.account.balance = Decimal("9500.00")
        self.account.save(update_fields=["balance"])
        self.create_transaction(
            amount="500.00",
            operation_date=past_date,
            account=self.account,
            category=self.expense_category,
            type=TransactionType.EXPENSE,
        )

        response = self.client.get(
            reverse("finance:financial-calendar-day", kwargs={"iso": past_date.isoformat()}),
            data={"accountIds": self.account.id},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        day_balance = response.data["dayBalance"]
        self.assertEqual(Decimal(day_balance["totalDelta"]), Decimal("-500.00"))
        self.assertEqual(Decimal(day_balance["actualBalanceRub"]), Decimal("9500.00"))
        self.assertEqual(Decimal(day_balance["forecastBalanceRub"]), Decimal("9500.00"))

    def test_cash_gap_is_detected_when_forecast_balance_goes_negative(self):
        self.authenticate()
        self.account.balance = Decimal("2000.00")
        self.account.save(update_fields=["balance"])
        gap_date = self.today + timedelta(days=7)
        self.create_planned(
            name="Крупная оплата",
            amount="3000.00",
            planned_date=gap_date,
        )

        response = self.client.get(
            reverse("finance:financial-calendar-month"),
            data={
                "year": gap_date.year,
                "month": gap_date.month,
                "accountIds": self.account.id,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        gap_forecast = self.forecast_for(response, gap_date)
        self.assertEqual(gap_forecast["riskLevel"], "risk")
        self.assertIsNotNone(response.data["cashGap"])
        self.assertLessEqual(response.data["cashGap"]["startIso"], gap_date.isoformat())
        self.assertGreaterEqual(response.data["cashGap"]["endIso"], gap_date.isoformat())

    def test_planned_operations_excluded_from_forecast_do_not_change_balance(self):
        self.authenticate()
        self.account.balance = Decimal("10000.00")
        self.account.save(update_fields=["balance"])
        future_date = self.today + timedelta(days=5)
        self.create_planned(
            name="Не учитывать",
            amount="9000.00",
            planned_date=future_date,
            include_in_forecast=False,
        )
        self.create_planned(
            name="Отменено",
            amount="8000.00",
            planned_date=future_date,
            status=PlannedStatus.CANCELLED,
        )

        response = self.client.get(
            reverse("finance:financial-calendar-month"),
            data={
                "year": future_date.year,
                "month": future_date.month,
                "accountIds": self.account.id,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        forecast = self.forecast_for(response, future_date)
        self.assertEqual(Decimal(forecast["totalDelta"]), Decimal("0.00"))
        self.assertEqual(Decimal(forecast["forecastBalanceRub"]), Decimal("10000.00"))
        self.assertFalse(forecast["hasEvents"])

    def test_sharp_change_marks_event_and_sets_caution_risk(self):
        self.authenticate()
        self.account.balance = Decimal("100000.00")
        self.account.save(update_fields=["balance"])
        future_date = self.today + timedelta(days=4)
        planned = self.create_planned(
            name="Крупная покупка",
            amount="30000.00",
            planned_date=future_date,
        )

        response = self.client.get(
            reverse("finance:financial-calendar-month"),
            data={
                "year": future_date.year,
                "month": future_date.month,
                "accountIds": self.account.id,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        event = next(item for item in response.data["events"] if item["id"] == f"planned-{planned.id}")
        forecast = self.forecast_for(response, future_date)
        self.assertTrue(event["isSharpChange"])
        self.assertEqual(forecast["riskLevel"], "caution")
