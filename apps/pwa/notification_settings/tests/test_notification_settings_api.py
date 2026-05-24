from rest_framework import status

from apps.pwa.models import PwaNotificationSettings
from apps.pwa.tests.base import PwaAPITestCase


class PwaNotificationSettingsAPITests(PwaAPITestCase):
    def setUp(self):
        super().setUp()
        self.authenticate()

    def test_get_notification_settings_creates_defaults(self):
        response = self.client.get("/api/v1/pwa/notification-settings/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["pushEnabled"])
        self.assertTrue(response.data["syncConflict"])
        self.assertTrue(response.data["syncFailed"])
        self.assertEqual(response.data["quietHoursFrom"], "22:00")
        self.assertEqual(response.data["quietHoursTo"], "08:00")
        self.assertEqual(PwaNotificationSettings.objects.filter(user=self.user).count(), 1)

    def test_update_notification_settings(self):
        payload = {
            "pushEnabled": False,
            "syncConflict": True,
            "syncFailed": False,
            "budgetLimitWarning": False,
            "plannedTransactionDue": True,
            "receiptImported": False,
            "quietHoursEnabled": True,
            "quietHoursFrom": "21:30",
            "quietHoursTo": "07:15",
        }

        response = self.client.put(
            "/api/v1/pwa/notification-settings/",
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["pushEnabled"])
        self.assertFalse(response.data["syncFailed"])
        self.assertTrue(response.data["quietHoursEnabled"])
        self.assertEqual(response.data["quietHoursFrom"], "21:30")
        self.assertEqual(response.data["quietHoursTo"], "07:15")

    def test_update_notification_settings_validates_quiet_hours(self):
        payload = {
            "pushEnabled": True,
            "syncConflict": True,
            "syncFailed": True,
            "budgetLimitWarning": True,
            "plannedTransactionDue": True,
            "receiptImported": True,
            "quietHoursEnabled": True,
            "quietHoursFrom": "22:00",
            "quietHoursTo": "22:00",
        }

        response = self.client.put(
            "/api/v1/pwa/notification-settings/",
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("quietHoursTo", response.data["error"]["field_errors"])
