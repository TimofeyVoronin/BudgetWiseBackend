from datetime import timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.finance.models import (
    NotificationChannel,
    NotificationDeliveryStatus,
    NotificationSettings,
    NotificationType,
)
from apps.finance.notifications.services import create_notification
from apps.finance.testing import FinanceAPITestCase


class FinanceNotificationSettingsAPITests(FinanceAPITestCase):
    def settings_url(self):
        return f"{reverse('finance:notification-list')}settings/"

    def test_get_settings_requires_authentication(self):
        response = self.client.get(self.settings_url())

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_settings_creates_default_settings_for_current_user(self):
        self.authenticate()

        response = self.client.get(self.settings_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["inAppEnabled"])
        self.assertTrue(response.data["emailEnabled"])
        self.assertTrue(response.data["pushEnabled"])
        self.assertTrue(response.data["smsEnabled"])
        self.assertTrue(response.data["operationEnabled"])
        self.assertTrue(response.data["goalEnabled"])
        self.assertTrue(response.data["budgetEnabled"])
        self.assertTrue(response.data["systemEnabled"])
        self.assertTrue(response.data["securityEnabled"])
        self.assertFalse(response.data["marketingEnabled"])
        self.assertFalse(response.data["quietHoursEnabled"])
        self.assertEqual(
            response.data["quietHoursDays"],
            [
                "mon",
                "tue",
                "wed",
                "thu",
                "fri",
            ],
        )
        self.assertEqual(
            NotificationSettings.objects.filter(user=self.user).count(),
            1,
        )

    def test_patch_settings_accepts_camel_case_fields(self):
        self.authenticate()

        response = self.client.patch(
            self.settings_url(),
            data={
                "emailEnabled": False,
                "pushEnabled": False,
                "smsEnabled": False,
                "inAppEnabled": True,
                "operationEnabled": True,
                "goalEnabled": False,
                "budgetEnabled": True,
                "systemEnabled": True,
                "securityEnabled": True,
                "marketingEnabled": True,
                "quietHoursEnabled": True,
                "quietHoursStart": "22:00",
                "quietHoursEnd": "08:00",
                "quietHoursDays": [
                    "MON",
                    "mon",
                    "Tue",
                    "fri",
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["emailEnabled"])
        self.assertFalse(response.data["pushEnabled"])
        self.assertFalse(response.data["smsEnabled"])
        self.assertFalse(response.data["goalEnabled"])
        self.assertTrue(response.data["marketingEnabled"])
        self.assertTrue(response.data["quietHoursEnabled"])
        self.assertEqual(response.data["quietHoursStart"], "22:00")
        self.assertEqual(response.data["quietHoursEnd"], "08:00")
        self.assertEqual(
            response.data["quietHoursDays"],
            [
                "mon",
                "tue",
                "fri",
            ],
        )

        settings = NotificationSettings.objects.get(user=self.user)
        self.assertFalse(settings.email_enabled)
        self.assertFalse(settings.push_enabled)
        self.assertFalse(settings.sms_enabled)
        self.assertFalse(settings.goal_enabled)
        self.assertTrue(settings.marketing_enabled)
        self.assertEqual(
            settings.quiet_hours_days,
            [
                "mon",
                "tue",
                "fri",
            ],
        )

    def test_patch_settings_accepts_snake_case_fields(self):
        self.authenticate()

        response = self.client.patch(
            self.settings_url(),
            data={
                "email_enabled": False,
                "push_enabled": True,
                "sms_enabled": False,
                "in_app_enabled": True,
                "quiet_hours_enabled": True,
                "quiet_hours_start": "21:30",
                "quiet_hours_end": "07:15",
                "quiet_hours_days": [
                    "sat",
                    "sun",
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["emailEnabled"])
        self.assertTrue(response.data["pushEnabled"])
        self.assertFalse(response.data["smsEnabled"])
        self.assertTrue(response.data["quietHoursEnabled"])
        self.assertEqual(response.data["quietHoursStart"], "21:30")
        self.assertEqual(response.data["quietHoursEnd"], "07:15")
        self.assertEqual(
            response.data["quietHoursDays"],
            [
                "sat",
                "sun",
            ],
        )

    def test_settings_are_isolated_between_users(self):
        self.authenticate()

        self.client.patch(
            self.settings_url(),
            data={
                "smsEnabled": False,
                "marketingEnabled": True,
            },
            format="json",
        )

        self.client.force_authenticate(user=self.other_user)
        response = self.client.get(self.settings_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["smsEnabled"])
        self.assertFalse(response.data["marketingEnabled"])

    def test_create_notification_marks_disabled_channel_as_unavailable(self):
        NotificationSettings.objects.create(
            user=self.user,
            sms_enabled=False,
        )

        notification = create_notification(
            user=self.user,
            title="SMS недоступно",
            type=NotificationType.SYSTEM,
            channel=NotificationChannel.SMS,
        )

        self.assertEqual(notification.delivery_status, NotificationDeliveryStatus.UNAVAILABLE)
        self.assertIn("Канал уведомлений отключён", notification.delivery_error)

    def test_create_notification_marks_disabled_type_as_unavailable(self):
        NotificationSettings.objects.create(
            user=self.user,
            marketing_enabled=False,
        )

        notification = create_notification(
            user=self.user,
            title="Маркетинговое уведомление",
            type=NotificationType.MARKETING,
            channel=NotificationChannel.IN_APP,
        )

        self.assertEqual(notification.delivery_status, NotificationDeliveryStatus.UNAVAILABLE)
        self.assertIn("Тип уведомлений отключён", notification.delivery_error)

    def test_create_notification_marks_quiet_hours_delivery_as_pending(self):
        now = timezone.localtime()
        start = (now - timedelta(minutes=1)).time().replace(microsecond=0)
        end = (now + timedelta(minutes=1)).time().replace(microsecond=0)

        NotificationSettings.objects.create(
            user=self.user,
            quiet_hours_enabled=True,
            quiet_hours_start=start,
            quiet_hours_end=end,
            quiet_hours_days=[
                now.strftime("%a").lower()[:3],
            ],
        )

        notification = create_notification(
            user=self.user,
            title="Тихие часы",
            type=NotificationType.SYSTEM,
            channel=NotificationChannel.IN_APP,
            amount=Decimal("100.00"),
        )

        self.assertEqual(notification.delivery_status, NotificationDeliveryStatus.PENDING)
        self.assertIn("тихих часов", notification.delivery_error)
