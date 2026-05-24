from decimal import Decimal

from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.finance.models import (
    Account,
    Category,
    Tag,
    Transaction,
    TransactionTemplate,
    TransactionTemplateStatus,
    TransactionType,
)
from apps.finance.testing import FinanceAPITestCase
from apps.users.app_settings.formatting import get_user_app_today


TEMPLATES_BASE_URL = "/api/v1/finance/transaction-templates/"


class FinanceTransactionTemplatesAPITests(FinanceAPITestCase):
    def create_tag(self, *, user=None, name="обед", is_visible=True):
        return Tag.objects.create(
            user=user or self.user,
            name=name,
            color="#66BB6A",
            icon="cart",
            is_visible=is_visible,
        )

    def create_template(
        self,
        *,
        user=None,
        name="Обед в офисе",
        kind=TransactionType.EXPENSE,
        amount="450.00",
        account=None,
        category=None,
        note="Рабочий обед",
        status=TransactionTemplateStatus.ACTIVE,
        use_count=0,
        last_used_at=None,
        is_default=False,
        tags=None,
    ):
        user = user or self.user
        template = TransactionTemplate.objects.create(
            user=user,
            name=name,
            kind=kind,
            amount=Decimal(amount),
            currency="RUB",
            account=account or self.account,
            category=category or self.expense_category,
            note=note,
            status=status,
            use_count=use_count,
            last_used_at=last_used_at,
            is_default=is_default,
        )

        if tags is not None:
            template.tags.set(tags)

        return template

    def template_ids(self, response):
        return [item["id"] for item in response.data["items"]]

    def test_template_list_requires_authentication(self):
        response = self.client.get(reverse("finance:transaction-template-list"))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(response.data["success"])

    def test_template_list_returns_items_summary_pagination_and_only_current_user_templates(self):
        self.authenticate()
        used_recently = timezone.now()
        own_template = self.create_template(
            name="Обед в офисе",
            use_count=4,
            last_used_at=used_recently,
        )
        archived_template = self.create_template(
            name="Архивный кофе",
            status=TransactionTemplateStatus.ARCHIVED,
        )
        other_template = self.create_template(
            user=self.other_user,
            account=self.other_account,
            category=self.other_category,
            name="Чужой шаблон",
        )

        active_response = self.client.get(reverse("finance:transaction-template-list"))

        self.assertEqual(active_response.status_code, status.HTTP_200_OK)
        self.assertIn("items", active_response.data)
        self.assertIn("summary", active_response.data)
        self.assertIn("pagination", active_response.data)
        self.assertEqual(active_response.data["summary"]["totalCount"], 1)
        self.assertEqual(active_response.data["summary"]["frequentCount"], 1)
        self.assertEqual(active_response.data["pagination"]["totalItems"], 1)
        self.assertEqual(self.template_ids(active_response), [own_template.id])
        self.assertNotIn(other_template.id, self.template_ids(active_response))

        archived_response = self.client.get(
            reverse("finance:transaction-template-list"),
            data={"status": TransactionTemplateStatus.ARCHIVED},
        )

        self.assertEqual(archived_response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.template_ids(archived_response), [archived_template.id])

    def test_create_retrieve_update_and_delete_template(self):
        self.authenticate()
        tag = self.create_tag(name="кофе")

        create_response = self.client.post(
            reverse("finance:transaction-template-list"),
            data={
                "name": "  Кофе   перед   работой ",
                "kind": TransactionType.EXPENSE,
                "amountRub": 180,
                "accountId": self.account.id,
                "categoryId": self.expense_category.id,
                "tagIds": [tag.id],
                "note": "  Американо  ",
                "currency": "rub",
            },
            format="json",
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        template_id = create_response.data["id"]
        template = TransactionTemplate.objects.get(pk=template_id)
        self.assertEqual(template.user, self.user)
        self.assertEqual(template.name, "Кофе перед работой")
        self.assertEqual(template.amount, Decimal("180.00"))
        self.assertEqual(template.currency, "RUB")
        self.assertEqual(list(template.tags.values_list("id", flat=True)), [tag.id])
        self.assertEqual(create_response.data["accountId"], self.account.id)
        self.assertEqual(create_response.data["categoryId"], self.expense_category.id)
        self.assertEqual(create_response.data["amountRub"], 180.0)
        self.assertEqual(create_response.data["tags"][0]["id"], tag.id)

        detail_response = self.client.get(
            reverse("finance:transaction-template-detail", kwargs={"pk": template_id})
        )
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.data["id"], template_id)

        update_response = self.client.patch(
            reverse("finance:transaction-template-detail", kwargs={"pk": template_id}),
            data={
                "name": "Кофе у дома",
                "amountRub": 220,
                "note": "Новый комментарий",
                "tagIds": [],
            },
            format="json",
        )

        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        template.refresh_from_db()
        self.assertEqual(template.name, "Кофе у дома")
        self.assertEqual(template.amount, Decimal("220.00"))
        self.assertEqual(template.tags.count(), 0)

        delete_response = self.client.delete(
            reverse("finance:transaction-template-detail", kwargs={"pk": template_id})
        )

        self.assertEqual(delete_response.status_code, status.HTTP_200_OK)
        self.assertTrue(delete_response.data["deleted"])
        self.assertEqual(delete_response.data["id"], template_id)
        self.assertFalse(TransactionTemplate.objects.filter(pk=template_id).exists())

    def test_template_filters_search_sort_and_pagination(self):
        self.authenticate()
        lunch_tag = self.create_tag(name="обед")
        salary_tag = self.create_tag(name="доход")
        lunch = self.create_template(
            name="Обед в офисе",
            category=self.expense_category,
            account=self.account,
            tags=[lunch_tag],
            use_count=5,
        )
        taxi = self.create_template(
            name="Такси домой",
            category=self.transport_category,
            account=self.cash_account,
            amount="320.00",
            note="Дорога домой",
            use_count=1,
        )
        salary = self.create_template(
            name="Зарплата",
            kind=TransactionType.INCOME,
            category=self.income_category,
            account=self.account,
            amount="85000.00",
            note="Основное место работы",
            tags=[salary_tag],
            use_count=10,
        )

        search_response = self.client.get(
            reverse("finance:transaction-template-list"),
            data={"search": "обед"},
        )
        self.assertEqual(search_response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.template_ids(search_response), [lunch.id])

        category_response = self.client.get(
            reverse("finance:transaction-template-list"),
            data={"categories": str(self.transport_category.id)},
        )
        self.assertEqual(category_response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.template_ids(category_response), [taxi.id])

        account_response = self.client.get(
            reverse("finance:transaction-template-list"),
            data={"accounts": str(self.cash_account.id)},
        )
        self.assertEqual(account_response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.template_ids(account_response), [taxi.id])

        tag_response = self.client.get(
            reverse("finance:transaction-template-list"),
            data={"tagIds": str(salary_tag.id)},
        )
        self.assertEqual(tag_response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.template_ids(tag_response), [salary.id])

        tag_query_response = self.client.get(
            reverse("finance:transaction-template-list"),
            data={"tagQuery": "обед"},
        )
        self.assertEqual(tag_query_response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.template_ids(tag_query_response), [lunch.id])

        sort_response = self.client.get(
            reverse("finance:transaction-template-list"),
            data={"sortBy": "useCount", "sortOrder": "desc", "perPage": 2},
        )
        self.assertEqual(sort_response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.template_ids(sort_response), [salary.id, lunch.id])
        self.assertEqual(sort_response.data["pagination"]["totalItems"], 3)
        self.assertEqual(sort_response.data["pagination"]["totalPages"], 2)

    def test_template_meta_uses_app_default_currency_after_settings_update(self):
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

        response = self.client.get(f"{TEMPLATES_BASE_URL}meta/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["defaultCurrency"], "USD")
        usd_option = next(item for item in response.data["currencies"] if item["value"] == "USD")
        self.assertTrue(usd_option["isDefault"])

    def test_template_custom_actions_archive_restore_duplicate_apply_draft_and_meta(self):
        self.authenticate()
        tag = self.create_tag(name="обед")
        template = self.create_template(tags=[tag])

        meta_response = self.client.get(f"{TEMPLATES_BASE_URL}meta/")
        self.assertEqual(meta_response.status_code, status.HTTP_200_OK)
        self.assertIn("kinds", meta_response.data)
        self.assertIn("categories", meta_response.data)
        self.assertIn("accounts", meta_response.data)

        draft_response = self.client.get(f"{TEMPLATES_BASE_URL}{template.id}/apply-draft/")
        self.assertEqual(draft_response.status_code, status.HTTP_200_OK)
        self.assertEqual(draft_response.data["templateId"], template.id)
        self.assertEqual(draft_response.data["templateName"], template.name)
        self.assertEqual(draft_response.data["tagIds"], [tag.id])
        self.assertEqual(str(draft_response.data["operationDate"]), str(get_user_app_today(self.user)))

        duplicate_response = self.client.post(f"{TEMPLATES_BASE_URL}{template.id}/duplicate/")
        self.assertEqual(duplicate_response.status_code, status.HTTP_201_CREATED)
        duplicate_id = duplicate_response.data["id"]
        self.assertNotEqual(duplicate_id, template.id)
        self.assertIn("копия", duplicate_response.data["name"])
        self.assertEqual([item["id"] for item in duplicate_response.data["tags"]], [tag.id])

        archive_response = self.client.post(f"{TEMPLATES_BASE_URL}{template.id}/archive/")
        self.assertEqual(archive_response.status_code, status.HTTP_200_OK)
        self.assertEqual(archive_response.data["template"]["status"], TransactionTemplateStatus.ARCHIVED)
        template.refresh_from_db()
        self.assertEqual(template.status, TransactionTemplateStatus.ARCHIVED)

        archived_draft_response = self.client.get(f"{TEMPLATES_BASE_URL}{template.id}/apply-draft/")
        self.assertEqual(archived_draft_response.status_code, status.HTTP_400_BAD_REQUEST)

        restore_response = self.client.post(f"{TEMPLATES_BASE_URL}{template.id}/restore/")
        self.assertEqual(restore_response.status_code, status.HTTP_200_OK)
        self.assertEqual(restore_response.data["template"]["status"], TransactionTemplateStatus.ACTIVE)

    def test_apply_template_creates_transaction_updates_balance_and_usage_stats(self):
        self.authenticate()
        tag = self.create_tag(name="обед")
        template = self.create_template(amount="450.00", tags=[tag])
        balance_before = self.account.balance

        response = self.client.post(
            f"{TEMPLATES_BASE_URL}{template.id}/apply/",
            data={
                "amountRub": 500,
                "operationDate": str(self.today),
                "note": "Обед по шаблону",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("template", response.data)
        self.assertIn("transaction", response.data)

        template.refresh_from_db()
        self.account.refresh_from_db()
        transaction = Transaction.objects.get(pk=response.data["transaction"]["id"])

        self.assertEqual(transaction.user, self.user)
        self.assertEqual(transaction.account, self.account)
        self.assertEqual(transaction.category, self.expense_category)
        self.assertEqual(transaction.type, TransactionType.EXPENSE)
        self.assertEqual(transaction.amount, Decimal("500.00"))
        self.assertEqual(transaction.description, "Обед по шаблону")
        self.assertEqual(list(transaction.tags.values_list("id", flat=True)), [tag.id])
        self.assertEqual(self.account.balance, balance_before - Decimal("500.00"))
        self.assertEqual(template.use_count, 1)
        self.assertIsNotNone(template.last_used_at)
        self.assertEqual(response.data["template"]["useCount"], 1)

    def test_apply_template_accepts_overrides_and_replaces_tags(self):
        self.authenticate()
        source_tag = self.create_tag(name="обед")
        new_tag = self.create_tag(name="такси")
        template = self.create_template(tags=[source_tag])
        taxi_category = self.transport_category

        response = self.client.post(
            f"{TEMPLATES_BASE_URL}{template.id}/apply/",
            data={
                "amountRub": 320,
                "accountId": self.cash_account.id,
                "categoryId": taxi_category.id,
                "tagIds": [new_tag.id],
                "description": "Такси домой",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        transaction = Transaction.objects.get(pk=response.data["transaction"]["id"])
        self.assertEqual(transaction.account, self.cash_account)
        self.assertEqual(transaction.category, taxi_category)
        self.assertEqual(transaction.description, "Такси домой")
        self.assertEqual(list(transaction.tags.values_list("id", flat=True)), [new_tag.id])

    def test_income_template_apply_increases_balance(self):
        self.authenticate()
        template = self.create_template(
            name="Зарплата",
            kind=TransactionType.INCOME,
            amount="85000.00",
            category=self.income_category,
        )
        balance_before = self.account.balance

        response = self.client.post(f"{TEMPLATES_BASE_URL}{template.id}/apply/", data={}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, balance_before + Decimal("85000.00"))

    def test_check_name_and_validate_endpoints(self):
        self.authenticate()
        template = self.create_template(name="Обед")

        duplicate_name_response = self.client.get(
            f"{TEMPLATES_BASE_URL}check-name/",
            data={"name": "обед"},
        )
        self.assertEqual(duplicate_name_response.status_code, status.HTTP_200_OK)
        self.assertFalse(duplicate_name_response.data["available"])

        available_name_response = self.client.get(
            f"{TEMPLATES_BASE_URL}check-name/",
            data={"name": "обед", "excludeId": template.id},
        )
        self.assertEqual(available_name_response.status_code, status.HTTP_200_OK)
        self.assertTrue(available_name_response.data["available"])

        validate_duplicate_response = self.client.post(
            f"{TEMPLATES_BASE_URL}validate/",
            data={
                "name": "обед",
                "kind": TransactionType.EXPENSE,
                "amountRub": 450,
                "accountId": self.account.id,
                "categoryId": self.expense_category.id,
            },
            format="json",
        )
        self.assertEqual(validate_duplicate_response.status_code, status.HTTP_200_OK)
        self.assertFalse(validate_duplicate_response.data["ok"])
        self.assertIn("name", validate_duplicate_response.data["fieldErrors"])

        validate_ok_response = self.client.post(
            f"{TEMPLATES_BASE_URL}validate/",
            data={
                "name": "Новый шаблон",
                "kind": TransactionType.EXPENSE,
                "amountRub": 450,
                "accountId": self.account.id,
                "categoryId": self.expense_category.id,
            },
            format="json",
        )
        self.assertEqual(validate_ok_response.status_code, status.HTTP_200_OK)
        self.assertTrue(validate_ok_response.data["ok"])
        self.assertEqual(validate_ok_response.data["fieldErrors"], {})

    def test_template_api_rejects_duplicates_foreign_objects_hidden_tags_and_kind_mismatch(self):
        self.authenticate()
        self.create_template(name="Кофе")
        hidden_tag = self.create_tag(name="скрытый", is_visible=False)
        other_tag = self.create_tag(user=self.other_user, name="чужой")

        duplicate_response = self.client.post(
            reverse("finance:transaction-template-list"),
            data={
                "name": "кофе",
                "kind": TransactionType.EXPENSE,
                "amountRub": 180,
                "accountId": self.account.id,
                "categoryId": self.expense_category.id,
            },
            format="json",
        )
        self.assertEqual(duplicate_response.status_code, status.HTTP_400_BAD_REQUEST)

        foreign_account_response = self.client.post(
            reverse("finance:transaction-template-list"),
            data={
                "name": "Чужой счёт",
                "kind": TransactionType.EXPENSE,
                "amountRub": 100,
                "accountId": self.other_account.id,
                "categoryId": self.expense_category.id,
            },
            format="json",
        )
        self.assertEqual(foreign_account_response.status_code, status.HTTP_400_BAD_REQUEST)

        foreign_category_response = self.client.post(
            reverse("finance:transaction-template-list"),
            data={
                "name": "Чужая категория",
                "kind": TransactionType.EXPENSE,
                "amountRub": 100,
                "accountId": self.account.id,
                "categoryId": self.other_category.id,
            },
            format="json",
        )
        self.assertEqual(foreign_category_response.status_code, status.HTTP_400_BAD_REQUEST)

        kind_mismatch_response = self.client.post(
            reverse("finance:transaction-template-list"),
            data={
                "name": "Несовпадение типа",
                "kind": TransactionType.EXPENSE,
                "amountRub": 100,
                "accountId": self.account.id,
                "categoryId": self.income_category.id,
            },
            format="json",
        )
        self.assertEqual(kind_mismatch_response.status_code, status.HTTP_400_BAD_REQUEST)

        hidden_tag_response = self.client.post(
            reverse("finance:transaction-template-list"),
            data={
                "name": "Скрытый тег",
                "kind": TransactionType.EXPENSE,
                "amountRub": 100,
                "accountId": self.account.id,
                "categoryId": self.expense_category.id,
                "tagIds": [hidden_tag.id],
            },
            format="json",
        )
        self.assertEqual(hidden_tag_response.status_code, status.HTTP_400_BAD_REQUEST)

        other_tag_response = self.client.post(
            reverse("finance:transaction-template-list"),
            data={
                "name": "Чужой тег",
                "kind": TransactionType.EXPENSE,
                "amountRub": 100,
                "accountId": self.account.id,
                "categoryId": self.expense_category.id,
                "tagIds": [other_tag.id],
            },
            format="json",
        )
        self.assertEqual(other_tag_response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_apply_rejects_archived_template_and_invalid_overrides(self):
        self.authenticate()
        template = self.create_template(status=TransactionTemplateStatus.ARCHIVED)

        archived_response = self.client.post(f"{TEMPLATES_BASE_URL}{template.id}/apply/", data={}, format="json")
        self.assertEqual(archived_response.status_code, status.HTTP_400_BAD_REQUEST)

        template.status = TransactionTemplateStatus.ACTIVE
        template.save(update_fields=["status"])

        foreign_account_response = self.client.post(
            f"{TEMPLATES_BASE_URL}{template.id}/apply/",
            data={"accountId": self.other_account.id},
            format="json",
        )
        self.assertEqual(foreign_account_response.status_code, status.HTTP_400_BAD_REQUEST)

        kind_mismatch_response = self.client.post(
            f"{TEMPLATES_BASE_URL}{template.id}/apply/",
            data={"categoryId": self.income_category.id},
            format="json",
        )
        self.assertEqual(kind_mismatch_response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_user_cannot_access_other_user_template(self):
        self.authenticate()
        other_template = self.create_template(
            user=self.other_user,
            account=self.other_account,
            category=self.other_category,
            name="Чужой шаблон",
        )

        detail_response = self.client.get(
            reverse("finance:transaction-template-detail", kwargs={"pk": other_template.id})
        )
        update_response = self.client.patch(
            reverse("finance:transaction-template-detail", kwargs={"pk": other_template.id}),
            data={"name": "Попытка изменить"},
            format="json",
        )
        delete_response = self.client.delete(
            reverse("finance:transaction-template-detail", kwargs={"pk": other_template.id})
        )

        self.assertEqual(detail_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(update_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(delete_response.status_code, status.HTTP_404_NOT_FOUND)

    def test_invalid_list_filters_return_400(self):
        self.authenticate()

        invalid_status_response = self.client.get(
            reverse("finance:transaction-template-list"),
            data={"status": "wrong"},
        )
        invalid_category_response = self.client.get(
            reverse("finance:transaction-template-list"),
            data={"categories": "abc"},
        )
        invalid_account_response = self.client.get(
            reverse("finance:transaction-template-list"),
            data={"accounts": self.other_account.id},
        )
        invalid_tag_response = self.client.get(
            reverse("finance:transaction-template-list"),
            data={"tagIds": "999999"},
        )
        invalid_sort_response = self.client.get(
            reverse("finance:transaction-template-list"),
            data={"sortBy": "wrong"},
        )

        self.assertEqual(invalid_status_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(invalid_category_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(invalid_account_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(invalid_tag_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(invalid_sort_response.status_code, status.HTTP_400_BAD_REQUEST)
