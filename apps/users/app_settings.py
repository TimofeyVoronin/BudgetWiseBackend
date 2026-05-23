from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import transaction

from apps.finance.currencies import (
    build_currency_select_options,
    get_user_currency_by_code,
    get_user_primary_currency_code,
    normalize_currency_code,
)
from apps.users.models import AppDateFormat, AppNumberFormat, UserAppSettings


DEFAULT_APP_TIMEZONE = "Asia/Krasnoyarsk"
DEFAULT_APP_DATE_FORMAT = AppDateFormat.DD_MM_YYYY
DEFAULT_APP_NUMBER_FORMAT = AppNumberFormat.RU_RU

TIMEZONE_OPTIONS = [
    {
        "value": "Asia/Krasnoyarsk",
        "label": "UTC+7 Красноярск",
        "offsetHours": 7,
    },
    {
        "value": "Europe/Moscow",
        "label": "UTC+3 Москва",
        "offsetHours": 3,
    },
    {
        "value": "UTC",
        "label": "UTC",
        "offsetHours": 0,
    },
]

DATE_FORMAT_OPTIONS = [
    {
        "value": AppDateFormat.DD_MM_YYYY,
        "label": "24.05.2026",
        "example": "24.05.2026",
    },
    {
        "value": AppDateFormat.YYYY_MM_DD,
        "label": "2026-05-24",
        "example": "2026-05-24",
    },
    {
        "value": AppDateFormat.MM_DD_YYYY,
        "label": "05/24/2026",
        "example": "05/24/2026",
    },
]

NUMBER_FORMAT_OPTIONS = [
    {
        "value": AppNumberFormat.RU_RU,
        "label": "Русский формат",
        "example": "1 234 567,89",
    },
    {
        "value": AppNumberFormat.EN_US,
        "label": "Английский формат",
        "example": "1,234,567.89",
    },
]


def get_allowed_timezone_values() -> set[str]:
    return {str(item["value"]) for item in TIMEZONE_OPTIONS}


def is_valid_timezone(value: str) -> bool:
    normalized = str(value or "").strip()

    if normalized not in get_allowed_timezone_values():
        return False

    try:
        ZoneInfo(normalized)
    except (ZoneInfoNotFoundError, ValueError):
        return False

    return True


def get_default_app_currency(user) -> str:
    return get_user_primary_currency_code(user)


def get_or_create_user_app_settings(user) -> UserAppSettings:
    default_currency = get_default_app_currency(user)
    settings, created = UserAppSettings.objects.get_or_create(
        user=user,
        defaults={
            "timezone": DEFAULT_APP_TIMEZONE,
            "date_format": DEFAULT_APP_DATE_FORMAT,
            "number_format": DEFAULT_APP_NUMBER_FORMAT,
            "default_currency": default_currency,
        },
    )

    update_fields: list[str] = []

    if not settings.default_currency:
        settings.default_currency = default_currency
        update_fields.append("default_currency")

    if not settings.timezone:
        settings.timezone = DEFAULT_APP_TIMEZONE
        update_fields.append("timezone")

    if update_fields:
        settings.save(update_fields=[*update_fields, "updated_at"])

    return settings


@transaction.atomic
def reset_user_app_settings(user) -> UserAppSettings:
    settings = get_or_create_user_app_settings(user)
    settings.timezone = DEFAULT_APP_TIMEZONE
    settings.date_format = DEFAULT_APP_DATE_FORMAT
    settings.number_format = DEFAULT_APP_NUMBER_FORMAT
    settings.default_currency = get_default_app_currency(user)
    settings.save(
        update_fields=[
            "timezone",
            "date_format",
            "number_format",
            "default_currency",
            "updated_at",
        ]
    )
    return settings


def validate_default_currency_for_user(
    user,
    value: str,
    *,
    current_value: str | None = None,
) -> str:
    normalized = normalize_currency_code(value)
    current_normalized = normalize_currency_code(current_value or "")

    if not normalized:
        from rest_framework import serializers

        raise serializers.ValidationError("Валюта по умолчанию обязательна.", code="required")

    if len(normalized) != 3 or not normalized.isalpha() or not normalized.isupper():
        from rest_framework import serializers

        raise serializers.ValidationError(
            "Валюта должна быть указана ISO-кодом из 3 латинских букв.",
            code="invalid_currency_code",
        )

    user_currency = get_user_currency_by_code(user, normalized)
    if user_currency is None:
        from rest_framework import serializers

        raise serializers.ValidationError(
            "Валюта по умолчанию должна быть добавлена в список валют пользователя.",
            code="currency_not_available",
        )

    if not user_currency.is_visible and normalized != current_normalized:
        from rest_framework import serializers

        raise serializers.ValidationError(
            "Скрытую валюту нельзя выбрать как новую валюту по умолчанию.",
            code="currency_hidden",
        )

    return normalized


def build_app_settings_meta(user) -> dict:
    return {
        "timezones": TIMEZONE_OPTIONS,
        "dateFormats": DATE_FORMAT_OPTIONS,
        "numberFormats": NUMBER_FORMAT_OPTIONS,
        "currencies": build_currency_select_options(user),
        "defaults": {
            "timezone": DEFAULT_APP_TIMEZONE,
            "dateFormat": DEFAULT_APP_DATE_FORMAT,
            "numberFormat": DEFAULT_APP_NUMBER_FORMAT,
            "defaultCurrency": get_default_app_currency(user),
        },
    }
