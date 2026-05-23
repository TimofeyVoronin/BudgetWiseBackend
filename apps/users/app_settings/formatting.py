from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone as datetime_timezone, tzinfo
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.utils import timezone as django_timezone

from apps.finance.currencies import DEFAULT_CURRENCY_CODE, get_user_currency_by_code, normalize_currency_code
from apps.users.app_settings.services import DEFAULT_APP_TIMEZONE, get_or_create_user_app_settings
from apps.users.models import AppDateFormat, AppNumberFormat, UserAppSettings


DATE_FORMAT_PATTERNS = {
    AppDateFormat.DD_MM_YYYY: "%d.%m.%Y",
    AppDateFormat.YYYY_MM_DD: "%Y-%m-%d",
    AppDateFormat.MM_DD_YYYY: "%m/%d/%Y",
}

LEGACY_TIMEZONE_OFFSETS = {
    "UTC+0": 0,
    "UTC": 0,
    "UTC+3": 3,
    "UTC+7": 7,
}


@dataclass(frozen=True)
class AppSettingsFormattingContext:
    timezone_name: str
    timezone: tzinfo
    date_format: str
    number_format: str
    default_currency: str


def get_user_app_formatting_context(user) -> AppSettingsFormattingContext:
    settings = get_or_create_user_app_settings(user)
    return build_app_formatting_context(user, settings=settings)


def build_app_formatting_context(
    user,
    *,
    settings: UserAppSettings | None = None,
    timezone_value: str | None = None,
) -> AppSettingsFormattingContext:
    settings = settings or get_or_create_user_app_settings(user)
    timezone_name = str(timezone_value or settings.timezone or DEFAULT_APP_TIMEZONE).strip()

    return AppSettingsFormattingContext(
        timezone_name=timezone_name,
        timezone=resolve_app_timezone(timezone_name),
        date_format=settings.date_format or AppDateFormat.DD_MM_YYYY,
        number_format=settings.number_format or AppNumberFormat.RU_RU,
        default_currency=normalize_currency_code(settings.default_currency or DEFAULT_CURRENCY_CODE),
    )


def resolve_app_timezone(value: str | None) -> tzinfo:
    normalized = str(value or DEFAULT_APP_TIMEZONE).strip()

    if normalized in LEGACY_TIMEZONE_OFFSETS:
        return datetime_timezone(timedelta(hours=LEGACY_TIMEZONE_OFFSETS[normalized]))

    try:
        return ZoneInfo(normalized)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_APP_TIMEZONE)


def get_user_app_timezone(user) -> tzinfo:
    return get_user_app_formatting_context(user).timezone


def get_user_app_today(user, *, timezone_value: str | None = None) -> date:
    context = build_app_formatting_context(user, timezone_value=timezone_value)
    return django_timezone.localdate(timezone=context.timezone)


def format_app_date(value, context: AppSettingsFormattingContext) -> str | None:
    resolved_date = coerce_to_date(value, context)
    if resolved_date is None:
        return None

    pattern = DATE_FORMAT_PATTERNS.get(context.date_format, DATE_FORMAT_PATTERNS[AppDateFormat.DD_MM_YYYY])
    return resolved_date.strftime(pattern)


def coerce_to_date(value, context: AppSettingsFormattingContext) -> date | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=datetime_timezone.utc)
        return value.astimezone(context.timezone).date()

    if isinstance(value, date):
        return value

    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None
        try:
            return date.fromisoformat(normalized[:10])
        except ValueError:
            return None

    return None


def format_app_number(
    value,
    context: AppSettingsFormattingContext,
    *,
    decimal_places: int = 2,
) -> str | None:
    decimal_value = coerce_to_decimal(value)
    if decimal_value is None:
        return None

    quant = Decimal("1") if decimal_places <= 0 else Decimal("1").scaleb(-decimal_places)
    decimal_value = decimal_value.quantize(quant, rounding=ROUND_HALF_UP)
    abs_value = abs(decimal_value)
    number = f"{abs_value:,.{decimal_places}f}"

    if context.number_format == AppNumberFormat.RU_RU:
        number = number.replace(",", " ").replace(".", ",")

    sign = "-" if decimal_value < 0 else ""
    return f"{sign}{number}"


def format_app_money(
    value,
    context: AppSettingsFormattingContext,
    *,
    user=None,
    currency_code: str | None = None,
    decimal_places: int = 2,
) -> str | None:
    number = format_app_number(value, context, decimal_places=decimal_places)
    if number is None:
        return None

    symbol = get_currency_symbol(
        user,
        currency_code or context.default_currency,
    )
    return f"{number} {symbol}" if symbol else number


def coerce_to_decimal(value) -> Decimal | None:
    if value is None:
        return None

    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def get_currency_symbol(user, currency_code: str | None) -> str:
    normalized_code = normalize_currency_code(currency_code or DEFAULT_CURRENCY_CODE)

    if user is not None and getattr(user, "is_authenticated", False):
        user_currency = get_user_currency_by_code(user, normalized_code)
        if user_currency is not None:
            return user_currency.display_symbol

    fallback_symbols = {
        "RUB": "₽",
        "USD": "$",
        "EUR": "€",
        "KZT": "₸",
        "CNY": "¥",
        "THB": "฿",
        "BYN": "Br",
        "GBP": "£",
        "BTC": "₿",
        "ETH": "Ξ",
    }
    return fallback_symbols.get(normalized_code, normalized_code)
