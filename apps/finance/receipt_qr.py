from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from hashlib import sha256
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit

from django.utils import timezone


RECEIPT_QR_REQUIRED_FIELDS = {"t", "s", "fn", "i", "fp", "n"}
RECEIPT_QR_DATE_FORMATS = (
    # Check the shorter fiscal format first. Python strptime can
    # otherwise parse YYYYMMDDTHHMM as HH:M:S with %H%M%S.
    "%Y%m%dT%H%M",
    "%Y%m%dT%H%M%S",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%dT%H:%M:%S",
)

RECEIPT_OPERATION_INCOME = "income"
RECEIPT_OPERATION_INCOME_RETURN = "income_return"
RECEIPT_OPERATION_EXPENSE = "expense"
RECEIPT_OPERATION_EXPENSE_RETURN = "expense_return"

RECEIPT_OPERATION_TYPES = {
    "1": RECEIPT_OPERATION_INCOME,
    "2": RECEIPT_OPERATION_INCOME_RETURN,
    "3": RECEIPT_OPERATION_EXPENSE,
    "4": RECEIPT_OPERATION_EXPENSE_RETURN,
}

MONEY_QUANT = Decimal("0.01")


class ReceiptQRParseError(ValueError):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        field_errors: dict[str, str] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.field_errors = field_errors or {}
        super().__init__(message)


@dataclass(frozen=True)
class FiscalReceiptQRData:
    raw: str
    raw_hash: str
    canonical: str
    date_time: datetime
    total_amount: Decimal
    fiscal_drive_number: str
    fiscal_document_number: str
    fiscal_sign: str
    operation_type_code: str
    operation_type: str
    fields: dict[str, str] = field(default_factory=dict)

    @property
    def fiscal_key(self) -> str:
        return ":".join(
            [
                self.fiscal_drive_number,
                self.fiscal_document_number,
                self.fiscal_sign,
            ]
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "raw": self.raw,
            "rawHash": self.raw_hash,
            "canonical": self.canonical,
            "dateTime": self.date_time.isoformat(),
            "totalAmount": str(self.total_amount),
            "fiscalDriveNumber": self.fiscal_drive_number,
            "fiscalDocumentNumber": self.fiscal_document_number,
            "fiscalSign": self.fiscal_sign,
            "operationTypeCode": self.operation_type_code,
            "operationType": self.operation_type,
            "fiscalKey": self.fiscal_key,
            "fields": dict(self.fields),
        }


def parse_receipt_qr(raw_qr: str) -> FiscalReceiptQRData:
    raw = _normalize_raw_qr(raw_qr)
    fields = _parse_query_fields(raw)
    _validate_required_fields(fields)

    date_time = _parse_receipt_datetime(fields["t"])
    total_amount = _parse_total_amount(fields["s"])
    operation_type_code = fields["n"]
    operation_type = _parse_operation_type(operation_type_code)

    fiscal_drive_number = _require_digits(
        fields["fn"],
        field="fn",
        message="ФН должен содержать только цифры.",
    )
    fiscal_document_number = _require_digits(
        fields["i"],
        field="i",
        message="Номер фискального документа должен содержать только цифры.",
    )
    fiscal_sign = _require_digits(
        fields["fp"],
        field="fp",
        message="Фискальный признак должен содержать только цифры.",
    )

    canonical = _build_canonical_qr(fields)

    return FiscalReceiptQRData(
        raw=raw,
        raw_hash=sha256(canonical.encode("utf-8")).hexdigest(),
        canonical=canonical,
        date_time=date_time,
        total_amount=total_amount,
        fiscal_drive_number=fiscal_drive_number,
        fiscal_document_number=fiscal_document_number,
        fiscal_sign=fiscal_sign,
        operation_type_code=operation_type_code,
        operation_type=operation_type,
        fields=fields,
    )


def build_receipt_deduplication_key(parsed_qr: FiscalReceiptQRData) -> str:
    return f"receipt:{parsed_qr.fiscal_key}"


def _normalize_raw_qr(raw_qr: str) -> str:
    if not isinstance(raw_qr, str):
        raise ReceiptQRParseError(
            code="receipt_qr_invalid_type",
            message="QR-код чека должен быть строкой.",
            field_errors={"qrRaw": "QR-код чека должен быть строкой."},
        )

    raw = raw_qr.strip()
    if not raw:
        raise ReceiptQRParseError(
            code="receipt_qr_empty",
            message="QR-код чека не должен быть пустым.",
            field_errors={"qrRaw": "QR-код чека не должен быть пустым."},
        )

    # Some scanner libraries return a full URL with the fiscal query string.
    split = urlsplit(raw)
    if split.query:
        raw = split.query

    return raw


def _parse_query_fields(raw: str) -> dict[str, str]:
    if "=" not in raw:
        raise ReceiptQRParseError(
            code="receipt_qr_invalid_format",
            message="QR-код чека должен содержать параметры в формате t=...&s=...&fn=... .",
            field_errors={"qrRaw": "Некорректный формат QR-кода чека."},
        )

    pairs = parse_qsl(raw, keep_blank_values=True)
    fields: dict[str, str] = {}

    for key, value in pairs:
        normalized_key = key.strip().lower()
        if not normalized_key:
            continue
        fields[normalized_key] = value.strip()

    if not fields:
        raise ReceiptQRParseError(
            code="receipt_qr_invalid_format",
            message="QR-код чека должен содержать параметры в формате t=...&s=...&fn=... .",
            field_errors={"qrRaw": "Некорректный формат QR-кода чека."},
        )

    return fields


def _validate_required_fields(fields: dict[str, str]) -> None:
    missing = sorted(
        field
        for field in RECEIPT_QR_REQUIRED_FIELDS
        if not fields.get(field)
    )
    if missing:
        raise ReceiptQRParseError(
            code="receipt_qr_missing_fields",
            message="В QR-коде чека отсутствуют обязательные поля.",
            field_errors={
                field: "Обязательное поле отсутствует в QR-коде чека."
                for field in missing
            },
        )


def _parse_receipt_datetime(value: str) -> datetime:
    for date_format in RECEIPT_QR_DATE_FORMATS:
        try:
            parsed = datetime.strptime(value, date_format)
            return timezone.make_aware(parsed, timezone.get_current_timezone())
        except ValueError:
            continue

    raise ReceiptQRParseError(
        code="receipt_qr_invalid_datetime",
        message="Некорректная дата и время чека.",
        field_errors={"t": "Дата должна быть в формате YYYYMMDDTHHMM или ISO."},
    )


def _parse_total_amount(value: str) -> Decimal:
    normalized_value = value.replace(",", ".")
    try:
        amount = Decimal(normalized_value).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        raise ReceiptQRParseError(
            code="receipt_qr_invalid_amount",
            message="Некорректная сумма чека.",
            field_errors={"s": "Сумма должна быть числом больше нуля."},
        )

    if amount <= 0:
        raise ReceiptQRParseError(
            code="receipt_qr_invalid_amount",
            message="Некорректная сумма чека.",
            field_errors={"s": "Сумма должна быть больше нуля."},
        )

    return amount


def _parse_operation_type(value: str) -> str:
    operation_type = RECEIPT_OPERATION_TYPES.get(value)
    if operation_type is None:
        raise ReceiptQRParseError(
            code="receipt_qr_invalid_operation_type",
            message="Некорректный тип операции в QR-коде чека.",
            field_errors={"n": "Поддерживаются типы операции 1, 2, 3 и 4."},
        )
    return operation_type


def _require_digits(value: str, *, field: str, message: str) -> str:
    if not value.isdigit():
        raise ReceiptQRParseError(
            code="receipt_qr_invalid_fiscal_field",
            message="Некорректные фискальные данные чека.",
            field_errors={field: message},
        )
    return value


def _build_canonical_qr(fields: dict[str, str]) -> str:
    return urlencode(sorted(fields.items()))
