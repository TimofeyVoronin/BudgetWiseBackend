from datetime import date
from decimal import Decimal

from django.urls import reverse
from rest_framework import status

from apps.finance.models import Account, Goal, GoalStatus, TransactionType

from .base import FinanceAPITestCase


class FinanceDashboardWidgetsAPITests(FinanceAPITestCase):
    def test_dashboard_widgets_require_authentication(self):
        urls = [
            reverse("finance:dashboard-period-currency"),
            reverse("finance:dashboard-balance-summary"),
            reverse("finance:dashboard-accounts-summary"),
            reverse("finance:dashboard-goals-summary"),
            reverse("finance:dashboard-expense-dynamics"),
        ]

        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)

                self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
                self.assertFalse(response.data["success"])

    def test_period_currency_returns_default_settings_and_visible_currencies(self):
        self.authenticate()

        settings_response = self.client.patch(
            "/api/v1/settings/app/",
            {
                "timezone": "Asia/Krasnoyarsk",
                "dateFormat": "DD.MM.YYYY",
                "numberFormat": "ru-RU",
                "defaultCurrency": "USD",
            },
            format="json",
        )
        self.assertEqual(settings_response.status_code, status.HTTP_200_OK)

        response = self.client.get(reverse("finance:dashboard-period-currency"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["defaultPeriod"], "month")
        self.assertEqual(response.data["defaultCurrency"], "USD")
        self.assertEqual(
            response.data["periodOptions"],
            [
                {"value": "week", "label": "Неделя"},
                {"value": "month", "label": "Месяц"},
                {"value": "year", "label": "Год"},
            ],
        )
        currency_values = {item["value"] for item in response.data["currencies"]}
        self.assertIn("RUB", currency_values)
        self.assertIn("USD", currency_values)
        rub_option = next(item for item in response.data["currencies"] if item["value"] == "RUB")
        self.assertEqual(rub_option["title"], "Руб.")

    def test_balance_summary_returns_current_balance_card(self):
        self.authenticate()

        response = self.client.get(reverse("finance:dashboard-balance-summary"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["title"], "Текущий баланс")
        self.assertEqual(response.data["headerIcon"], "wallet")
        self.assertEqual(response.data["amountRub"], 13000.0)
        self.assertEqual(response.data["trendLabel"], "Нет данных для сравнения")

    def test_balance_summary_filters_by_currency_and_validates_period(self):
        self.authenticate()
        Account.objects.create(
            user=self.user,
            name="USD account",
            balance=Decimal("120.00"),
            currency="USD",
        )

        response = self.client.get(
            reverse("finance:dashboard-balance-summary"),
            data={"period": "month", "currency": "usd"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["amountRub"], 120.0)

        invalid_period_response = self.client.get(
            reverse("finance:dashboard-balance-summary"),
            data={"period": "custom"},
        )

        self.assertEqual(invalid_period_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(invalid_period_response.data["success"])
        self.assertIn(
            "period",
            invalid_period_response.data["error"]["field_errors"],
        )

    def test_accounts_summary_returns_active_accounts_preview(self):
        self.authenticate()
        archived_account = Account.objects.create(
            user=self.user,
            name="Архивный счёт",
            balance=Decimal("999.00"),
            currency="RUB",
            is_archived=True,
            is_active=False,
        )
        usd_account = Account.objects.create(
            user=self.user,
            name="USD account",
            balance=Decimal("120.00"),
            currency="USD",
        )

        response = self.client.get(
            reverse("finance:dashboard-accounts-summary"),
            data={"period": "year", "currency": "RUB"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["title"], "Счета")
        self.assertEqual(response.data["headerIcon"], "credit-card")
        self.assertEqual(response.data["footerLinkLabel"], "Все счета")
        row_ids = {item["id"] for item in response.data["rows"]}
        self.assertIn(str(self.account.id), row_ids)
        self.assertIn(str(self.cash_account.id), row_ids)
        self.assertNotIn(str(archived_account.id), row_ids)
        self.assertNotIn(str(usd_account.id), row_ids)

    def test_goals_summary_filters_goals_by_currency(self):
        self.authenticate()
        usd_account = Account.objects.create(
            user=self.user,
            name="USD account",
            balance=Decimal("120.00"),
            currency="USD",
        )
        rub_goal = Goal.objects.create(
            user=self.user,
            account=self.account,
            name="Ремонт",
            target_amount=Decimal("500000.00"),
            current_amount=Decimal("455000.00"),
        )
        no_account_goal = Goal.objects.create(
            user=self.user,
            name="Резерв",
            target_amount=Decimal("100000.00"),
            current_amount=Decimal("25000.00"),
        )
        usd_goal = Goal.objects.create(
            user=self.user,
            account=usd_account,
            name="Поездка",
            target_amount=Decimal("1000.00"),
            current_amount=Decimal("200.00"),
        )
        Goal.objects.create(
            user=self.user,
            name="Закрытая цель",
            target_amount=Decimal("1000.00"),
            current_amount=Decimal("1000.00"),
            status=GoalStatus.COMPLETED,
        )

        rub_response = self.client.get(
            reverse("finance:dashboard-goals-summary"),
            data={"currency": "RUB"},
        )

        self.assertEqual(rub_response.status_code, status.HTTP_200_OK)
        rub_ids = {item["id"] for item in rub_response.data["goals"]}
        self.assertIn(str(rub_goal.id), rub_ids)
        self.assertIn(str(no_account_goal.id), rub_ids)
        self.assertNotIn(str(usd_goal.id), rub_ids)
        rub_goal_row = next(item for item in rub_response.data["goals"] if item["id"] == str(rub_goal.id))
        self.assertEqual(rub_goal_row["targetRub"], 500000.0)
        self.assertEqual(rub_goal_row["currentRub"], 455000.0)
        self.assertEqual(rub_goal_row["percent"], 91.0)

        usd_response = self.client.get(
            reverse("finance:dashboard-goals-summary"),
            data={"currency": "USD"},
        )

        self.assertEqual(usd_response.status_code, status.HTTP_200_OK)
        usd_ids = {item["id"] for item in usd_response.data["goals"]}
        self.assertEqual(usd_ids, {str(usd_goal.id)})

    def test_expense_dynamics_returns_weekly_relative_values(self):
        self.authenticate()
        self.create_transaction(
            account=self.account,
            category=self.income_category,
            type=TransactionType.INCOME,
            amount="1000.00",
            operation_date=date(2026, 5, 3),
        )
        self.create_transaction(
            account=self.account,
            category=self.expense_category,
            type=TransactionType.EXPENSE,
            amount="500.00",
            operation_date=date(2026, 5, 4),
        )
        self.create_transaction(
            account=self.account,
            category=self.transport_category,
            type=TransactionType.EXPENSE,
            amount="250.00",
            operation_date=date(2026, 5, 10),
        )
        self.create_transaction(
            account=self.account,
            category=self.income_category,
            type=TransactionType.INCOME,
            amount="900.00",
            operation_date=date(2026, 6, 1),
        )

        response = self.client.get(
            reverse("finance:dashboard-expense-dynamics"),
            data={"month": "2026-05", "currency": "RUB"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["title"], "Динамика расходов и доходов")
        self.assertEqual(response.data["headerIcon"], "bar-chart-3")
        self.assertEqual(response.data["monthLabel"], "Май")
        self.assertEqual(response.data["legendIncome"], "Доходы")
        self.assertEqual(response.data["legendExpenses"], "Расходы")
        self.assertEqual(response.data["yAxisLabels"], ["0", "25", "50", "75", "100"])
        self.assertEqual(response.data["weeks"][0], {"label": "1 неделя", "income": 100, "expenses": 50})
        self.assertEqual(response.data["weeks"][1], {"label": "2 неделя", "income": 0, "expenses": 25})

    def test_expense_dynamics_validates_month(self):
        self.authenticate()

        response = self.client.get(
            reverse("finance:dashboard-expense-dynamics"),
            data={"month": "2026/05"},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        self.assertIn("month", response.data["error"]["field_errors"])
