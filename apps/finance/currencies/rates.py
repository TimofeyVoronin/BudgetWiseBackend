from __future__ import annotations

import json
import logging
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from django.conf import settings
from django.core.cache import cache

from apps.finance.models import UserCurrency


logger = logging.getLogger(__name__)

RUB_CODE = "RUB"
USD_CODE = "USD"
RATE_DECIMAL_PLACES = Decimal("0.00000001")
MIN_RATE_TO_PRIMARY = Decimal("0.00000001")

CRYPTO_COIN_IDS_BY_CODE = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
}

STATIC_RUB_VALUE_BY_CODE = {
    "RUB": Decimal("1.00000000"),
    "USD": Decimal("90.00000000"),
    "EUR": Decimal("98.00000000"),
    "KZT": Decimal("0.18000000"),
    "CNY": Decimal("12.50000000"),
    "THB": Decimal("2.70000000"),
    "BYN": Decimal("30.00000000"),
    "GBP": Decimal("115.00000000"),
    "BTC": Decimal("9000000.00000000"),
    "ETH": Decimal("300000.00000000"),
}


def refresh_user_currency_rates(user, *, force: bool = False) -> None:
    """Refresh user currency rates against the current primary currency.

    The API contract uses rateToPrimary as: 1 unit of selected currency equals
    N units of the user's primary currency. Rates are refreshed on demand and
    cached shortly to keep the currencies page fast and stable.
    """

    if not getattr(settings, "CURRENCY_RATES_ENABLED", True):
        return

    user_currencies = list(
        UserCurrency.objects
        .filter(user=user)
        .select_related("currency")
        .order_by("-is_primary", "currency__code")
    )
    if not user_currencies:
        return

    primary = next((item for item in user_currencies if item.is_primary), None)
    if primary is None:
        return

    codes = {item.code for item in user_currencies if not item.is_custom}
    codes.add(primary.code)

    rate_to_primary = build_rate_to_primary_map(
        codes=codes,
        primary_code=primary.code,
        force=force,
    )

    for user_currency in user_currencies:
        if user_currency.is_custom:
            continue

        rate = rate_to_primary.get(user_currency.code)
        if rate is None:
            continue

        if user_currency.rate_to_primary != rate:
            user_currency.rate_to_primary = rate
            user_currency.save(update_fields=["rate_to_primary", "updated_at"])


def build_rate_to_primary_map(
    *,
    codes: set[str],
    primary_code: str,
    force: bool = False,
) -> dict[str, Decimal]:
    normalized_codes = {str(code or "").upper() for code in codes if code}
    normalized_primary = str(primary_code or RUB_CODE).upper()
    normalized_codes.add(normalized_primary)

    rub_values = get_rub_values_for_codes(normalized_codes, force=force)
    primary_rub_value = rub_values.get(normalized_primary)
    if not primary_rub_value or primary_rub_value <= 0:
        primary_rub_value = STATIC_RUB_VALUE_BY_CODE.get(normalized_primary, Decimal("1.00000000"))

    result = {}
    for code in normalized_codes:
        if code == normalized_primary:
            result[code] = Decimal("1.00000000")
            continue

        rub_value = rub_values.get(code)
        if not rub_value or rub_value <= 0:
            continue

        result[code] = quantize_rate(rub_value / primary_rub_value)

    return result


def get_rub_values_for_codes(codes: set[str], *, force: bool = False) -> dict[str, Decimal]:
    normalized_codes = {str(code or "").upper() for code in codes if code}
    normalized_codes.add(RUB_CODE)

    cache_key = "finance:currency-rates:rub-values"
    failure_key = "finance:currency-rates:failure"

    if not force:
        cached = cache.get(cache_key)
        if cached:
            return {key: Decimal(value) for key, value in cached.items()}

        if cache.get(failure_key):
            return build_static_rub_values(normalized_codes)

    rub_values = build_static_rub_values(normalized_codes)

    try:
        rub_values.update(fetch_cbr_rub_values(normalized_codes))
        rub_values.update(fetch_crypto_rub_values(normalized_codes))
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, ElementTree.ParseError, json.JSONDecodeError) as exc:
        logger.warning("Currency rates refresh failed: %s", exc)
        cache.set(
            failure_key,
            True,
            timeout=getattr(settings, "CURRENCY_RATES_FAILURE_CACHE_SECONDS", 300),
        )
    else:
        cache.set(
            cache_key,
            {key: str(value) for key, value in rub_values.items()},
            timeout=getattr(settings, "CURRENCY_RATES_CACHE_SECONDS", 900),
        )
        cache.delete(failure_key)

    return rub_values


def build_static_rub_values(codes: set[str]) -> dict[str, Decimal]:
    return {
        code: STATIC_RUB_VALUE_BY_CODE[code]
        for code in codes
        if code in STATIC_RUB_VALUE_BY_CODE
    }


def fetch_cbr_rub_values(codes: set[str]) -> dict[str, Decimal]:
    fiat_codes = {
        code
        for code in codes
        if code not in CRYPTO_COIN_IDS_BY_CODE and code != RUB_CODE
    }
    if not fiat_codes:
        return {RUB_CODE: Decimal("1.00000000")}

    content = fetch_url(getattr(settings, "CURRENCY_FIAT_RATES_URL"))
    root = ElementTree.fromstring(content)
    values = {RUB_CODE: Decimal("1.00000000")}

    for valute in root.findall("Valute"):
        char_code = (valute.findtext("CharCode") or "").strip().upper()
        if char_code not in fiat_codes:
            continue

        nominal = parse_decimal(valute.findtext("Nominal"))
        value = parse_decimal(valute.findtext("Value"))
        if nominal <= 0 or value <= 0:
            continue

        values[char_code] = quantize_rate(value / nominal)

    return values


def fetch_crypto_rub_values(codes: set[str]) -> dict[str, Decimal]:
    crypto_codes = [code for code in codes if code in CRYPTO_COIN_IDS_BY_CODE]
    if not crypto_codes:
        return {}

    coin_ids = [CRYPTO_COIN_IDS_BY_CODE[code] for code in crypto_codes]
    url = build_url(
        getattr(settings, "CURRENCY_CRYPTO_RATES_URL"),
        {
            "ids": ",".join(coin_ids),
            "vs_currencies": "rub",
        },
    )
    payload = json.loads(fetch_url(url).decode("utf-8"))
    values = {}

    code_by_coin_id = {
        coin_id: code
        for code, coin_id in CRYPTO_COIN_IDS_BY_CODE.items()
        if code in crypto_codes
    }
    for coin_id, code in code_by_coin_id.items():
        raw_value = payload.get(coin_id, {}).get("rub")
        if raw_value in (None, ""):
            continue
        value = parse_decimal(raw_value)
        if value > 0:
            values[code] = quantize_rate(value)

    return values


def fetch_url(url: str) -> bytes:
    request = Request(
        url,
        headers={
            "User-Agent": "BudgetWiseBackend/1.0 (+https://budgetwise.local)",
            "Accept": "application/json, application/xml, text/xml, */*",
        },
    )
    timeout = getattr(settings, "CURRENCY_RATES_TIMEOUT_SECONDS", 2.0)
    with urlopen(request, timeout=timeout) as response:
        return response.read()


def build_url(base_url: str, query_params: dict[str, str]) -> str:
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}{urlencode(query_params)}"


def parse_decimal(value) -> Decimal:
    try:
        return Decimal(str(value or "").strip().replace(",", "."))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid decimal value: {value!r}") from exc


def quantize_rate(value: Decimal) -> Decimal:
    if value <= 0:
        return MIN_RATE_TO_PRIMARY

    quantized = value.quantize(RATE_DECIMAL_PLACES, rounding=ROUND_HALF_UP)
    if quantized <= 0:
        return MIN_RATE_TO_PRIMARY

    return quantized
