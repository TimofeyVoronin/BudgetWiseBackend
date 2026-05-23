from decimal import Decimal

from django.contrib.auth.models import AnonymousUser
from django.urls import reverse
from rest_framework import status
from rest_framework.exceptions import ValidationError

from apps.finance.models import (
    Notification,
    NotificationChannel,
    NotificationDeliveryStatus,
    NotificationEntityKind,
    NotificationIconTone,
    NotificationType,
)
from apps.finance.notifications.services import create_notification
from apps.finance.testing import FinanceAPITestCase


class FinanceNotificationValidationAPITests(FinanceAPITestCase):
    def setUp(self):
        super().setUp()

        self.notification = Notification.objects.create(
            user=self.user,
            title="Тестовое уведомление",
            body="Текст уведомления",
            type=NotificationType.SYSTEM,
            channel=NotificationChannel.IN_APP,
            delivery_status=NotificationDeliveryStatus.DELIVERED,
        )
        self.other_notification = Notification.objects.create(
            user=self.other_user,
            title="Чужое уведомление",
            body="Текст уведомления",
            type=NotificationType.SYSTEM,
            channel=NotificationChannel.IN_APP,
        )

    def list_url(self):
        return reverse("finance:notification-list")

    def settings_url(self):
        return f"{self.list_url()}settings/"

    def archive_selected_url(self):
        return f"{self.list_url()}archive-selected/"

    def test_list_rejects_invalid_status(self):
        self.authenticate()

        response = self.client.get(
            self.list_url(),
            data={
                "status": "wrong",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_rejects_invalid_type_channel_entity_and_delivery_status(self):
        self.authenticate()

        invalid_queries = [
            {
                "types": "wrong",
            },
            {
                "channels": "wrong",
            },
            {
                "entity": "wrong",
            },
            {
                "deliveryStatus": "wrong",
            },
        ]

        for query in invalid_queries:
            with self.subTest(query=query):
                response = self.client.get(
                    self.list_url(),
                    data=query,
                )

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_rejects_invalid_dates(self):
        self.authenticate()

        invalid_date_response = self.client.get(
            self.list_url(),
            data={
                "dateFrom": "wrong-date",
            },
        )
        wrong_period_response = self.client.get(
            self.list_url(),
            data={
                "dateFrom": "2026-05-20",
                "dateTo": "2026-05-19",
            },
        )

        self.assertEqual(invalid_date_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(wrong_period_response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_rejects_too_long_search(self):
        self.authenticate()

        response = self.client.get(
            self.list_url(),
            data={
                "search": "a" * 101,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_archive_selected_rejects_empty_ids(self):
        self.authenticate()

        response = self.client.post(
            self.archive_selected_url(),
            data={
                "ids": [],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_archive_selected_rejects_missing_or_foreign_ids(self):
        self.authenticate()

        missing_response = self.client.post(
            self.archive_selected_url(),
            data={
                "ids": [
                    999999,
                ],
            },
            format="json",
        )
        foreign_response = self.client.post(
            self.archive_selected_url(),
            data={
                "ids": [
                    self.other_notification.id,
                ],
            },
            format="json",
        )

        self.assertEqual(missing_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(foreign_response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_settings_rejects_invalid_quiet_hours_days(self):
        self.authenticate()

        response = self.client.patch(
            self.settings_url(),
            data={
                "quietHoursEnabled": True,
                "quietHoursStart": "22:00",
                "quietHoursEnd": "08:00",
                "quietHoursDays": [
                    "mon",
                    "wrong",
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_settings_rejects_empty_quiet_hours_days_when_enabled(self):
        self.authenticate()

        response = self.client.patch(
            self.settings_url(),
            data={
                "quietHoursEnabled": True,
                "quietHoursStart": "22:00",
                "quietHoursEnd": "08:00",
                "quietHoursDays": [],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_notification_rejects_unauthenticated_user(self):
        with self.assertRaises(ValidationError):
            create_notification(
                user=AnonymousUser(),
                title="Без пользователя",
            )

    def test_create_notification_rejects_invalid_required_data(self):
        invalid_payloads = [
            {
                "title": "",
            },
            {
                "title": "Неверный канал",
                "channel": "wrong",
            },
            {
                "title": "Неверный тип",
                "type": "wrong",
            },
            {
                "title": "Неверный тон",
                "icon_tone": "wrong",
            },
            {
                "title": "Неверная сущность",
                "entity_kind": "wrong",
            },
            {
                "title": "Неверный ID сущности",
                "entity_kind": NotificationEntityKind.GOAL,
                "entity_id": 0,
            },
            {
                "title": "Отрицательная сумма",
                "amount": Decimal("-1.00"),
            },
            {
                "title": "Некорректный процент цели",
                "related_goal_percent": Decimal("101.00"),
            },
            {
                "title": "Некорректные шаги доставки",
                "delivery_steps": "wrong",
            },
            {
                "title": "Шаг доставки без даты",
                "delivery_steps": [
                    {
                        "label": "Создано",
                    },
                ],
            },
        ]

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                data = {
                    "user": self.user,
                    "type": NotificationType.SYSTEM,
                    "channel": NotificationChannel.IN_APP,
                    "icon_tone": NotificationIconTone.PRIMARY,
                }
                data.update(payload)

                with self.assertRaises(ValidationError):
                    create_notification(**data)

    def test_create_notification_normalizes_valid_data(self):
        notification = create_notification(
            user=self.user,
            title="  Валидное уведомление  ",
            body="  Текст уведомления  ",
            type=NotificationType.OPERATION,
            channel=NotificationChannel.IN_APP,
            icon="bell",
            icon_tone=NotificationIconTone.SUCCESS,
            entity_kind=NotificationEntityKind.TRANSACTION,
            entity_id=10,
            entity_route_name=" transactions.detail ",
            entity_label=" Операция ",
            entity_tag=" Счёт: Текущий ",
            amount=Decimal("100.00"),
            account_name=" Текущий ",
            category_name=" Продукты ",
            related_goal_name=" Цель ",
            related_goal_percent=Decimal("50.00"),
            delivery_steps=[
                {
                    "label": " Создано ",
                    "at": "2026-05-20T10:00:00+03:00",
                }
            ],
        )

        self.assertEqual(notification.title, "Валидное уведомление")
        self.assertEqual(notification.body, "Текст уведомления")
        self.assertEqual(notification.entity_route_name, "transactions.detail")
        self.assertEqual(notification.entity_label, "Операция")
        self.assertEqual(notification.entity_tag, "Счёт: Текущий")
        self.assertEqual(notification.account_name, "Текущий")
        self.assertEqual(notification.category_name, "Продукты")
        self.assertEqual(notification.related_goal_name, "Цель")
        self.assertEqual(notification.delivery_steps[0]["label"], "Создано")
        self.assertEqual(notification.delivery_status, NotificationDeliveryStatus.DELIVERED)
