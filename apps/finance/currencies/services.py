from __future__ import annotations

import re
from decimal import Decimal
from typing import Iterable

from django.db import transaction
from django.db.models import Q

from apps.finance.models import (
    Account,
    Budget,
    Currency,
    Transaction,
    TransactionTemplate,
    UserCurrency,
)


DEFAULT_CURRENCY_CODE = "RUB"
MAX_CURRENCY_CODE_LENGTH = 3
MAX_CURRENCY_NAME_LENGTH = 100
MAX_CURRENCY_SYMBOL_LENGTH = 12

CURRENCY_CODE_RE = re.compile(r"^[A-Z]{3}$")

CURRENCY_CATALOG = [
    {
        "code": "RUB",
        "name": "Российский рубль",
        "symbol": "₽",
        "flagIcon": "rub",
        "decimalPlaces": 2,
        "popular": True,
        "rateToPrimary": Decimal("1.00000000"),
        "defaultVisible": True,
    },
    {
        "code": "USD",
        "name": "Доллар США",
        "symbol": "$",
        "flagIcon": "usd",
        "decimalPlaces": 2,
        "popular": True,
        "rateToPrimary": Decimal("90.00000000"),
        "defaultVisible": True,
    },
    {
        "code": "EUR",
        "name": "Евро",
        "symbol": "€",
        "flagIcon": "eur",
        "decimalPlaces": 2,
        "popular": True,
        "rateToPrimary": Decimal("98.00000000"),
        "defaultVisible": True,
    },
    {
        "code": "KZT",
        "name": "Казахстанский тенге",
        "symbol": "₸",
        "flagIcon": "kzt",
        "decimalPlaces": 2,
        "popular": True,
        "rateToPrimary": Decimal("0.18000000"),
        "defaultVisible": True,
    },
    {
        "code": "CNY",
        "name": "Китайский юань",
        "symbol": "¥",
        "flagIcon": "cny",
        "decimalPlaces": 2,
        "popular": True,
        "rateToPrimary": Decimal("12.50000000"),
        "defaultVisible": False,
    },
    {
        "code": "THB",
        "name": "Тайский бат",
        "symbol": "฿",
        "flagIcon": "thb",
        "decimalPlaces": 2,
        "popular": False,
        "rateToPrimary": Decimal("2.70000000"),
        "defaultVisible": True,
    },
    {
        "code": "BYN",
        "name": "Белорусский рубль",
        "symbol": "Br",
        "flagIcon": "byn",
        "decimalPlaces": 2,
        "popular": False,
        "rateToPrimary": Decimal("30.00000000"),
        "defaultVisible": True,
    },
    {
        "code": "GBP",
        "name": "Фунт стерлингов",
        "symbol": "£",
        "flagIcon": "gbp",
        "decimalPlaces": 2,
        "popular": True,
        "rateToPrimary": Decimal("115.00000000"),
        "defaultVisible": True,
    },
    {
        "code": "BTC",
        "name": "Bitcoin",
        "symbol": "₿",
        "flagIcon": "btc",
        "decimalPlaces": 8,
        "popular": False,
        "rateToPrimary": Decimal("9000000.00000000"),
        "defaultVisible": True,
    },
    {
        "code": "ETH",
        "name": "Ethereum",
        "symbol": "Ξ",
        "flagIcon": "eth",
        "decimalPlaces": 8,
        "popular": False,
        "rateToPrimary": Decimal("300000.00000000"),
        "defaultVisible": False,
    },
]

CATALOG_BY_CODE = {item["code"]: item for item in CURRENCY_CATALOG}
DEFAULT_VISIBLE_BY_CODE = {
    item["code"]: bool(item.get("defaultVisible", True))
    for item in CURRENCY_CATALOG
}
DEFAULT_RATE_BY_CODE = {
    item["code"]: Decimal(item.get("rateToPrimary", Decimal("1.00000000")))
    for item in CURRENCY_CATALOG
}

CURRENCY_SORT_FIELDS = {
    "code": "currency__code",
    "name": "currency__name",
    "rateToPrimary": "rate_to_primary",
    "rate_to_primary": "rate_to_primary",
    "isPrimary": "is_primary",
    "is_primary": "is_primary",
    "isVisible": "is_visible",
    "is_visible": "is_visible",
    "isCustom": "is_custom",
    "is_custom": "is_custom",
    "createdAt": "created_at",
    "created_at": "created_at",
}


def normalize_currency_code(value: str) -> str:
    return str(value or "").strip().upper()


def normalize_currency_text(value: str) -> str:
    return " ".join(str(value or "").split())


def normalize_currency_symbol(value: str) -> str:
    return str(value or "").strip()


def is_valid_currency_code(value: str) -> bool:
    return bool(CURRENCY_CODE_RE.fullmatch(normalize_currency_code(value)))


def get_catalog_item(code: str) -> dict | None:
    return CATALOG_BY_CODE.get(normalize_currency_code(code))


def seed_currency_catalog() -> None:
    for item in CURRENCY_CATALOG:
        Currency.objects.update_or_create(
            code=item["code"],
            defaults={
                "name": item["name"],
                "symbol": item["symbol"],
                "flag_icon": item["flagIcon"],
                "decimal_places": item["decimalPlaces"],
                "is_system": True,
                "is_popular": bool(item.get("popular", False)),
            },
        )


def ensure_user_currencies(user) -> None:
    catalog_codes = set(CATALOG_BY_CODE.keys())
    existing_system_codes = set(
        Currency.objects
        .filter(is_system=True, code__in=catalog_codes)
        .values_list("code", flat=True)
    )

    if catalog_codes - existing_system_codes:
        seed_currency_catalog()

    existing_codes = set(
        UserCurrency.objects
        .filter(user=user)
        .values_list("currency__code", flat=True)
    )

    settings_to_create = []

    for currency in Currency.objects.filter(is_system=True).order_by("code"):
        if currency.code in existing_codes:
            continue

        is_primary = currency.code == DEFAULT_CURRENCY_CODE and not UserCurrency.objects.filter(
            user=user,
            is_primary=True,
        ).exists()

        settings_to_create.append(
            UserCurrency(
                user=user,
                currency=currency,
                is_visible=DEFAULT_VISIBLE_BY_CODE.get(currency.code, True) or is_primary,
                is_primary=is_primary,
                is_custom=False,
                rate_to_primary=DEFAULT_RATE_BY_CODE.get(currency.code, Decimal("1.00000000")),
            )
        )

    if settings_to_create:
        UserCurrency.objects.bulk_create(settings_to_create, ignore_conflicts=True)

    if not UserCurrency.objects.filter(user=user, is_primary=True).exists():
        rub_currency = Currency.objects.filter(code=DEFAULT_CURRENCY_CODE).first()
        if rub_currency:
            UserCurrency.objects.update_or_create(
                user=user,
                currency=rub_currency,
                defaults={
                    "is_visible": True,
                    "is_primary": True,
                    "is_custom": False,
                    "rate_to_primary": Decimal("1.00000000"),
                },
            )


def get_user_currencies(user):
    ensure_user_currencies(user)
    return (
        UserCurrency.objects
        .filter(user=user)
        .select_related("currency")
        .order_by("-is_primary", "currency__code")
    )


def get_visible_user_currencies(user):
    return get_user_currencies(user).filter(is_visible=True)


def get_primary_currency(user) -> UserCurrency | None:
    return get_user_currencies(user).filter(is_primary=True).first()




def get_user_primary_currency_code(user) -> str:
    primary = get_primary_currency(user)
    return primary.code if primary else DEFAULT_CURRENCY_CODE


def get_user_default_currency_code(user) -> str:
    """Return currency selected in app settings, falling back to primary currency."""
    primary_code = get_user_primary_currency_code(user)

    try:
        from apps.users.app_settings.services import get_or_create_user_app_settings

        settings = get_or_create_user_app_settings(user)
        default_code = normalize_currency_code(settings.default_currency)
    except Exception:
        return primary_code

    user_currency = get_user_currency_by_code(user, default_code)
    if user_currency is None or not user_currency.is_visible:
        return primary_code

    return default_code


def get_user_visible_currency_codes(user) -> set[str]:
    return set(get_visible_user_currencies(user).values_list("currency__code", flat=True))


def get_user_available_currency_codes(user, *, include_hidden: bool = True) -> set[str]:
    queryset = get_user_currencies(user)
    if not include_hidden:
        queryset = queryset.filter(is_visible=True)
    return set(queryset.values_list("currency__code", flat=True))


def get_user_currency_by_code(user, code: str) -> UserCurrency | None:
    normalized_code = normalize_currency_code(code)
    if not normalized_code:
        return None
    return get_user_currencies(user).filter(currency__code=normalized_code).first()


def validate_user_currency_available(
    user,
    code: str,
    *,
    field_name: str | None = "currency",
    require_visible: bool = True,
) -> str:
    from rest_framework.exceptions import ValidationError

    normalized_code = normalize_currency_code(code)

    def _raise(message: str):
        if field_name is None:
            raise ValidationError([message])
        raise ValidationError({field_name: [message]})

    if not is_valid_currency_code(normalized_code):
        _raise("Валюта должна быть указана ISO-кодом из 3 латинских букв.")

    user_currency = get_user_currency_by_code(user, normalized_code)

    if user_currency is None:
        _raise("Валюта не добавлена в список валют пользователя.")

    if require_visible and not user_currency.is_visible:
        _raise("Скрытую валюту нельзя выбрать для новых данных.")

    return normalized_code


def build_currency_select_options(user) -> list[dict]:
    default_currency_code = get_user_default_currency_code(user)

    return [
        {
            "title": f"{item.code} · {item.display_name}",
            "value": item.code,
            "symbol": item.display_symbol,
            "isPrimary": item.is_primary,
            "isDefault": item.code == default_currency_code,
        }
        for item in get_visible_user_currencies(user)
    ]


def get_currency_usage_count(user, code: str) -> int:
    normalized_code = normalize_currency_code(code)
    account_ids = list(
        Account.objects
        .filter(user=user, currency=normalized_code)
        .values_list("id", flat=True)
    )
    transaction_count = Transaction.objects.filter(
        user=user,
        account_id__in=account_ids,
    ).count()

    return int(
        len(account_ids)
        + transaction_count
        + Budget.objects.filter(user=user, currency=normalized_code).count()
        + TransactionTemplate.objects.filter(user=user, currency=normalized_code).count()
    )


def build_currencies_summary(queryset) -> dict:
    all_items = list(queryset)
    primary = next((item for item in all_items if item.is_primary), None)

    return {
        "totalCount": len(all_items),
        "primaryCode": primary.code if primary else DEFAULT_CURRENCY_CODE,
        "hiddenCount": sum(1 for item in all_items if not item.is_visible),
    }


def parse_bool(value, *, default=None):
    if value is None:
        return default

    if isinstance(value, bool):
        return value

    normalized = str(value).strip().lower()

    if normalized in {"1", "true", "yes", "y", "on"}:
        return True

    if normalized in {"0", "false", "no", "n", "off"}:
        return False

    return default


def filter_user_currencies_queryset(queryset, request):
    params = request.query_params
    search = str(params.get("search") or "").strip()

    if search:
        queryset = queryset.filter(
            Q(currency__code__icontains=search)
            | Q(currency__name__icontains=search)
            | Q(currency__symbol__icontains=search)
            | Q(custom_name__icontains=search)
            | Q(custom_symbol__icontains=search)
        )

    is_visible = parse_bool(params.get("isVisible", params.get("is_visible")))
    if is_visible is not None:
        queryset = queryset.filter(is_visible=is_visible)

    is_custom = parse_bool(params.get("isCustom", params.get("is_custom")))
    if is_custom is not None:
        queryset = queryset.filter(is_custom=is_custom)

    only_used = parse_bool(params.get("onlyUsed", params.get("only_used")), default=False)
    if only_used:
        items = [item.pk for item in queryset if get_currency_usage_count(request.user, item.code) > 0]
        queryset = queryset.filter(pk__in=items)

    ordering = params.get("ordering")
    if ordering:
        ordering_fields = []
        for raw_field in str(ordering).split(","):
            field = raw_field.strip()
            if not field:
                continue
            desc = field.startswith("-")
            normalized = field[1:] if desc else field
            mapped = CURRENCY_SORT_FIELDS.get(normalized)
            if mapped:
                ordering_fields.append(f"-{mapped}" if desc else mapped)
        if ordering_fields:
            return queryset.order_by(*ordering_fields)

    return queryset.order_by("-is_primary", "currency__code")


def build_catalog_items(user, *, search: str = "", exclude_added: bool = False) -> list[dict]:
    ensure_user_currencies(user)
    added_codes = set(
        UserCurrency.objects
        .filter(user=user)
        .values_list("currency__code", flat=True)
    )
    normalized_search = str(search or "").strip().lower()
    items = []

    for item in CURRENCY_CATALOG:
        if exclude_added and item["code"] in added_codes:
            continue

        haystack = f"{item['code']} {item['name']} {item['symbol']}".lower()
        if normalized_search and normalized_search not in haystack:
            continue

        items.append(
            {
                "code": item["code"],
                "name": item["name"],
                "symbol": item["symbol"],
                "flagIcon": item["flagIcon"],
                "popular": bool(item.get("popular", False)),
            }
        )

    return items


@transaction.atomic
def set_primary_currency(user, user_currency: UserCurrency) -> UserCurrency:
    from apps.finance.currencies.rates import refresh_user_currency_rates

    with transaction.atomic():
        UserCurrency.objects.filter(user=user, is_primary=True).exclude(pk=user_currency.pk).update(
            is_primary=False,
        )
        user_currency.is_primary = True
        user_currency.is_visible = True
        user_currency.rate_to_primary = Decimal("1.00000000")
        user_currency.save(update_fields=["is_primary", "is_visible", "rate_to_primary", "updated_at"])

    refresh_user_currency_rates(user, force=True)
    user_currency.refresh_from_db()
    return user_currency


def validate_custom_currency_payload(*, code: str, name: str, symbol: str, exclude_id=None, user=None) -> dict:
    field_errors = {}
    normalized_code = normalize_currency_code(code)
    normalized_name = normalize_currency_text(name)
    normalized_symbol = normalize_currency_symbol(symbol)

    if not normalized_code:
        field_errors["code"] = "Код валюты не может быть пустым."
    elif not is_valid_currency_code(normalized_code):
        field_errors["code"] = "Код валюты должен состоять из 3 латинских букв."

    if not normalized_name:
        field_errors["name"] = "Название валюты не может быть пустым."
    elif len(normalized_name) > MAX_CURRENCY_NAME_LENGTH:
        field_errors["name"] = f"Название валюты не может быть длиннее {MAX_CURRENCY_NAME_LENGTH} символов."

    if not normalized_symbol:
        field_errors["symbol"] = "Символ валюты не может быть пустым."
    elif len(normalized_symbol) > MAX_CURRENCY_SYMBOL_LENGTH:
        field_errors["symbol"] = f"Символ валюты не может быть длиннее {MAX_CURRENCY_SYMBOL_LENGTH} символов."

    if normalized_code and user is not None:
        existing = UserCurrency.objects.filter(user=user, currency__code=normalized_code)
        if exclude_id:
            existing = existing.exclude(pk=exclude_id)
        if existing.exists():
            field_errors["code"] = "Валюта с таким кодом уже добавлена."

    return {
        "code": normalized_code,
        "name": normalized_name,
        "symbol": normalized_symbol,
        "fieldErrors": field_errors,
    }
