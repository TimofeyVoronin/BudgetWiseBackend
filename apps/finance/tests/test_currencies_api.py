from decimal import Decimal

from rest_framework import status

from apps.finance.currencies import get_user_currencies
from apps.finance.models import Account, Currency, UserCurrency
from apps.finance.tests.base import FinanceAPITestCase


CURRENCIES_URL = "/api/v1/finance/currencies/"


class FinanceCurrenciesAPITests(FinanceAPITestCase):
    def get_currency_row(self, code: str, response=None):
        if response is None:
            response = self.client.get(CURRENCIES_URL)
        return next(item for item in response.data["items"] if item["code"] == code)

    def test_currency_list_requires_authentication(self):
        response = self.client.get(CURRENCIES_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(response.data["success"])

    def test_currency_list_seeds_default_currencies_and_summary(self):
        self.authenticate()

        response = self.client.get(CURRENCIES_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("items", response.data)
        self.assertIn("summary", response.data)
        self.assertGreaterEqual(response.data["summary"]["totalCount"], 10)
        self.assertEqual(response.data["summary"]["primaryCode"], "RUB")
        codes = {item["code"] for item in response.data["items"]}
        self.assertIn("RUB", codes)
        self.assertIn("USD", codes)
        self.assertIn("EUR", codes)

        rub = self.get_currency_row("RUB", response)
        self.assertTrue(rub["isPrimary"])
        self.assertTrue(rub["isVisible"])
        self.assertFalse(rub["isCustom"])
        self.assertEqual(rub["rateToPrimary"], 1.0)

    def test_set_primary_currency_keeps_only_one_primary_and_makes_currency_visible(self):
        self.authenticate()
        response = self.client.get(CURRENCIES_URL)
        usd = self.get_currency_row("USD", response)

        hide_response = self.client.patch(
            f"{CURRENCIES_URL}{usd['id']}/visibility/",
            {"isVisible": False},
            format="json",
        )
        self.assertEqual(hide_response.status_code, status.HTTP_200_OK)
        self.assertFalse(hide_response.data["isVisible"])

        primary_response = self.client.patch(f"{CURRENCIES_URL}{usd['id']}/set-primary/")

        self.assertEqual(primary_response.status_code, status.HTTP_200_OK)
        self.assertEqual(primary_response.data["summary"]["primaryCode"], "USD")
        primary_items = [item for item in primary_response.data["items"] if item["isPrimary"]]
        self.assertEqual(len(primary_items), 1)
        self.assertEqual(primary_items[0]["code"], "USD")
        self.assertTrue(primary_items[0]["isVisible"])

        user_primary_count = UserCurrency.objects.filter(user=self.user, is_primary=True).count()
        self.assertEqual(user_primary_count, 1)

    def test_primary_currency_cannot_be_hidden_or_deleted(self):
        self.authenticate()
        rub = self.get_currency_row("RUB")

        hide_response = self.client.patch(
            f"{CURRENCIES_URL}{rub['id']}/visibility/",
            {"isVisible": False},
            format="json",
        )
        self.assertEqual(hide_response.status_code, status.HTTP_409_CONFLICT)

        delete_response = self.client.delete(f"{CURRENCIES_URL}{rub['id']}/")
        self.assertEqual(delete_response.status_code, status.HTTP_409_CONFLICT)

    def test_system_currency_cannot_be_deleted_but_can_be_hidden(self):
        self.authenticate()
        usd = self.get_currency_row("USD")

        hide_response = self.client.patch(
            f"{CURRENCIES_URL}{usd['id']}/visibility/",
            {"isVisible": False},
            format="json",
        )
        self.assertEqual(hide_response.status_code, status.HTTP_200_OK)
        self.assertFalse(hide_response.data["isVisible"])

        delete_response = self.client.delete(f"{CURRENCIES_URL}{usd['id']}/")
        self.assertEqual(delete_response.status_code, status.HTTP_409_CONFLICT)

    def test_custom_currency_create_update_validate_check_code_and_delete(self):
        self.authenticate()

        available_response = self.client.get(
            f"{CURRENCIES_URL}check-code/",
            {"code": "ABC"},
        )
        self.assertEqual(available_response.status_code, status.HTTP_200_OK)
        self.assertTrue(available_response.data["available"])

        create_response = self.client.post(
            f"{CURRENCIES_URL}custom/",
            {
                "code": "abc",
                "name": " Тестовая   валюта ",
                "symbol": " A ",
                "isVisible": True,
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(create_response.data["code"], "ABC")
        self.assertEqual(create_response.data["name"], "Тестовая валюта")
        self.assertEqual(create_response.data["symbol"], "A")
        self.assertTrue(create_response.data["isCustom"])

        currency_id = create_response.data["id"]

        duplicate_check_response = self.client.get(
            f"{CURRENCIES_URL}check-code/",
            {"code": "ABC"},
        )
        self.assertEqual(duplicate_check_response.status_code, status.HTTP_200_OK)
        self.assertFalse(duplicate_check_response.data["available"])

        validate_response = self.client.post(
            f"{CURRENCIES_URL}validate-custom/",
            {
                "code": "ABC",
                "name": "Дубль",
                "symbol": "D",
            },
            format="json",
        )
        self.assertEqual(validate_response.status_code, status.HTTP_200_OK)
        self.assertFalse(validate_response.data["ok"])
        self.assertIn("code", validate_response.data["fieldErrors"])

        update_response = self.client.patch(
            f"{CURRENCIES_URL}{currency_id}/",
            {
                "name": "Новая валюта",
                "symbol": "N",
                "isVisible": False,
            },
            format="json",
        )
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.data["name"], "Новая валюта")
        self.assertEqual(update_response.data["symbol"], "N")
        self.assertFalse(update_response.data["isVisible"])

        delete_response = self.client.delete(f"{CURRENCIES_URL}{currency_id}/")
        self.assertEqual(delete_response.status_code, status.HTTP_200_OK)
        self.assertTrue(delete_response.data["deleted"])
        self.assertFalse(UserCurrency.objects.filter(pk=currency_id).exists())

    def test_used_custom_currency_cannot_be_deleted(self):
        self.authenticate()
        create_response = self.client.post(
            f"{CURRENCIES_URL}custom/",
            {
                "code": "XYZ",
                "name": "Валюта проекта",
                "symbol": "X",
                "isVisible": True,
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        currency_id = create_response.data["id"]

        Account.objects.create(
            user=self.user,
            name="Счёт в XYZ",
            type="card",
            currency="XYZ",
            initial_balance=Decimal("100.00"),
            balance=Decimal("100.00"),
        )

        delete_response = self.client.delete(f"{CURRENCIES_URL}{currency_id}/")

        self.assertEqual(delete_response.status_code, status.HTTP_409_CONFLICT)
        self.assertFalse(delete_response.data["success"])
        self.assertIn("HAS_OPERATIONS", delete_response.data["error"]["code"])

    def test_select_options_return_only_visible_currencies(self):
        self.authenticate()
        usd = self.get_currency_row("USD")
        self.client.patch(
            f"{CURRENCIES_URL}{usd['id']}/visibility/",
            {"isVisible": False},
            format="json",
        )

        response = self.client.get(f"{CURRENCIES_URL}select-options/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["primaryCode"], "RUB")
        values = {item["value"] for item in response.data["options"]}
        self.assertIn("RUB", values)
        self.assertNotIn("USD", values)

    def test_catalog_search_from_catalog_and_list_filters(self):
        self.authenticate()

        catalog_response = self.client.get(
            f"{CURRENCIES_URL}catalog/",
            {"search": "bitcoin"},
        )
        self.assertEqual(catalog_response.status_code, status.HTTP_200_OK)
        self.assertEqual(catalog_response.data["items"][0]["code"], "BTC")

        btc = self.get_currency_row("BTC")
        self.client.patch(
            f"{CURRENCIES_URL}{btc['id']}/visibility/",
            {"isVisible": False},
            format="json",
        )
        from_catalog_response = self.client.post(
            f"{CURRENCIES_URL}from-catalog/",
            {"code": "btc"},
            format="json",
        )
        self.assertIn(from_catalog_response.status_code, {status.HTTP_200_OK, status.HTTP_201_CREATED})
        self.assertEqual(from_catalog_response.data["code"], "BTC")
        self.assertTrue(from_catalog_response.data["isVisible"])

        custom_response = self.client.post(
            f"{CURRENCIES_URL}custom/",
            {
                "code": "QWE",
                "name": "Qwerty coin",
                "symbol": "Q",
                "isVisible": True,
            },
            format="json",
        )
        self.assertEqual(custom_response.status_code, status.HTTP_201_CREATED)

        custom_filter_response = self.client.get(
            CURRENCIES_URL,
            {"isCustom": "true", "search": "qwe"},
        )
        self.assertEqual(custom_filter_response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["code"] for item in custom_filter_response.data["items"]], ["QWE"])

    def test_user_cannot_access_other_users_currency_settings(self):
        self.authenticate()
        other_currency = get_user_currencies(self.other_user).get(currency__code="USD")

        detail_response = self.client.get(f"{CURRENCIES_URL}{other_currency.id}/")
        update_response = self.client.patch(
            f"{CURRENCIES_URL}{other_currency.id}/visibility/",
            {"isVisible": False},
            format="json",
        )
        delete_response = self.client.delete(f"{CURRENCIES_URL}{other_currency.id}/")

        self.assertEqual(detail_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(update_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(delete_response.status_code, status.HTTP_404_NOT_FOUND)

    def test_invalid_custom_currency_payload_returns_validation_errors(self):
        self.authenticate()

        response = self.client.post(
            f"{CURRENCIES_URL}validate-custom/",
            {
                "code": "12",
                "name": "",
                "symbol": "",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["ok"])
        self.assertIn("code", response.data["fieldErrors"])
        self.assertIn("name", response.data["fieldErrors"])
        self.assertIn("symbol", response.data["fieldErrors"])
