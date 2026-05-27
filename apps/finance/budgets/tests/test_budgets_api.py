from datetime import timedelta
from decimal import Decimal

from django.test import override_settings
from django.urls import reverse
from rest_framework import status

from apps.finance.currencies.services import ensure_user_currencies, get_user_currency_by_code
from apps.finance.models import (
    Account,
    Budget,
    BudgetCategoryGroup,
    BudgetKind,
    BudgetPeriodType,
    Category,
    TransactionType,
)
from apps.finance.testing import FinanceAPITestCase


@override_settings(CURRENCY_RATES_ENABLED=False)
class FinanceBudgetsAPITests(FinanceAPITestCase):
    def create_budget(
        self,
        *,
        user=None,
        category=None,
        category_group=BudgetCategoryGroup.MAIN,
        period_type=BudgetPeriodType.MONTH,
        amount_limit="10000.00",
        period_start=None,
        period_end=None,
        currency="RUB",
        kind=BudgetKind.EXPENSE,
        rollover=False,
        paused=False,
        is_active=True,
        comment="",
    ):
        period_start = period_start or self.today.replace(day=1)
        period_end = period_end or (period_start + timedelta(days=27))

        return Budget.objects.create(
            user=user or self.user,
            category=category or self.expense_category,
            category_group=category_group,
            period_type=period_type,
            amount_limit=Decimal(amount_limit),
            period_start=period_start,
            period_end=period_end,
            currency=currency,
            kind=kind,
            rollover=rollover,
            paused=paused,
            is_active=is_active,
            comment=comment,
        )

    def get_budget_ids(self, response):
        return [item["id"] for item in response.data["items"]]

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

    def test_budget_list_requires_authentication(self):
        response = self.client.get(reverse("finance:budget-list"))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_budget_list_returns_only_current_user_budgets_with_summary_and_pagination(self):
        self.authenticate()
        own_budget = self.create_budget(comment="Мой бюджет")
        other_budget = self.create_budget(
            user=self.other_user,
            category=self.other_category,
            comment="Чужой бюджет",
        )

        response = self.client.get(reverse("finance:budget-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("items", response.data)
        self.assertIn("summary", response.data)
        self.assertIn("pagination", response.data)
        self.assertEqual(response.data["summary"]["totalCount"], 1)
        self.assertEqual(response.data["pagination"]["totalItems"], 1)
        budget_ids = self.get_budget_ids(response)
        self.assertIn(own_budget.id, budget_ids)
        self.assertNotIn(other_budget.id, budget_ids)

    def test_create_budget_success(self):
        self.authenticate()
        period_start = self.today.replace(day=1)
        period_end = period_start + timedelta(days=30)

        response = self.client.post(
            reverse("finance:budget-list"),
            data={
                "categoryId": self.expense_category.id,
                "categoryGroup": BudgetCategoryGroup.FAMILY,
                "periodType": BudgetPeriodType.MONTH,
                "periodStart": str(period_start),
                "periodEnd": str(period_end),
                "limitRub": 30000,
                "currency": "rub",
                "kind": BudgetKind.EXPENSE,
                "rollover": True,
                "comment": "Лимит на продукты",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        budget = Budget.objects.get(id=response.data["id"])
        self.assertEqual(budget.user, self.user)
        self.assertEqual(budget.category, self.expense_category)
        self.assertEqual(budget.category_group, BudgetCategoryGroup.FAMILY)
        self.assertEqual(budget.period_type, BudgetPeriodType.MONTH)
        self.assertEqual(budget.currency, "RUB")
        self.assertTrue(budget.rollover)
        self.assertEqual(response.data["categoryId"], self.expense_category.id)
        self.assertEqual(response.data["categoryName"], self.expense_category.name)
        self.assertEqual(response.data["limitRub"], 30000.0)
        self.assertEqual(response.data["spentRub"], 0.0)
        self.assertEqual(response.data["usageStatus"], "normal")

    def test_create_budget_rejects_duplicate_category_kind_and_period(self):
        self.authenticate()
        period_start = self.today.replace(day=1)
        period_end = period_start + timedelta(days=30)
        self.create_budget(
            period_start=period_start,
            period_end=period_end,
            category=self.expense_category,
            kind=BudgetKind.EXPENSE,
        )

        response = self.client.post(
            reverse("finance:budget-list"),
            data={
                "categoryId": self.expense_category.id,
                "periodType": BudgetPeriodType.MONTH,
                "periodStart": str(period_start),
                "periodEnd": str(period_end),
                "limitRub": 12000,
                "kind": BudgetKind.EXPENSE,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_budget_rejects_wrong_user_category_and_kind_mismatch(self):
        self.authenticate()
        period_start = self.today.replace(day=1)
        period_end = period_start + timedelta(days=30)

        wrong_user_response = self.client.post(
            reverse("finance:budget-list"),
            data={
                "categoryId": self.other_category.id,
                "periodStart": str(period_start),
                "periodEnd": str(period_end),
                "limitRub": 10000,
                "kind": BudgetKind.EXPENSE,
            },
            format="json",
        )
        self.assertEqual(wrong_user_response.status_code, status.HTTP_400_BAD_REQUEST)

        kind_mismatch_response = self.client.post(
            reverse("finance:budget-list"),
            data={
                "categoryId": self.income_category.id,
                "periodStart": str(period_start),
                "periodEnd": str(period_end),
                "limitRub": 10000,
                "kind": BudgetKind.EXPENSE,
            },
            format="json",
        )
        self.assertEqual(kind_mismatch_response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_budget_list_calculates_spent_percent_and_usage_statuses(self):
        self.authenticate()
        period_start = self.today.replace(day=1)
        period_end = period_start + timedelta(days=30)
        normal_budget = self.create_budget(
            category=self.expense_category,
            amount_limit="10000.00",
            period_start=period_start,
            period_end=period_end,
        )
        warning_budget = self.create_budget(
            category=self.transport_category,
            amount_limit="1000.00",
            period_start=period_start,
            period_end=period_end,
        )
        entertainment_category = Category.objects.create(
            user=self.user,
            name="Развлечения",
            type=TransactionType.EXPENSE,
        )
        exceeded_budget = self.create_budget(
            category=entertainment_category,
            amount_limit="1000.00",
            period_start=period_start,
            period_end=period_end,
        )
        self.create_transaction(
            category=self.expense_category,
            amount="4000.00",
            operation_date=period_start + timedelta(days=1),
        )
        self.create_transaction(
            category=self.transport_category,
            amount="900.00",
            operation_date=period_start + timedelta(days=1),
        )
        self.create_transaction(
            category=entertainment_category,
            amount="1200.00",
            operation_date=period_start + timedelta(days=1),
        )

        response = self.client.get(reverse("finance:budget-list"), data={"perPage": 20})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rows = {item["id"]: item for item in response.data["items"]}
        self.assertEqual(rows[normal_budget.id]["spentRub"], 4000.0)
        self.assertEqual(rows[normal_budget.id]["usagePercent"], 40.0)
        self.assertEqual(rows[normal_budget.id]["usageStatus"], "normal")
        self.assertEqual(rows[warning_budget.id]["usageStatus"], "warning")
        self.assertEqual(rows[warning_budget.id]["usagePercent"], 90.0)
        self.assertEqual(rows[exceeded_budget.id]["usageStatus"], "exceeded")
        self.assertEqual(rows[exceeded_budget.id]["usagePercent"], 120.0)
        self.assertEqual(response.data["summary"]["normalCount"], 1)
        self.assertEqual(response.data["summary"]["attentionCount"], 2)

    def test_budget_usage_includes_child_categories(self):
        self.authenticate()
        child_category = Category.objects.create(
            user=self.user,
            parent=self.expense_category,
            name="Супермаркеты",
            type=TransactionType.EXPENSE,
        )
        budget = self.create_budget(
            category=self.expense_category,
            amount_limit="1000.00",
        )
        self.create_transaction(
            category=child_category,
            amount="250.00",
            operation_date=budget.period_start + timedelta(days=1),
        )

        response = self.client.get(reverse("finance:budget-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rows = {item["id"]: item for item in response.data["items"]}
        self.assertEqual(rows[budget.id]["spentRub"], 250.0)
        self.assertEqual(rows[budget.id]["usagePercent"], 25.0)

    def test_budget_detail_returns_stats_chart_and_operations(self):
        self.authenticate()
        budget = self.create_budget(amount_limit="1000.00")
        transaction = self.create_transaction(
            category=self.expense_category,
            amount="400.00",
            description="Покупка продуктов",
            operation_date=budget.period_start + timedelta(days=2),
        )

        response = self.client.get(
            reverse("finance:budget-detail", kwargs={"pk": budget.id}),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["budget"]["id"], budget.id)
        self.assertEqual(response.data["stats"]["limitRub"], 1000.0)
        self.assertEqual(response.data["stats"]["spentRub"], 400.0)
        self.assertEqual(response.data["stats"]["remainingRub"], 600.0)
        self.assertIn("forecastRub", response.data["stats"])
        self.assertGreaterEqual(len(response.data["chart"]), 1)
        operation_ids = [item["id"] for item in response.data["operations"]]
        self.assertIn(str(transaction.id), operation_ids)

    def test_budget_patch_pause_resume_and_delete(self):
        self.authenticate()
        budget = self.create_budget(amount_limit="1000.00")

        patch_response = self.client.patch(
            reverse("finance:budget-detail", kwargs={"pk": budget.id}),
            data={
                "limitRub": 1500,
                "comment": "Обновлённый комментарий",
            },
            format="json",
        )
        self.assertEqual(patch_response.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_response.data["limitRub"], 1500.0)

        pause_response = self.client.post(
            reverse("finance:budget-pause", kwargs={"pk": budget.id}),
        )
        self.assertEqual(pause_response.status_code, status.HTTP_200_OK)
        self.assertTrue(pause_response.data["paused"])

        resume_response = self.client.post(
            reverse("finance:budget-resume", kwargs={"pk": budget.id}),
        )
        self.assertEqual(resume_response.status_code, status.HTTP_200_OK)
        self.assertFalse(resume_response.data["paused"])

        delete_response = self.client.delete(
            reverse("finance:budget-detail", kwargs={"pk": budget.id}),
        )
        self.assertEqual(delete_response.status_code, status.HTTP_200_OK)
        self.assertEqual(delete_response.data, {"deleted": True, "id": str(budget.id)})
        self.assertFalse(Budget.objects.filter(id=budget.id).exists())

    def test_budget_filters_by_period_category_group_kind_status_and_risk(self):
        self.authenticate()
        period_start = self.today.replace(day=1)
        period_end = period_start + timedelta(days=30)
        month_budget = self.create_budget(
            category=self.expense_category,
            category_group=BudgetCategoryGroup.MAIN,
            period_type=BudgetPeriodType.MONTH,
            amount_limit="1000.00",
            period_start=period_start,
            period_end=period_end,
        )
        quarter_budget = self.create_budget(
            category=self.transport_category,
            category_group=BudgetCategoryGroup.FAMILY,
            period_type=BudgetPeriodType.QUARTER,
            amount_limit="1000.00",
            period_start=period_start + timedelta(days=40),
            period_end=period_start + timedelta(days=130),
        )
        income_budget = self.create_budget(
            category=self.income_category,
            category_group=BudgetCategoryGroup.PERSONAL,
            period_type=BudgetPeriodType.YEAR,
            amount_limit="100000.00",
            period_start=period_start,
            period_end=period_start + timedelta(days=364),
            kind=BudgetKind.INCOME,
        )
        self.create_transaction(
            category=self.transport_category,
            amount="950.00",
            operation_date=quarter_budget.period_start + timedelta(days=1),
        )

        quarter_response = self.client.get(
            reverse("finance:budget-list"),
            data={"periodTab": BudgetPeriodType.QUARTER},
        )
        self.assertEqual(self.get_budget_ids(quarter_response), [quarter_budget.id])

        category_response = self.client.get(
            reverse("finance:budget-list"),
            data={"categories": str(self.expense_category.id)},
        )
        self.assertEqual(self.get_budget_ids(category_response), [month_budget.id])

        group_response = self.client.get(
            reverse("finance:budget-list"),
            data={"categoryGroups": BudgetCategoryGroup.PERSONAL},
        )
        self.assertEqual(self.get_budget_ids(group_response), [income_budget.id])

        kind_response = self.client.get(
            reverse("finance:budget-list"),
            data={"kinds": BudgetKind.INCOME},
        )
        self.assertEqual(self.get_budget_ids(kind_response), [income_budget.id])

        risk_response = self.client.get(
            reverse("finance:budget-list"),
            data={"onlyAtRisk": "true"},
        )
        self.assertEqual(self.get_budget_ids(risk_response), [quarter_budget.id])

        status_response = self.client.get(
            reverse("finance:budget-list"),
            data={"usageStatuses": "warning"},
        )
        self.assertEqual(self.get_budget_ids(status_response), [quarter_budget.id])

    def test_budget_search_and_pagination(self):
        self.authenticate()
        target = self.create_budget(comment="ежемесячные продукты")
        self.create_budget(
            category=self.transport_category,
            period_start=self.today.replace(day=1) + timedelta(days=40),
            period_end=self.today.replace(day=1) + timedelta(days=70),
            comment="такси и автобусы",
        )

        response = self.client.get(
            reverse("finance:budget-list"),
            data={"search": "продукты", "page": 1, "perPage": 1},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.get_budget_ids(response), [target.id])
        self.assertEqual(response.data["pagination"]["page"], 1)
        self.assertEqual(response.data["pagination"]["perPage"], 1)
        self.assertEqual(response.data["pagination"]["totalItems"], 1)

    def test_budget_warnings_endpoint_returns_only_attention_budgets(self):
        self.authenticate()
        normal_budget = self.create_budget(
            category=self.expense_category,
            amount_limit="1000.00",
        )
        warning_budget = self.create_budget(
            category=self.transport_category,
            amount_limit="1000.00",
        )
        self.create_transaction(
            category=self.expense_category,
            amount="200.00",
            operation_date=normal_budget.period_start + timedelta(days=1),
        )
        self.create_transaction(
            category=self.transport_category,
            amount="1100.00",
            operation_date=warning_budget.period_start + timedelta(days=1),
        )

        response = self.client.get(reverse("finance:budget-warnings"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["attentionCount"], 1)
        self.assertEqual(response.data["items"][0]["budgetId"], str(warning_budget.id))
        self.assertEqual(response.data["items"][0]["status"], "exceeded")
        self.assertNotEqual(response.data["items"][0]["budgetId"], str(normal_budget.id))

    def test_budget_meta_returns_categories_and_option_lists(self):
        self.authenticate()

        response = self.client.get(reverse("finance:budget-meta"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("categories", response.data)
        self.assertIn("categoryGroups", response.data)
        self.assertIn("periodTypes", response.data)
        self.assertIn("currencies", response.data)
        self.assertIn("kinds", response.data)
        self.assertIn("usageStatuses", response.data)
        category_values = [item["value"] for item in response.data["categories"]]
        self.assertIn(str(self.expense_category.id), category_values)

    def test_budget_check_duplicate_endpoint(self):
        self.authenticate()
        budget = self.create_budget(category=self.expense_category)

        duplicate_response = self.client.post(
            reverse("finance:budget-check-duplicate"),
            data={
                "categoryId": self.expense_category.id,
                "periodType": budget.period_type,
                "periodStart": str(budget.period_start),
                "periodEnd": str(budget.period_end),
                "kind": budget.kind,
            },
            format="json",
        )
        self.assertEqual(duplicate_response.status_code, status.HTTP_200_OK)
        self.assertTrue(duplicate_response.data["isDuplicate"])

        exclude_response = self.client.post(
            reverse("finance:budget-check-duplicate"),
            data={
                "excludeId": budget.id,
                "categoryId": self.expense_category.id,
                "periodType": budget.period_type,
                "periodStart": str(budget.period_start),
                "periodEnd": str(budget.period_end),
                "kind": budget.kind,
            },
            format="json",
        )
        self.assertEqual(exclude_response.status_code, status.HTTP_200_OK)
        self.assertFalse(exclude_response.data["isDuplicate"])

    def test_budget_validate_endpoint_returns_field_errors_without_400(self):
        self.authenticate()

        response = self.client.post(
            reverse("finance:budget-validate-form"),
            data={
                "categoryName": "",
                "limitRub": 1000,
                "periodStart": str(self.today),
                "periodEnd": str(self.today - timedelta(days=1)),
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["ok"])
        self.assertIn("categoryName", response.data["fieldErrors"])
        self.assertIn("period", response.data["fieldErrors"])


    def test_budget_list_converts_limit_and_spent_to_display_currency(self):
        self.authenticate()
        self.ensure_usd_currency()
        budget = self.create_budget(
            category=self.expense_category,
            amount_limit="100.00",
            currency="USD",
        )
        self.create_transaction(
            account=self.account,
            category=self.expense_category,
            amount="5000.00",
            operation_date=budget.period_start + timedelta(days=1),
        )

        response = self.client.get(
            reverse("finance:budget-list"),
            data={"currency": "RUB"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        row = next(item for item in response.data["items"] if item["id"] == budget.id)
        self.assertEqual(row["sourceCurrency"], "USD")
        self.assertEqual(row["limitRub"], 10000.0)
        self.assertEqual(row["spentRub"], 5000.0)
        self.assertEqual(row["usagePercent"], 50.0)
        self.assertEqual(row["limit"], {"amount": 10000.0, "currency": "RUB"})
        self.assertEqual(row["spent"], {"amount": 5000.0, "currency": "RUB"})
        self.assertEqual(response.data["currencyContext"]["code"], "RUB")

    def test_budget_currency_query_is_display_currency_and_budget_currency_filters_source(self):
        self.authenticate()
        self.ensure_usd_currency()
        rub_budget = self.create_budget(
            category=self.expense_category,
            currency="RUB",
        )
        usd_budget = self.create_budget(
            category=self.transport_category,
            currency="USD",
        )

        display_response = self.client.get(
            reverse("finance:budget-list"),
            data={"currency": "USD", "perPage": 20},
        )
        self.assertEqual(display_response.status_code, status.HTTP_200_OK)
        self.assertIn(rub_budget.id, self.get_budget_ids(display_response))
        self.assertIn(usd_budget.id, self.get_budget_ids(display_response))

        filter_response = self.client.get(
            reverse("finance:budget-list"),
            data={"budgetCurrency": "USD", "perPage": 20},
        )
        self.assertEqual(filter_response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.get_budget_ids(filter_response), [usd_budget.id])

    def test_budget_detail_and_warnings_include_money_payloads(self):
        self.authenticate()
        self.ensure_usd_currency()
        budget = self.create_budget(
            category=self.expense_category,
            amount_limit="100.00",
            currency="USD",
        )
        transaction = self.create_transaction(
            account=self.account,
            category=self.expense_category,
            amount="12000.00",
            operation_date=budget.period_start + timedelta(days=1),
        )

        detail_response = self.client.get(
            reverse("finance:budget-detail", kwargs={"pk": budget.id}),
            data={"currency": "RUB"},
        )

        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.data["stats"]["limit"], {"amount": 10000.0, "currency": "RUB"})
        self.assertEqual(detail_response.data["stats"]["spent"], {"amount": 12000.0, "currency": "RUB"})
        operation = next(
            item for item in detail_response.data["operations"]
            if item["id"] == str(transaction.id)
        )
        self.assertEqual(operation["amount"], {"amount": 12000.0, "currency": "RUB"})
        self.assertEqual(operation["sourceCurrency"], "RUB")

        warnings_response = self.client.get(
            reverse("finance:budget-warnings"),
            data={"currency": "RUB"},
        )

        self.assertEqual(warnings_response.status_code, status.HTTP_200_OK)
        warning = warnings_response.data["items"][0]
        self.assertEqual(warning["budgetId"], str(budget.id))
        self.assertEqual(warning["limit"], {"amount": 10000.0, "currency": "RUB"})
        self.assertEqual(warning["spent"], {"amount": 12000.0, "currency": "RUB"})
        self.assertEqual(warnings_response.data["currencyContext"]["code"], "RUB")

    def test_budget_invalid_query_params_return_400(self):
        self.authenticate()

        invalid_requests = [
            {"periodTab": "wrong"},
            {"periodTypes": "month,wrong"},
            {"categories": "abc"},
            {"categoryGroups": "wrong"},
            {"usageStatuses": "normal,wrong"},
            {"kinds": "expense,wrong"},
            {"onlyAtRisk": "maybe"},
            {"page": "0"},
            {"perPage": "0"},
            {"search": "x" * 101},
        ]

        for query_params in invalid_requests:
            with self.subTest(query_params=query_params):
                response = self.client.get(reverse("finance:budget-list"), data=query_params)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
