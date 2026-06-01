from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings
from django.core.cache import cache
from rest_framework.exceptions import ValidationError

from apps.finance.currencies.money import MoneyAmount, normalize_decimal, quantize_money
from apps.finance.currencies.rates import refresh_user_currency_rates
from apps.finance.currencies.services import (
    DEFAULT_CURRENCY_CODE,
    ensure_user_currencies,
    is_valid_currency_code,
    normalize_currency_code,
)
from apps.finance.models import UserCurrency
from apps.users.models import UserAppSettings

RATE_FAILURE_CACHE_KEY = "finance:currency-rates:failure"
CURRENCY_WARNING_SERVICE_UNAVAILABLE = (
    "Курсы валют временно недоступны. Используются последние доступные значения."
)


@dataclass(frozen=True)
class CurrencyConversionContext:
    display_currency: str
    primary_currency: str
    source_available: bool = True
    using_cached_rates: bool = False
    warning: str = ""

    def as_payload(self) -> dict:
        return {
            "code": self.display_currency,
            "primaryCode": self.primary_currency,
            "sourceAvailable": self.source_available,
            "usingCachedRates": self.using_cached_rates,
            "warning": self.warning,
        }


class CurrencyConversionService:
    """Convert user money values through the user's primary currency.

    Storage may keep amounts in their original entity currency. Aggregated API
    responses can use this service to normalize values through the user's
    primary currency and return the selected display currency.
    """

    def __init__(
        self,
        *,
        user,
        display_currency: str | None = None,
        require_visible_display_currency: bool = True,
        refresh_rates: bool = True,
        force_refresh: bool = False,
    ) -> None:
        self.user = user
        self._user_currencies_by_code = self._load_user_currencies_by_code()

        if not self._user_currencies_by_code:
            ensure_user_currencies(user)
            self._user_currencies_by_code = self._load_user_currencies_by_code()

        if refresh_rates and getattr(settings, "CURRENCY_RATES_ENABLED", True):
            refresh_user_currency_rates(user, force=force_refresh)
            self._user_currencies_by_code = self._load_user_currencies_by_code()

        self.primary_currency = self._resolve_primary_currency()
        self.display_currency = self.resolve_display_currency(
            display_currency,
            require_visible=require_visible_display_currency,
        )
        self._rate_to_primary_cache: dict[str, Decimal] = {
            self.primary_currency: Decimal("1.00000000"),
        }

    def _load_user_currencies_by_code(self) -> dict[str, UserCurrency]:
        return {
            user_currency.currency.code: user_currency
            for user_currency in (
                UserCurrency.objects
                .filter(user=self.user)
                .select_related("currency")
            )
        }

    def _resolve_primary_currency(self) -> str:
        primary_currency = next(
            (
                user_currency.code
                for user_currency in self._user_currencies_by_code.values()
                if user_currency.is_primary
            ),
            "",
        )
        return primary_currency or DEFAULT_CURRENCY_CODE

    def _get_default_currency_code(self) -> str:
        default_currency = normalize_currency_code(
            UserAppSettings.objects
            .filter(user=self.user)
            .values_list("default_currency", flat=True)
            .first()
            or ""
        )

        if not default_currency:
            return self.primary_currency

        user_currency = self._user_currencies_by_code.get(default_currency)

        if user_currency is None or not user_currency.is_visible:
            return self.primary_currency

        return default_currency

    def _validate_display_currency(
        self,
        currency: str,
        *,
        require_visible: bool,
    ) -> str:
        normalized_currency = normalize_currency_code(currency)

        if not is_valid_currency_code(normalized_currency):
            raise ValidationError(
                {"currency": ["Валюта должна быть указана ISO-кодом из 3 латинских букв."]}
            )

        user_currency = self._user_currencies_by_code.get(normalized_currency)
        if user_currency is None:
            raise ValidationError({"currency": ["Валюта не добавлена в список валют пользователя."]})

        if require_visible and not user_currency.is_visible:
            raise ValidationError({"currency": ["Скрытую валюту нельзя выбрать для новых данных."]})

        return normalized_currency

    def resolve_display_currency(
        self,
        currency: str | None = None,
        *,
        require_visible: bool = True,
    ) -> str:
        requested_currency = normalize_currency_code(currency or "")

        if requested_currency:
            return self._validate_display_currency(
                requested_currency,
                require_visible=require_visible,
            )

        default_currency = self._get_default_currency_code()
        if default_currency:
            user_currency = self._user_currencies_by_code.get(default_currency)
            if user_currency is not None and (user_currency.is_visible or not require_visible):
                return default_currency

        primary_currency = self.primary_currency or DEFAULT_CURRENCY_CODE
        user_currency = self._user_currencies_by_code.get(primary_currency)
        if user_currency is not None and (user_currency.is_visible or not require_visible):
            return primary_currency

        return DEFAULT_CURRENCY_CODE

    def convert(
        self,
        amount,
        *,
        source_currency: str | None,
        target_currency: str | None = None,
        quantize: bool = True,
    ) -> MoneyAmount:
        source_code = normalize_currency_code(source_currency or self.primary_currency)
        target_code = normalize_currency_code(target_currency or self.display_currency)
        value = normalize_decimal(amount)

        if source_code == target_code:
            return MoneyAmount(
                amount=quantize_money(value) if quantize else value,
                currency=target_code,
            )

        source_rate = self.get_rate_to_primary(source_code)
        target_rate = self.get_rate_to_primary(target_code)

        converted = (value * source_rate) / target_rate
        if quantize:
            converted = quantize_money(converted)

        return MoneyAmount(amount=converted, currency=target_code)

    def convert_to_display(
        self,
        amount,
        *,
        source_currency: str | None,
        quantize: bool = True,
    ) -> MoneyAmount:
        return self.convert(
            amount,
            source_currency=source_currency,
            target_currency=self.display_currency,
            quantize=quantize,
        )

    def convert_to_primary(
        self,
        amount,
        *,
        source_currency: str | None,
        quantize: bool = True,
    ) -> MoneyAmount:
        return self.convert(
            amount,
            source_currency=source_currency,
            target_currency=self.primary_currency,
            quantize=quantize,
        )

    def amount_payload(
        self,
        amount,
        *,
        source_currency: str | None,
        target_currency: str | None = None,
        quantize: bool = True,
    ) -> dict:
        return self.convert(
            amount,
            source_currency=source_currency,
            target_currency=target_currency,
            quantize=quantize,
        ).as_payload()

    def display_amount_payload(
        self,
        amount,
        *,
        source_currency: str | None,
        quantize: bool = True,
    ) -> dict:
        return self.convert_to_display(
            amount,
            source_currency=source_currency,
            quantize=quantize,
        ).as_payload()

    def get_rate_to_primary(self, currency: str) -> Decimal:
        code = normalize_currency_code(currency)

        if code == self.primary_currency:
            return Decimal("1.00000000")

        if code in self._rate_to_primary_cache:
            return self._rate_to_primary_cache[code]

        user_currency = self._user_currencies_by_code.get(code)
        if user_currency is None:
            raise ValidationError({"currency": ["Валюта не добавлена в список валют пользователя."]})

        rate_to_primary = normalize_decimal(user_currency.rate_to_primary)
        self._rate_to_primary_cache[code] = rate_to_primary
        return rate_to_primary

    def get_context(self) -> CurrencyConversionContext:
        using_cached_rates = bool(cache.get(RATE_FAILURE_CACHE_KEY))
        source_available = not using_cached_rates
        warning = CURRENCY_WARNING_SERVICE_UNAVAILABLE if using_cached_rates else ""

        return CurrencyConversionContext(
            display_currency=self.display_currency,
            primary_currency=self.primary_currency,
            source_available=source_available,
            using_cached_rates=using_cached_rates,
            warning=warning,
        )

    def context_payload(self) -> dict:
        return self.get_context().as_payload()


def get_currency_conversion_service(
    user,
    *,
    display_currency: str | None = None,
    require_visible_display_currency: bool = True,
    refresh_rates: bool = True,
    force_refresh: bool = False,
) -> CurrencyConversionService:
    return CurrencyConversionService(
        user=user,
        display_currency=display_currency,
        require_visible_display_currency=require_visible_display_currency,
        refresh_rates=refresh_rates,
        force_refresh=force_refresh,
    )

