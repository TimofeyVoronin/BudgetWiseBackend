import csv
from decimal import Decimal
from io import StringIO

from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.finance.models import Tag, TagGroup, Transaction, TransactionType
from apps.finance.tests.base import FinanceAPITestCase


TAGS_BASE_URL = "/api/v1/finance/tags/"


class FinanceTagsAPITests(FinanceAPITestCase):
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

    def create_tagged_transaction(self, *, tag, description="Покупка продуктов", amount="250.00"):
        transaction = self.create_transaction(
            account=self.account,
            category=self.expense_category,
            type=TransactionType.EXPENSE,
            amount=amount,
            description=description,
            operation_date=self.today,
        )
        transaction.tags.add(tag)
        return transaction

    def get_tag_ids(self, response):
        return [item["id"] for item in response.data["items"]]

    def test_tag_list_requires_authentication(self):
        response = self.client.get(reverse("finance:tag-list"))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(response.data["success"])

    def test_tag_list_returns_summary_groups_and_only_current_user_tags(self):
        self.authenticate()
        group = self.create_tag_group(name="Покупки")
        own_tag = self.create_tag(group=group, name="Продукты")
        used_tag = self.create_tag(group=group, name="Такси", color="#FFA726", icon="taxi")
        self.create_tagged_transaction(tag=used_tag, description="Такси до офиса")
        other_group = self.create_tag_group(user=self.other_user, name="Чужая группа")
        other_tag = self.create_tag(
            user=self.other_user,
            group=other_group,
            name="Чужой тег",
        )

        response = self.client.get(reverse("finance:tag-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("items", response.data)
        self.assertIn("summary", response.data)
        self.assertIn("groups", response.data)
        self.assertEqual(response.data["summary"]["totalCount"], 2)
        self.assertEqual(response.data["summary"]["withOperationsCount"], 1)
        self.assertEqual(response.data["summary"]["withoutOperationsCount"], 1)
        tag_ids = self.get_tag_ids(response)
        self.assertIn(own_tag.id, tag_ids)
        self.assertIn(used_tag.id, tag_ids)
        self.assertNotIn(other_tag.id, tag_ids)
        self.assertTrue(
            any(group_payload["name"] == "Без группы" for group_payload in response.data["groups"])
        )
        self.assertTrue(
            any(group_payload["id"] == group.id for group_payload in response.data["groups"])
        )

    def test_create_retrieve_update_and_delete_unused_tag(self):
        self.authenticate()
        group = self.create_tag_group(name="Покупки")

        create_response = self.client.post(
            reverse("finance:tag-list"),
            data={
                "name": "  Продукты   и   супермаркеты  ",
                "groupId": group.id,
                "color": "#66bb6a",
                "icon": "cart",
                "isVisible": True,
                "description": "  Покупки продуктов  ",
            },
            format="json",
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(create_response.data["name"], "Продукты и супермаркеты")
        self.assertEqual(create_response.data["color"], "#66BB6A")
        self.assertEqual(create_response.data["groupId"], group.id)
        self.assertEqual(create_response.data["groupName"], group.name)
        self.assertEqual(create_response.data["operationsCount"], 0)
        self.assertFalse(create_response.data["isSystem"])

        tag_id = create_response.data["id"]
        detail_response = self.client.get(reverse("finance:tag-detail", kwargs={"pk": tag_id}))

        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.data["id"], tag_id)

        update_response = self.client.patch(
            reverse("finance:tag-detail", kwargs={"pk": tag_id}),
            data={
                "name": "Продукты",
                "color": "#42A5F5",
                "icon": "tag",
                "description": "Новая подпись",
            },
            format="json",
        )

        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.data["name"], "Продукты")
        self.assertEqual(update_response.data["color"], "#42A5F5")
        self.assertEqual(update_response.data["icon"], "tag")

        delete_response = self.client.delete(reverse("finance:tag-detail", kwargs={"pk": tag_id}))

        self.assertEqual(delete_response.status_code, status.HTTP_200_OK)
        self.assertTrue(delete_response.data["deleted"])
        self.assertEqual(delete_response.data["id"], tag_id)
        self.assertFalse(Tag.objects.filter(id=tag_id).exists())

    def test_tag_custom_actions_rename_move_group_and_visibility(self):
        self.authenticate()
        source_group = self.create_tag_group(name="Покупки")
        target_group = self.create_tag_group(name="Транспорт")
        tag = self.create_tag(group=source_group, name="Продукты")

        rename_response = self.client.patch(
            f"{TAGS_BASE_URL}{tag.id}/rename/",
            data={"name": "Продукты и супермаркеты"},
            format="json",
        )

        self.assertEqual(rename_response.status_code, status.HTTP_200_OK)
        self.assertEqual(rename_response.data["tag"]["name"], "Продукты и супермаркеты")
        self.assertEqual(rename_response.data["operationsCount"], 0)

        move_response = self.client.patch(
            f"{TAGS_BASE_URL}{tag.id}/group/",
            data={"groupId": target_group.id},
            format="json",
        )

        self.assertEqual(move_response.status_code, status.HTTP_200_OK)
        self.assertEqual(move_response.data["groupId"], target_group.id)
        self.assertEqual(move_response.data["groupName"], target_group.name)

        hide_response = self.client.patch(
            f"{TAGS_BASE_URL}{tag.id}/visibility/",
            data={"isVisible": False},
            format="json",
        )

        self.assertEqual(hide_response.status_code, status.HTTP_200_OK)
        self.assertFalse(hide_response.data["isVisible"])

        select_response = self.client.get(f"{TAGS_BASE_URL}select-options/")
        self.assertEqual(select_response.status_code, status.HTTP_200_OK)
        self.assertEqual(select_response.data["options"], [])

        show_response = self.client.patch(
            f"{TAGS_BASE_URL}{tag.id}/visibility/",
            data={"isVisible": True},
            format="json",
        )

        self.assertEqual(show_response.status_code, status.HTTP_200_OK)
        self.assertTrue(show_response.data["isVisible"])

        select_response = self.client.get(f"{TAGS_BASE_URL}select-options/")
        self.assertEqual(select_response.status_code, status.HTTP_200_OK)
        self.assertEqual(select_response.data["options"][0]["value"], tag.id)

    def test_tag_meta_groups_select_options_search_filters_and_sorting(self):
        self.authenticate()
        group = self.create_tag_group(name="Покупки")
        taxi_group = self.create_tag_group(name="Транспорт")
        products_tag = self.create_tag(
            group=group,
            name="Продукты",
            color="#66BB6A",
            icon="cart",
            description="Еда и супермаркеты",
        )
        taxi_tag = self.create_tag(
            group=taxi_group,
            name="Такси",
            color="#FFA726",
            icon="taxi",
            is_visible=False,
        )
        self.create_tagged_transaction(tag=products_tag)

        meta_response = self.client.get(f"{TAGS_BASE_URL}meta/")
        self.assertEqual(meta_response.status_code, status.HTTP_200_OK)
        self.assertIn("groups", meta_response.data)
        self.assertIn("colors", meta_response.data)
        self.assertIn("icons", meta_response.data)

        groups_response = self.client.get(f"{TAGS_BASE_URL}groups/")
        self.assertEqual(groups_response.status_code, status.HTTP_200_OK)
        self.assertTrue(any(item["id"] == group.id for item in groups_response.data["groups"]))

        search_response = self.client.get(reverse("finance:tag-list"), data={"search": "супермаркеты"})
        self.assertEqual(search_response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.get_tag_ids(search_response), [products_tag.id])

        group_filter_response = self.client.get(reverse("finance:tag-list"), data={"groupId": group.id})
        self.assertEqual(group_filter_response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.get_tag_ids(group_filter_response), [products_tag.id])

        only_with_operations_response = self.client.get(
            reverse("finance:tag-list"),
            data={"onlyWithOperations": "true"},
        )
        self.assertEqual(only_with_operations_response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.get_tag_ids(only_with_operations_response), [products_tag.id])

        hidden_excluded_response = self.client.get(reverse("finance:tag-list"))
        self.assertNotIn(taxi_tag.id, self.get_tag_ids(hidden_excluded_response))

        hidden_included_response = self.client.get(
            reverse("finance:tag-list"),
            data={"includeHidden": "true", "sortBy": "name", "sortOrder": "asc"},
        )
        self.assertEqual(hidden_included_response.status_code, status.HTTP_200_OK)
        self.assertIn(taxi_tag.id, self.get_tag_ids(hidden_included_response))

    def test_tag_validation_duplicate_invalid_fields_and_validate_endpoint(self):
        self.authenticate()
        group = self.create_tag_group(name="Покупки")
        self.create_tag(group=group, name="Такси", icon="taxi", color="#FFA726")

        duplicate_response = self.client.post(
            reverse("finance:tag-list"),
            data={
                "name": "  такси  ",
                "groupId": group.id,
                "color": "#FFA726",
                "icon": "taxi",
            },
            format="json",
        )

        self.assertEqual(duplicate_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(duplicate_response.data["success"])
        self.assertEqual(duplicate_response.data["error"]["code"], "duplicate_tag_name")
        self.assertIn("name", duplicate_response.data["error"]["field_errors"])

        invalid_name_response = self.client.post(
            reverse("finance:tag-list"),
            data={
                "name": "Тег<script>",
                "groupId": group.id,
                "color": "#66BB6A",
                "icon": "cart",
            },
            format="json",
        )

        self.assertEqual(invalid_name_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(invalid_name_response.data["error"]["code"], "tag_name_invalid_chars")

        invalid_color_response = self.client.post(
            reverse("finance:tag-list"),
            data={
                "name": "Некорректный цвет",
                "groupId": group.id,
                "color": "green",
                "icon": "cart",
            },
            format="json",
        )

        self.assertEqual(invalid_color_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("color", invalid_color_response.data["error"]["field_errors"])

        invalid_icon_response = self.client.post(
            reverse("finance:tag-list"),
            data={
                "name": "Некорректная иконка",
                "groupId": group.id,
                "color": "#66BB6A",
                "icon": "unknown-icon",
            },
            format="json",
        )

        self.assertEqual(invalid_icon_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(invalid_icon_response.data["error"]["code"], "tag_icon_invalid")

        validate_response = self.client.post(
            f"{TAGS_BASE_URL}validate/",
            data={
                "name": "Такси",
                "groupId": group.id,
                "color": "#66BB6A",
                "icon": "taxi",
            },
            format="json",
        )

        self.assertEqual(validate_response.status_code, status.HTTP_200_OK)
        self.assertFalse(validate_response.data["ok"])
        self.assertIn("name", validate_response.data["fieldErrors"])

    def test_user_cannot_access_foreign_tags_or_groups(self):
        self.authenticate()
        own_group = self.create_tag_group(name="Моя группа")
        other_group = self.create_tag_group(user=self.other_user, name="Чужая группа")
        other_tag = self.create_tag(
            user=self.other_user,
            group=other_group,
            name="Чужой тег",
        )

        detail_response = self.client.get(reverse("finance:tag-detail", kwargs={"pk": other_tag.id}))
        self.assertEqual(detail_response.status_code, status.HTTP_404_NOT_FOUND)

        create_with_foreign_group_response = self.client.post(
            reverse("finance:tag-list"),
            data={
                "name": "Попытка чужой группы",
                "groupId": other_group.id,
                "color": "#66BB6A",
                "icon": "cart",
            },
            format="json",
        )
        self.assertEqual(create_with_foreign_group_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("groupId", create_with_foreign_group_response.data["error"]["field_errors"])

        own_tag = self.create_tag(group=own_group, name="Мой тег")
        other_user_list_response = self.client.get(reverse("finance:tag-list"))
        self.assertIn(own_tag.id, self.get_tag_ids(other_user_list_response))
        self.assertNotIn(other_tag.id, self.get_tag_ids(other_user_list_response))

    def test_transaction_create_update_list_search_and_filter_by_tags(self):
        self.authenticate()
        group = self.create_tag_group(name="Покупки")
        products_tag = self.create_tag(group=group, name="Супермаркеты", icon="cart")
        taxi_tag = self.create_tag(group=group, name="Такси", icon="taxi", color="#FFA726")

        create_response = self.client.post(
            reverse("finance:transaction-list"),
            data={
                "account": self.account.id,
                "category": self.expense_category.id,
                "type": TransactionType.EXPENSE,
                "amount": "1250.00",
                "description": "Покупка продуктов",
                "operation_date": str(self.today),
                "tagIds": [products_tag.id],
            },
            format="json",
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        transaction_id = create_response.data["id"]
        self.assertEqual([tag["id"] for tag in create_response.data["tags"]], [products_tag.id])

        transaction = Transaction.objects.get(id=transaction_id)
        self.assertEqual(list(transaction.tags.values_list("id", flat=True)), [products_tag.id])

        update_response = self.client.patch(
            reverse("finance:transaction-detail", kwargs={"pk": transaction_id}),
            data={"tagIds": [taxi_tag.id]},
            format="json",
        )

        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual([tag["id"] for tag in update_response.data["tags"]], [taxi_tag.id])

        list_by_tags_response = self.client.get(
            reverse("finance:transaction-list"),
            data={"tags": str(taxi_tag.id)},
        )
        self.assertEqual(list_by_tags_response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.get_transaction_ids(list_by_tags_response), [transaction_id])

        list_by_tag_ids_response = self.client.get(
            reverse("finance:transaction-list"),
            data={"tagIds": str(products_tag.id)},
        )
        self.assertEqual(list_by_tag_ids_response.status_code, status.HTTP_200_OK)
        self.assertEqual(list_by_tag_ids_response.data["count"], 0)

        search_response = self.client.get(
            reverse("finance:transaction-list"),
            data={"search": "такси"},
        )
        self.assertEqual(search_response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.get_transaction_ids(search_response), [transaction_id])

        clear_response = self.client.patch(
            reverse("finance:transaction-detail", kwargs={"pk": transaction_id}),
            data={"tagIds": []},
            format="json",
        )

        self.assertEqual(clear_response.status_code, status.HTTP_200_OK)
        self.assertEqual(clear_response.data["tags"], [])
        transaction.refresh_from_db()
        self.assertEqual(transaction.tags.count(), 0)

    def test_transaction_rejects_hidden_foreign_and_invalid_tags(self):
        self.authenticate()
        group = self.create_tag_group(name="Покупки")
        hidden_tag = self.create_tag(group=group, name="Скрытый", is_visible=False)
        other_group = self.create_tag_group(user=self.other_user, name="Чужая группа")
        other_tag = self.create_tag(
            user=self.other_user,
            group=other_group,
            name="Чужой тег",
        )

        for tag_id in [hidden_tag.id, other_tag.id, 999999]:
            response = self.client.post(
                reverse("finance:transaction-list"),
                data={
                    "account": self.account.id,
                    "category": self.expense_category.id,
                    "type": TransactionType.EXPENSE,
                    "amount": "100.00",
                    "description": "Операция с недоступным тегом",
                    "operation_date": str(self.today),
                    "tagIds": [tag_id],
                },
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("tagIds", response.data["error"]["field_errors"])

    def test_rename_keeps_transaction_history_and_delete_used_tag_returns_conflict(self):
        self.authenticate()
        group = self.create_tag_group(name="Покупки")
        tag = self.create_tag(group=group, name="Продукты", icon="cart")
        transaction = self.create_tagged_transaction(tag=tag)

        rename_response = self.client.patch(
            f"{TAGS_BASE_URL}{tag.id}/rename/",
            data={"name": "Продукты и супермаркеты"},
            format="json",
        )

        self.assertEqual(rename_response.status_code, status.HTTP_200_OK)
        self.assertEqual(rename_response.data["operationsCount"], 1)

        detail_response = self.client.get(
            reverse("finance:transaction-detail", kwargs={"pk": transaction.id})
        )
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.data["tags"][0]["id"], tag.id)
        self.assertEqual(detail_response.data["tags"][0]["name"], "Продукты и супермаркеты")

        delete_response = self.client.delete(reverse("finance:tag-detail", kwargs={"pk": tag.id}))

        self.assertEqual(delete_response.status_code, status.HTTP_409_CONFLICT)
        self.assertFalse(delete_response.data["success"])
        self.assertEqual(delete_response.data["error"]["code"], "tag_has_operations")
        self.assertEqual(delete_response.data["error"]["detail"]["code"], "HAS_OPERATIONS")
        self.assertEqual(delete_response.data["error"]["detail"]["operationsCount"], 1)
        self.assertTrue(delete_response.data["error"]["detail"]["canHide"])
        self.assertTrue(Tag.objects.filter(id=tag.id).exists())

    def test_dashboard_and_export_use_tag_filter(self):
        self.authenticate()
        group = self.create_tag_group(name="Покупки")
        tag = self.create_tag(group=group, name="Супермаркеты", icon="cart")
        tagged_transaction = self.create_tagged_transaction(
            tag=tag,
            description="Покупка с тегом",
            amount="300.00",
        )
        self.create_transaction(
            account=self.account,
            category=self.transport_category,
            type=TransactionType.EXPENSE,
            amount="700.00",
            description="Операция без нужного тега",
            operation_date=self.today,
        )

        dashboard_response = self.client.get(
            reverse("finance:dashboard-summary"),
            data={
                "period": "custom",
                "date_from": str(self.today - timezone.timedelta(days=1)),
                "date_to": str(self.today),
                "tagIds": str(tag.id),
                "limit": 10,
            },
        )

        self.assertEqual(dashboard_response.status_code, status.HTTP_200_OK)
        self.assertEqual(dashboard_response.data["totals"]["expense"], "300.00")
        self.assertEqual(
            [item["id"] for item in dashboard_response.data["recent_transactions"]],
            [tagged_transaction.id],
        )

        export_response = self.client.get(
            reverse("finance:transaction-export"),
            data={
                "format": "csv",
                "tags": str(tag.id),
            },
        )

        self.assertEqual(export_response.status_code, status.HTTP_200_OK)
        decoded_content = export_response.content.decode("utf-8-sig")
        csv_reader = csv.DictReader(StringIO(decoded_content))
        rows = list(csv_reader)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Описание"], "Покупка с тегом")
        self.assertEqual(rows[0]["Теги"], tag.name)
        self.assertNotIn("Операция без нужного тега", decoded_content)
