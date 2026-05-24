from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.finance.models import Tag, TagGroup, TransactionType
from apps.finance.testing import FinanceAPITestCase


class FinanceTransactionsByTagAPITests(FinanceAPITestCase):
    def create_tag_group(self, *, user=None, name="Покупки"):
        return TagGroup.objects.create(
            user=user or self.user,
            name=name,
            is_system=False,
        )

    def create_tag(
        self,
        *,
        user=None,
        group=None,
        name="Продукты",
        color="#66BB6A",
        icon="cart",
        is_visible=True,
        description="",
    ):
        return Tag.objects.create(
            user=user or self.user,
            group=group,
            name=name,
            color=color,
            icon=icon,
            is_visible=is_visible,
            description=description,
        )

    def tag_report_url(self, tag):
        return f"/api/v1/finance/tags/{tag.id}/transactions/"

    def create_tagged_transaction(
        self,
        *,
        tag,
        account=None,
        category=None,
        type=TransactionType.EXPENSE,
        amount="100.00",
        description="Операция с тегом",
        operation_date=None,
    ):
        transaction = self.create_transaction(
            account=account or self.account,
            category=category or self.expense_category,
            type=type,
            amount=amount,
            description=description,
            operation_date=operation_date or self.today,
        )
        transaction.tags.add(tag)
        return transaction

    def test_transactions_by_tag_requires_authentication(self):
        tag = self.create_tag(name="Продукты")

        response = self.client.get(self.tag_report_url(tag))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(response.data["success"])

    def test_transactions_by_tag_returns_summary_breakdowns_dynamics_and_page_items(self):
        self.authenticate()
        group = self.create_tag_group(name="Покупки")
        tag = self.create_tag(group=group, name="Семейные расходы")
        other_tag = self.create_tag(group=group, name="Другой тег", color="#FFA726", icon="taxi")

        groceries_transaction = self.create_tagged_transaction(
            tag=tag,
            account=self.account,
            category=self.expense_category,
            type=TransactionType.EXPENSE,
            amount="1200.00",
            description="Покупка продуктов",
            operation_date=self.today,
        )
        taxi_transaction = self.create_tagged_transaction(
            tag=tag,
            account=self.cash_account,
            category=self.transport_category,
            type=TransactionType.EXPENSE,
            amount="600.00",
            description="Такси домой",
            operation_date=self.today - timezone.timedelta(days=1),
        )
        income_transaction = self.create_tagged_transaction(
            tag=tag,
            account=self.account,
            category=self.income_category,
            type=TransactionType.INCOME,
            amount="5000.00",
            description="Возврат денег",
            operation_date=self.today,
        )
        self.create_tagged_transaction(
            tag=other_tag,
            account=self.account,
            category=self.expense_category,
            type=TransactionType.EXPENSE,
            amount="999.00",
            description="Операция другого тега",
            operation_date=self.today,
        )
        self.create_transaction(
            account=self.account,
            category=self.expense_category,
            type=TransactionType.EXPENSE,
            amount="777.00",
            description="Операция без тега",
            operation_date=self.today,
        )

        response = self.client.get(
            self.tag_report_url(tag),
            data={
                "perPage": 2,
                "page": 1,
                "ordering": "-date,-amount",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["tag"],
            {
                "id": tag.id,
                "name": tag.name,
                "groupId": group.id,
                "groupName": group.name,
                "color": tag.color,
                "icon": tag.icon,
                "isVisible": True,
            },
        )
        self.assertEqual(response.data["summary"]["transactionsCount"], 3)
        self.assertEqual(response.data["summary"]["totalIncome"], "5000.00")
        self.assertEqual(response.data["summary"]["totalExpense"], "1800.00")
        self.assertEqual(response.data["summary"]["netAmount"], "3200.00")
        self.assertEqual(response.data["summary"]["averageAmount"], "2266.67")

        self.assertEqual(response.data["pagination"]["page"], 1)
        self.assertEqual(response.data["pagination"]["perPage"], 2)
        self.assertEqual(response.data["pagination"]["totalItems"], 3)
        self.assertEqual(response.data["pagination"]["totalPages"], 2)
        self.assertEqual(len(response.data["items"]), 2)
        self.assertEqual(
            {item["id"] for item in response.data["items"]},
            {income_transaction.id, groceries_transaction.id},
        )
        self.assertTrue(
            all(
                any(item_tag["id"] == tag.id for item_tag in item["tags"])
                for item in response.data["items"]
            )
        )

        categories_by_name = {
            item["categoryName"]: item
            for item in response.data["categories"]
        }
        self.assertEqual(categories_by_name[self.expense_category.name]["expense"], "1200.00")
        self.assertEqual(categories_by_name[self.transport_category.name]["expense"], "600.00")
        self.assertEqual(categories_by_name[self.income_category.name]["income"], "5000.00")
        self.assertEqual(categories_by_name[self.income_category.name]["netAmount"], "5000.00")
        self.assertEqual(categories_by_name[self.expense_category.name]["transactionsCount"], 1)
        self.assertAlmostEqual(categories_by_name[self.income_category.name]["percent"], 73.53)

        accounts_by_name = {
            item["accountName"]: item
            for item in response.data["accounts"]
        }
        self.assertEqual(accounts_by_name[self.account.name]["transactionsCount"], 2)
        self.assertEqual(accounts_by_name[self.account.name]["income"], "5000.00")
        self.assertEqual(accounts_by_name[self.account.name]["expense"], "1200.00")
        self.assertEqual(accounts_by_name[self.cash_account.name]["transactionsCount"], 1)
        self.assertEqual(accounts_by_name[self.cash_account.name]["expense"], "600.00")

        dynamics_by_date = {
            item["date"]: item
            for item in response.data["dynamics"]
        }
        self.assertEqual(dynamics_by_date[str(self.today)]["transactionsCount"], 2)
        self.assertEqual(dynamics_by_date[str(self.today)]["income"], "5000.00")
        self.assertEqual(dynamics_by_date[str(self.today)]["expense"], "1200.00")
        self.assertEqual(
            dynamics_by_date[str(self.today - timezone.timedelta(days=1))]["transactionsCount"],
            1,
        )
        self.assertEqual(
            dynamics_by_date[str(self.today - timezone.timedelta(days=1))]["expense"],
            "600.00",
        )

        second_page_response = self.client.get(
            self.tag_report_url(tag),
            data={
                "perPage": 2,
                "page": 2,
                "ordering": "-date,-amount",
            },
        )

        self.assertEqual(second_page_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(second_page_response.data["items"]), 1)
        self.assertEqual(second_page_response.data["items"][0]["id"], taxi_transaction.id)

    def test_transactions_by_tag_filters_by_date_type_account_category_and_search(self):
        self.authenticate()
        tag = self.create_tag(name="Рабочие расходы")

        groceries_transaction = self.create_tagged_transaction(
            tag=tag,
            account=self.account,
            category=self.expense_category,
            type=TransactionType.EXPENSE,
            amount="1200.00",
            description="Покупка продуктов",
            operation_date=self.today,
        )
        taxi_transaction = self.create_tagged_transaction(
            tag=tag,
            account=self.cash_account,
            category=self.transport_category,
            type=TransactionType.EXPENSE,
            amount="600.00",
            description="Такси домой",
            operation_date=self.today - timezone.timedelta(days=1),
        )
        income_transaction = self.create_tagged_transaction(
            tag=tag,
            account=self.account,
            category=self.income_category,
            type=TransactionType.INCOME,
            amount="5000.00",
            description="Возврат денег",
            operation_date=self.today - timezone.timedelta(days=2),
        )

        type_response = self.client.get(
            self.tag_report_url(tag),
            data={"type": TransactionType.EXPENSE},
        )
        self.assertEqual(type_response.status_code, status.HTTP_200_OK)
        self.assertEqual(type_response.data["summary"]["transactionsCount"], 2)
        self.assertEqual(
            {item["id"] for item in type_response.data["items"]},
            {groceries_transaction.id, taxi_transaction.id},
        )

        kind_alias_response = self.client.get(
            self.tag_report_url(tag),
            data={"kind": TransactionType.INCOME},
        )
        self.assertEqual(kind_alias_response.status_code, status.HTTP_200_OK)
        self.assertEqual(kind_alias_response.data["summary"]["transactionsCount"], 1)
        self.assertEqual(kind_alias_response.data["items"][0]["id"], income_transaction.id)

        date_response = self.client.get(
            self.tag_report_url(tag),
            data={
                "dateFrom": str(self.today - timezone.timedelta(days=1)),
                "dateTo": str(self.today),
                "ordering": "date",
            },
        )
        self.assertEqual(date_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {item["id"] for item in date_response.data["items"]},
            {groceries_transaction.id, taxi_transaction.id},
        )

        account_response = self.client.get(
            self.tag_report_url(tag),
            data={"accounts": str(self.cash_account.id)},
        )
        self.assertEqual(account_response.status_code, status.HTTP_200_OK)
        self.assertEqual(account_response.data["summary"]["transactionsCount"], 1)
        self.assertEqual(account_response.data["items"][0]["id"], taxi_transaction.id)

        account_alias_response = self.client.get(
            self.tag_report_url(tag),
            data={"accountIds": str(self.account.id)},
        )
        self.assertEqual(account_alias_response.status_code, status.HTTP_200_OK)
        self.assertEqual(account_alias_response.data["summary"]["transactionsCount"], 2)
        self.assertEqual(
            {item["id"] for item in account_alias_response.data["items"]},
            {groceries_transaction.id, income_transaction.id},
        )

        category_response = self.client.get(
            self.tag_report_url(tag),
            data={"categories": str(self.transport_category.id)},
        )
        self.assertEqual(category_response.status_code, status.HTTP_200_OK)
        self.assertEqual(category_response.data["summary"]["transactionsCount"], 1)
        self.assertEqual(category_response.data["items"][0]["id"], taxi_transaction.id)

        category_alias_response = self.client.get(
            self.tag_report_url(tag),
            data={"categoryIds": str(self.expense_category.id)},
        )
        self.assertEqual(category_alias_response.status_code, status.HTTP_200_OK)
        self.assertEqual(category_alias_response.data["summary"]["transactionsCount"], 1)
        self.assertEqual(category_alias_response.data["items"][0]["id"], groceries_transaction.id)

        search_response = self.client.get(
            self.tag_report_url(tag),
            data={"search": "такси"},
        )
        self.assertEqual(search_response.status_code, status.HTTP_200_OK)
        self.assertEqual(search_response.data["summary"]["transactionsCount"], 1)
        self.assertEqual(search_response.data["items"][0]["id"], taxi_transaction.id)

    def test_transactions_by_tag_supports_ordering(self):
        self.authenticate()
        tag = self.create_tag(name="Сортировка")

        small = self.create_tagged_transaction(
            tag=tag,
            amount="100.00",
            description="Маленькая операция",
            operation_date=self.today - timezone.timedelta(days=1),
        )
        large = self.create_tagged_transaction(
            tag=tag,
            amount="900.00",
            description="Большая операция",
            operation_date=self.today,
        )

        amount_desc_response = self.client.get(
            self.tag_report_url(tag),
            data={"ordering": "-amount"},
        )
        self.assertEqual(amount_desc_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item["id"] for item in amount_desc_response.data["items"]],
            [large.id, small.id],
        )

        amount_asc_response = self.client.get(
            self.tag_report_url(tag),
            data={"ordering": "amount"},
        )
        self.assertEqual(amount_asc_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item["id"] for item in amount_asc_response.data["items"]],
            [small.id, large.id],
        )

    def test_transactions_by_tag_empty_and_hidden_tag_report(self):
        self.authenticate()
        tag = self.create_tag(name="Пустой отчёт")
        hidden_tag = self.create_tag(name="Скрытый тег", is_visible=False)
        self.create_tagged_transaction(tag=hidden_tag, amount="300.00")

        empty_response = self.client.get(self.tag_report_url(tag))

        self.assertEqual(empty_response.status_code, status.HTTP_200_OK)
        self.assertEqual(empty_response.data["summary"]["transactionsCount"], 0)
        self.assertEqual(empty_response.data["summary"]["totalIncome"], "0.00")
        self.assertEqual(empty_response.data["summary"]["totalExpense"], "0.00")
        self.assertEqual(empty_response.data["items"], [])
        self.assertEqual(empty_response.data["categories"], [])
        self.assertEqual(empty_response.data["accounts"], [])
        self.assertEqual(empty_response.data["dynamics"], [])

        hidden_response = self.client.get(self.tag_report_url(hidden_tag))

        self.assertEqual(hidden_response.status_code, status.HTTP_200_OK)
        self.assertEqual(hidden_response.data["tag"]["id"], hidden_tag.id)
        self.assertFalse(hidden_response.data["tag"]["isVisible"])
        self.assertEqual(hidden_response.data["summary"]["transactionsCount"], 1)

    def test_transactions_by_tag_rejects_missing_foreign_and_invalid_filters(self):
        self.authenticate()
        tag = self.create_tag(name="Ошибки")
        other_tag = self.create_tag(user=self.other_user, name="Чужой тег")

        missing_response = self.client.get("/api/v1/finance/tags/999999/transactions/")
        self.assertEqual(missing_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(missing_response.data["success"])

        foreign_response = self.client.get(self.tag_report_url(other_tag))
        self.assertEqual(foreign_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(foreign_response.data["success"])

        invalid_date_response = self.client.get(
            self.tag_report_url(tag),
            data={"dateFrom": str(self.today), "dateTo": str(self.today - timezone.timedelta(days=1))},
        )
        self.assertEqual(invalid_date_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("dateFrom", invalid_date_response.data["error"]["field_errors"])

        invalid_type_response = self.client.get(
            self.tag_report_url(tag),
            data={"type": "wrong"},
        )
        self.assertEqual(invalid_type_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("type", invalid_type_response.data["error"]["field_errors"])

        invalid_account_response = self.client.get(
            self.tag_report_url(tag),
            data={"accounts": "abc"},
        )
        self.assertEqual(invalid_account_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("accounts", invalid_account_response.data["error"]["field_errors"])

        invalid_category_response = self.client.get(
            self.tag_report_url(tag),
            data={"categories": "abc"},
        )
        self.assertEqual(invalid_category_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("categories", invalid_category_response.data["error"]["field_errors"])

        foreign_account_response = self.client.get(
            self.tag_report_url(tag),
            data={"accounts": str(self.other_account.id)},
        )
        self.assertEqual(foreign_account_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("accounts", foreign_account_response.data["error"]["field_errors"])

        foreign_category_response = self.client.get(
            self.tag_report_url(tag),
            data={"categories": str(self.other_category.id)},
        )
        self.assertEqual(foreign_category_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("categories", foreign_category_response.data["error"]["field_errors"])

        invalid_page_response = self.client.get(
            self.tag_report_url(tag),
            data={"page": "0"},
        )
        self.assertEqual(invalid_page_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("page", invalid_page_response.data["error"]["field_errors"])

        out_of_range_page_response = self.client.get(
            self.tag_report_url(tag),
            data={"page": "2"},
        )
        self.assertEqual(out_of_range_page_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("page", out_of_range_page_response.data["error"]["field_errors"])

    def test_transactions_by_tag_rejects_invalid_ordering_and_long_search(self):
        self.authenticate()
        tag = self.create_tag(name="Поиск")

        invalid_ordering_response = self.client.get(
            self.tag_report_url(tag),
            data={"ordering": "wrong"},
        )
        self.assertEqual(invalid_ordering_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("ordering", invalid_ordering_response.data["error"]["field_errors"])

        long_search_response = self.client.get(
            self.tag_report_url(tag),
            data={"search": "x" * 101},
        )
        self.assertEqual(long_search_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("search", long_search_response.data["error"]["field_errors"])
