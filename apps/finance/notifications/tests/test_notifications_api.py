from datetime import timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.finance.models import (
    Notification,
    NotificationChannel,
    NotificationDeliveryStatus,
    NotificationEntityKind,
    NotificationType,
)
from apps.finance.testing import FinanceAPITestCase


class FinanceNotificationsAPITests(FinanceAPITestCase):
    def setUp(self):
        super().setUp()

        self.unread_operation = self.create_notification(
            title="Операция: списание 1 245 ₽",
            body="Покупка в супермаркете",
            type=NotificationType.OPERATION,
            channel=NotificationChannel.IN_APP,
            delivery_status=NotificationDeliveryStatus.DELIVERED,
            entity_kind=NotificationEntityKind.TRANSACTION,
            entity_id=301,
            entity_route_name="transactions.detail",
            entity_label="Операция",
            entity_tag="Счёт: Текущий",
            amount=Decimal("1245.00"),
            account_name="Текущий",
            category_name="Продукты",
        )
        self.read_goal = self.create_notification(
            title="Цель «Отпуск»: 62%",
            body="Вы на пути к своей цели.",
            type=NotificationType.GOAL,
            channel=NotificationChannel.EMAIL,
            delivery_status=NotificationDeliveryStatus.PENDING,
            entity_kind=NotificationEntityKind.GOAL,
            entity_id=11,
            entity_route_name="goals.detail",
            entity_label="Отпуск в Турции",
            entity_tag="Цель: Отпуск в Турции",
            related_goal_name="Отпуск в Турции",
            related_goal_percent=Decimal("62.00"),
            is_read=True,
        )
        self.failed_budget = self.create_notification(
            title="Бюджет превышен",
            body="Вы превысили бюджет по категории Продукты.",
            type=NotificationType.BUDGET,
            channel=NotificationChannel.PUSH,
            delivery_status=NotificationDeliveryStatus.FAILED,
            delivery_error="Push-канал недоступен.",
            entity_kind=NotificationEntityKind.BUDGET,
            entity_id=22,
            entity_route_name="budgets.detail",
            entity_label="Продукты",
            entity_tag="Бюджет: Продукты",
        )
        self.archived_system = self.create_notification(
            title="Старое системное уведомление",
            body="Архивное уведомление.",
            type=NotificationType.SYSTEM,
            channel=NotificationChannel.IN_APP,
            is_archived=True,
        )
        self.other_notification = self.create_notification(
            user=self.other_user,
            title="Чужое уведомление",
            body="Не должно попасть в список текущего пользователя.",
            type=NotificationType.SECURITY,
            channel=NotificationChannel.SMS,
        )

        old_created_at = timezone.now() - timedelta(days=10)
        Notification.objects.filter(pk=self.failed_budget.pk).update(
            created_at=old_created_at,
        )
        self.failed_budget.refresh_from_db()

    def create_notification(self, **kwargs):
        defaults = {
            "user": self.user,
            "title": "Тестовое уведомление",
            "body": "Текст уведомления",
            "type": NotificationType.SYSTEM,
            "channel": NotificationChannel.IN_APP,
            "delivery_status": NotificationDeliveryStatus.DELIVERED,
            "icon": "bell",
            "icon_tone": "primary",
        }
        defaults.update(kwargs)
        return Notification.objects.create(**defaults)

    def list_url(self):
        return reverse("finance:notification-list")

    def detail_url(self, notification):
        return reverse(
            "finance:notification-detail",
            kwargs={
                "pk": notification.pk,
            },
        )

    def action_url(self, notification, action):
        return f"{self.detail_url(notification)}{action}/"

    def collection_action_url(self, action):
        return f"{self.list_url()}{action}/"

    def result_ids(self, response):
        return [
            item["id"]
            for item in response.data["results"]
        ]

    def test_notification_list_requires_authentication(self):
        response = self.client.get(self.list_url())

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_notification_list_returns_current_user_non_archived_notifications_by_default(self):
        self.authenticate()

        response = self.client.get(self.list_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        notification_ids = self.result_ids(response)

        self.assertIn(self.unread_operation.id, notification_ids)
        self.assertIn(self.read_goal.id, notification_ids)
        self.assertIn(self.failed_budget.id, notification_ids)
        self.assertNotIn(self.archived_system.id, notification_ids)
        self.assertNotIn(self.other_notification.id, notification_ids)

    def test_notification_detail_returns_frontend_fields(self):
        self.authenticate()

        response = self.client.get(self.detail_url(self.unread_operation))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.unread_operation.id)
        self.assertEqual(response.data["status"], "unread")
        self.assertEqual(response.data["isRead"], False)
        self.assertEqual(response.data["type"], NotificationType.OPERATION)
        self.assertEqual(response.data["channel"], NotificationChannel.IN_APP)
        self.assertEqual(response.data["deliveryStatus"], NotificationDeliveryStatus.DELIVERED)
        self.assertEqual(response.data["amountRub"], "1245.00")
        self.assertEqual(response.data["accountName"], "Текущий")
        self.assertEqual(response.data["categoryName"], "Продукты")
        self.assertEqual(response.data["entityLink"]["kind"], NotificationEntityKind.TRANSACTION)

    def test_notification_detail_does_not_return_other_user_notification(self):
        self.authenticate()

        response = self.client.get(self.detail_url(self.other_notification))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_notification_list_filters_by_status(self):
        self.authenticate()

        unread_response = self.client.get(
            self.list_url(),
            data={
                "status": "unread",
            },
        )
        read_response = self.client.get(
            self.list_url(),
            data={
                "status": "read",
            },
        )
        archived_response = self.client.get(
            self.list_url(),
            data={
                "status": "archived",
            },
        )

        self.assertEqual(unread_response.status_code, status.HTTP_200_OK)
        self.assertEqual(read_response.status_code, status.HTTP_200_OK)
        self.assertEqual(archived_response.status_code, status.HTTP_200_OK)

        self.assertIn(self.unread_operation.id, self.result_ids(unread_response))
        self.assertNotIn(self.read_goal.id, self.result_ids(unread_response))

        self.assertIn(self.read_goal.id, self.result_ids(read_response))
        self.assertNotIn(self.unread_operation.id, self.result_ids(read_response))

        self.assertIn(self.archived_system.id, self.result_ids(archived_response))
        self.assertNotIn(self.unread_operation.id, self.result_ids(archived_response))

    def test_notification_list_filters_by_type_channel_entity_and_delivery_status(self):
        self.authenticate()

        response = self.client.get(
            self.list_url(),
            data={
                "types": "goal,budget",
                "channels": "email,push",
                "entity": "goal",
                "deliveryStatus": "pending",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        notification_ids = self.result_ids(response)

        self.assertEqual(notification_ids, [self.read_goal.id])

    def test_notification_list_filters_by_search_and_period(self):
        self.authenticate()

        response = self.client.get(
            self.list_url(),
            data={
                "search": "Отпуск",
                "dateFrom": timezone.localdate().isoformat(),
                "dateTo": timezone.localdate().isoformat(),
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        notification_ids = self.result_ids(response)

        self.assertIn(self.read_goal.id, notification_ids)
        self.assertNotIn(self.failed_budget.id, notification_ids)

    def test_read_and_unread_actions_are_idempotent(self):
        self.authenticate()

        read_response = self.client.patch(
            self.action_url(self.unread_operation, "read"),
            format="json",
        )
        second_read_response = self.client.patch(
            self.action_url(self.unread_operation, "read"),
            format="json",
        )

        self.assertEqual(read_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_read_response.status_code, status.HTTP_200_OK)

        self.unread_operation.refresh_from_db()
        self.assertTrue(self.unread_operation.is_read)
        self.assertIsNotNone(self.unread_operation.read_at)

        unread_response = self.client.patch(
            self.action_url(self.unread_operation, "unread"),
            format="json",
        )
        second_unread_response = self.client.patch(
            self.action_url(self.unread_operation, "unread"),
            format="json",
        )

        self.assertEqual(unread_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_unread_response.status_code, status.HTTP_200_OK)

        self.unread_operation.refresh_from_db()
        self.assertFalse(self.unread_operation.is_read)
        self.assertIsNone(self.unread_operation.read_at)

    def test_archive_and_restore_actions_are_idempotent(self):
        self.authenticate()

        archive_response = self.client.patch(
            self.action_url(self.unread_operation, "archive"),
            format="json",
        )
        second_archive_response = self.client.patch(
            self.action_url(self.unread_operation, "archive"),
            format="json",
        )

        self.assertEqual(archive_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_archive_response.status_code, status.HTTP_200_OK)

        self.unread_operation.refresh_from_db()
        self.assertTrue(self.unread_operation.is_archived)
        self.assertIsNotNone(self.unread_operation.archived_at)

        restore_response = self.client.patch(
            self.action_url(self.unread_operation, "restore"),
            format="json",
        )
        second_restore_response = self.client.patch(
            self.action_url(self.unread_operation, "restore"),
            format="json",
        )

        self.assertEqual(restore_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_restore_response.status_code, status.HTTP_200_OK)

        self.unread_operation.refresh_from_db()
        self.assertFalse(self.unread_operation.is_archived)
        self.assertIsNone(self.unread_operation.archived_at)

    def test_mark_all_read_updates_only_current_user_non_archived_notifications(self):
        self.authenticate()

        response = self.client.post(
            self.collection_action_url("mark-all-read"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["updatedCount"], 2)

        self.unread_operation.refresh_from_db()
        self.failed_budget.refresh_from_db()
        self.archived_system.refresh_from_db()
        self.other_notification.refresh_from_db()

        self.assertTrue(self.unread_operation.is_read)
        self.assertTrue(self.failed_budget.is_read)
        self.assertFalse(self.archived_system.is_read)
        self.assertFalse(self.other_notification.is_read)

    def test_archive_selected_updates_requested_user_notifications(self):
        self.authenticate()

        response = self.client.post(
            self.collection_action_url("archive-selected"),
            data={
                "ids": [
                    self.unread_operation.id,
                    self.read_goal.id,
                    self.read_goal.id,
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["updatedCount"], 2)

        self.unread_operation.refresh_from_db()
        self.read_goal.refresh_from_db()

        self.assertTrue(self.unread_operation.is_archived)
        self.assertTrue(self.read_goal.is_archived)

    def test_summary_returns_notification_counts(self):
        self.authenticate()

        response = self.client.get(self.collection_action_url("summary"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["unreadCount"], 2)
        self.assertEqual(response.data["deliveryErrorsCount"], 1)
        self.assertEqual(response.data["archivedCount"], 1)
        self.assertEqual(response.data["totalCount"], 4)

    def test_meta_returns_filter_options(self):
        self.authenticate()

        response = self.client.get(self.collection_action_url("meta"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("channels", response.data)
        self.assertIn("types", response.data)
        self.assertIn("statuses", response.data)
        self.assertIn("deliveryStatuses", response.data)
        self.assertIn("entityKinds", response.data)
        self.assertIn("iconTones", response.data)
