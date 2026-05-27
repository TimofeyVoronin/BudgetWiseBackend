from decimal import Decimal

from django.core.cache import cache
from django.test import override_settings
from rest_framework.exceptions import ValidationError

from apps.finance.currencies.conversion import (
    CURRENCY_WARNING_SERVICE_UNAVAILABLE,
    CurrencyConversionService,
)
from apps.finance.currencies.services import get_user_currency_by_code
from apps.finance.testing import FinanceAPITestCase
from apps.users.app_settings.services import get_or_create_user_app_settings


@override_settings(CURRENCY_RATES_ENABLED=False)
class CurrencyConversionServiceTests(FinanceAPITestCase):
    def setUp(self):
        super().setUp()
        self.authenticate()
        CurrencyConversionService(user=self.user, refresh_rates=False)

    def set_rate(self, code: str, value: str):
        user_currency = get_user_currency_by_code(self.user, code)
        user_currency.rate_to_primary = Decimal(value)
        user_currency.save(update_fields=["rate_to_primary", "updated_at"])

    def test_convert_from_account_currency_to_display_currency(self):
        self.set_rate("USD", "100.00000000")
        service = CurrencyConversionService(
            user=self.user,
            display_currency="USD",
            refresh_rates=False,
        )

        result = service.convert_to_display(
            Decimal("500.00"),
            source_currency="RUB",
        )

        self.assertEqual(result.currency, "USD")
        self.assertEqual(result.amount, Decimal("5.00"))
        self.assertEqual(result.as_payload(), {"amount": 5.0, "currency": "USD"})

    def test_convert_between_non_primary_currencies_through_primary_currency(self):
        self.set_rate("USD", "100.00000000")
        self.set_rate("EUR", "125.00000000")
        service = CurrencyConversionService(
            user=self.user,
            display_currency="EUR",
            refresh_rates=False,
        )

        result = service.convert_to_display(
            Decimal("10.00"),
            source_currency="USD",
        )

        self.assertEqual(result.currency, "EUR")
        self.assertEqual(result.amount, Decimal("8.00"))

    def test_display_currency_falls_back_to_user_default_currency(self):
        settings = get_or_create_user_app_settings(self.user)
        settings.default_currency = "EUR"
        settings.save(update_fields=["default_currency", "updated_at"])

        service = CurrencyConversionService(user=self.user, refresh_rates=False)

        self.assertEqual(service.display_currency, "EUR")
        self.assertEqual(service.context_payload()["code"], "EUR")
        self.assertEqual(service.context_payload()["primaryCode"], "RUB")

    def test_hidden_display_currency_is_rejected(self):
        usd = get_user_currency_by_code(self.user, "USD")
        usd.is_visible = False
        usd.save(update_fields=["is_visible", "updated_at"])

        with self.assertRaises(ValidationError):
            CurrencyConversionService(
                user=self.user,
                display_currency="USD",
                refresh_rates=False,
            )

    def test_context_warns_when_currency_provider_failed(self):
        cache.set("finance:currency-rates:failure", True, timeout=300)

        service = CurrencyConversionService(user=self.user, refresh_rates=False)
        context = service.context_payload()

        self.assertFalse(context["sourceAvailable"])
        self.assertTrue(context["usingCachedRates"])
        self.assertEqual(context["warning"], CURRENCY_WARNING_SERVICE_UNAVAILABLE)
