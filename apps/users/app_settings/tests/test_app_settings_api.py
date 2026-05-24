from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.finance.currencies.services import ensure_user_currencies, get_user_currency_by_code
from apps.users.models import UserAppSettings


User = get_user_model()


class AppSettingsAPITests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="settings_user",
            email="settings-user@example.com",
            password="StrongPass123!",
        )
        self.url = reverse("app-settings")
        self.meta_url = reverse("app-settings-meta")
        self.reset_url = reverse("app-settings-reset")

    def authenticate(self):
        self.client.force_authenticate(user=self.user)

    def test_app_settings_requires_authentication(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(response.data["success"])

    def test_get_app_settings_creates_defaults(self):
        self.authenticate()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["timezone"], "Asia/Krasnoyarsk")
        self.assertEqual(response.data["dateFormat"], "DD.MM.YYYY")
        self.assertEqual(response.data["numberFormat"], "ru-RU")
        self.assertEqual(response.data["defaultCurrency"], "RUB")
        self.assertIn("createdAt", response.data)
        self.assertIn("updatedAt", response.data)
        self.assertTrue(UserAppSettings.objects.filter(user=self.user).exists())

    def test_put_app_settings_updates_all_fields(self):
        self.authenticate()
        ensure_user_currencies(self.user)

        response = self.client.put(
            self.url,
            {
                "timezone": "Europe/Moscow",
                "dateFormat": "YYYY-MM-DD",
                "numberFormat": "en-US",
                "defaultCurrency": "USD",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["timezone"], "Europe/Moscow")
        self.assertEqual(response.data["dateFormat"], "YYYY-MM-DD")
        self.assertEqual(response.data["numberFormat"], "en-US")
        self.assertEqual(response.data["defaultCurrency"], "USD")

        settings = UserAppSettings.objects.get(user=self.user)
        self.assertEqual(settings.timezone, "Europe/Moscow")
        self.assertEqual(settings.date_format, "YYYY-MM-DD")
        self.assertEqual(settings.number_format, "en-US")
        self.assertEqual(settings.default_currency, "USD")

    def test_patch_app_settings_updates_partially(self):
        self.authenticate()

        response = self.client.patch(
            self.url,
            {
                "timezone": "UTC",
                "numberFormat": "en-US",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["timezone"], "UTC")
        self.assertEqual(response.data["dateFormat"], "DD.MM.YYYY")
        self.assertEqual(response.data["numberFormat"], "en-US")
        self.assertEqual(response.data["defaultCurrency"], "RUB")

    def test_app_settings_accepts_snake_case_aliases(self):
        self.authenticate()

        response = self.client.patch(
            self.url,
            {
                "date_format": "MM/DD/YYYY",
                "number_format": "en-US",
                "default_currency": "RUB",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["dateFormat"], "MM/DD/YYYY")
        self.assertEqual(response.data["numberFormat"], "en-US")
        self.assertEqual(response.data["defaultCurrency"], "RUB")

    def test_app_settings_validates_invalid_values(self):
        self.authenticate()

        response = self.client.patch(
            self.url,
            {
                "timezone": "Wrong/Timezone",
                "dateFormat": "DD-MM-YYYY",
                "numberFormat": "de-DE",
                "defaultCurrency": "ZZZ",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        field_errors = response.data["error"]["field_errors"]
        self.assertIn("timezone", field_errors)
        self.assertIn("dateFormat", field_errors)
        self.assertIn("numberFormat", field_errors)
        self.assertIn("defaultCurrency", field_errors)

    def test_app_settings_meta_returns_options(self):
        self.authenticate()

        response = self.client.get(self.meta_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("timezones", response.data)
        self.assertIn("dateFormats", response.data)
        self.assertIn("numberFormats", response.data)
        self.assertIn("currencies", response.data)
        self.assertEqual(response.data["defaults"]["timezone"], "Asia/Krasnoyarsk")
        self.assertEqual(response.data["defaults"]["dateFormat"], "DD.MM.YYYY")
        self.assertEqual(response.data["defaults"]["numberFormat"], "ru-RU")
        self.assertEqual(response.data["defaults"]["defaultCurrency"], "RUB")
        currency_values = {item["value"] for item in response.data["currencies"]}
        self.assertIn("RUB", currency_values)

    def test_app_settings_reset_restores_defaults(self):
        self.authenticate()
        self.client.patch(
            self.url,
            {
                "timezone": "UTC",
                "dateFormat": "YYYY-MM-DD",
                "numberFormat": "en-US",
                "defaultCurrency": "USD",
            },
            format="json",
        )

        response = self.client.post(self.reset_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["reset"])
        settings = response.data["settings"]
        self.assertEqual(settings["timezone"], "Asia/Krasnoyarsk")
        self.assertEqual(settings["dateFormat"], "DD.MM.YYYY")
        self.assertEqual(settings["numberFormat"], "ru-RU")
        self.assertEqual(settings["defaultCurrency"], "RUB")

    def test_app_settings_page_flow_saves_and_reloads_updated_values(self):
        self.authenticate()
        ensure_user_currencies(self.user)

        initial_response = self.client.get(self.url)
        self.assertEqual(initial_response.status_code, status.HTTP_200_OK)
        self.assertEqual(initial_response.data["defaultCurrency"], "RUB")

        update_response = self.client.patch(
            self.url,
            {
                "timezone": "Europe/Moscow",
                "dateFormat": "MM/DD/YYYY",
                "numberFormat": "en-US",
                "defaultCurrency": "USD",
            },
            format="json",
        )
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)

        reload_response = self.client.get(self.url)
        self.assertEqual(reload_response.status_code, status.HTTP_200_OK)
        self.assertEqual(reload_response.data["timezone"], "Europe/Moscow")
        self.assertEqual(reload_response.data["dateFormat"], "MM/DD/YYYY")
        self.assertEqual(reload_response.data["numberFormat"], "en-US")
        self.assertEqual(reload_response.data["defaultCurrency"], "USD")

        meta_response = self.client.get(self.meta_url)
        self.assertEqual(meta_response.status_code, status.HTTP_200_OK)
        usd_option = next(item for item in meta_response.data["currencies"] if item["value"] == "USD")
        rub_option = next(item for item in meta_response.data["currencies"] if item["value"] == "RUB")
        self.assertTrue(usd_option["isDefault"])
        self.assertFalse(rub_option["isDefault"])

    def test_hidden_currency_cannot_be_selected_as_new_default_currency(self):
        self.authenticate()
        ensure_user_currencies(self.user)
        usd = get_user_currency_by_code(self.user, "USD")
        usd.is_visible = False
        usd.save(update_fields=["is_visible", "updated_at"])

        response = self.client.patch(
            self.url,
            {"defaultCurrency": "USD"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        self.assertIn("defaultCurrency", response.data["error"]["field_errors"])

    def test_existing_hidden_default_currency_does_not_break_other_updates(self):
        self.authenticate()
        ensure_user_currencies(self.user)
        usd = get_user_currency_by_code(self.user, "USD")
        usd.is_visible = False
        usd.save(update_fields=["is_visible", "updated_at"])
        UserAppSettings.objects.create(
            user=self.user,
            timezone="Asia/Krasnoyarsk",
            date_format="DD.MM.YYYY",
            number_format="ru-RU",
            default_currency="USD",
        )

        response = self.client.patch(
            self.url,
            {"timezone": "UTC", "defaultCurrency": "USD"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["timezone"], "UTC")
        self.assertEqual(response.data["defaultCurrency"], "USD")

    def test_app_settings_rejects_timezone_outside_meta_options(self):
        self.authenticate()

        response = self.client.patch(
            self.url,
            {"timezone": "Europe/Berlin"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("timezone", response.data["error"]["field_errors"])
