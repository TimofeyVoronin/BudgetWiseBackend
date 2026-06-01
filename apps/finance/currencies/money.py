from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Mapping

from rest_framework import serializers
from rest_framework.exceptions import ValidationError

MONEY_DECIMAL_PLACES = Decimal("0.01")
MONEY_ZERO = Decimal("0.00")
DEFAULT_MONEY_CURRENCY = "RUB"


@dataclass(frozen=True)
class MoneyAmount:
    """Universal DTO for API money values.

    The frontend contract for converted money values is intentionally small:
    `{amount: number, currency: string}`. The backend keeps Decimal internally
    and converts to a JSON number only at the API boundary.
    """

    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "amount", normalize_decimal(self.amount))
        object.__setattr__(self, "currency", normalize_money_currency(self.currency))

    def quantized(self) -> "MoneyAmount":
        return MoneyAmount(
            amount=quantize_money(self.amount),
            currency=self.currency,
        )

    def as_payload(self) -> dict:
        return {
            "amount": float(self.amount),
            "currency": self.currency,
        }


class MoneyAmountSerializer(serializers.Serializer):
    amount = serializers.FloatField(
        help_text="Сумма в выбранной валюте отображения.",
    )
    currency = serializers.CharField(
        max_length=3,
        help_text="ISO-код валюты суммы, например RUB, USD или EUR.",
    )


def normalize_money_currency(currency: str | None) -> str:
    normalized = str(currency or DEFAULT_MONEY_CURRENCY).strip().upper()
    return normalized or DEFAULT_MONEY_CURRENCY


def normalize_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value

    try:
        return Decimal(str(value if value is not None else "0").replace(",", "."))
    except (InvalidOperation, ValueError) as exc:
        raise ValidationError({"amount": ["Некорректная сумма."]}) from exc


def quantize_money(value: Decimal) -> Decimal:
    return normalize_decimal(value).quantize(MONEY_DECIMAL_PLACES, rounding=ROUND_HALF_UP)


def build_money_amount(
    amount,
    *,
    currency: str | None,
    quantize: bool = True,
) -> MoneyAmount:
    normalized_amount = normalize_decimal(amount)
    if quantize:
        normalized_amount = quantize_money(normalized_amount)

    return MoneyAmount(
        amount=normalized_amount,
        currency=normalize_money_currency(currency),
    )


def build_money_payload(
    amount,
    *,
    currency: str | None,
    quantize: bool = True,
) -> dict:
    return build_money_amount(
        amount,
        currency=currency,
        quantize=quantize,
    ).as_payload()


def build_zero_money_payload(*, currency: str | None) -> dict:
    return build_money_payload(MONEY_ZERO, currency=currency)


def build_money_payload_map(
    values: Mapping[str, object],
    *,
    currency: str | None,
    quantize: bool = True,
) -> dict[str, dict]:
    return {
        key: build_money_payload(value, currency=currency, quantize=quantize)
        for key, value in values.items()
    }


def parse_money_payload(
    payload: Mapping[str, object],
    *,
    default_currency: str | None = None,
) -> MoneyAmount:
    if not isinstance(payload, Mapping):
        raise ValidationError({"amount": ["Некорректный формат денежной суммы."]})

    amount = payload.get("amount", MONEY_ZERO)
    currency = payload.get("currency") or default_currency

    return build_money_amount(amount, currency=currency)
