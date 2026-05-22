from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings

from apps.finance.receipt_qr import FiscalReceiptQRData, parse_receipt_qr


logger = logging.getLogger("apps")

PROVIDER_PROVERKACHEKA = "proverkacheka"
MONEY_QUANT = Decimal("0.01")

PROVERKACHEKA_SUCCESS_CODE = 1
PROVERKACHEKA_INVALID_CODE = 0
PROVERKACHEKA_PENDING_CODE = 2
PROVERKACHEKA_LIMIT_CODE = 3
PROVERKACHEKA_RETRY_LATER_CODE = 4
PROVERKACHEKA_UNKNOWN_ERROR_CODE = 5

PROVERKACHEKA_CODE_MESSAGES = {
    PROVERKACHEKA_INVALID_CODE: "Чек некорректен или не найден у провайдера.",
    PROVERKACHEKA_PENDING_CODE: "Данные чека пока не получены. Повторите запрос позже.",
    PROVERKACHEKA_LIMIT_CODE: "Превышено количество запросов к сервису проверки чеков.",
    PROVERKACHEKA_RETRY_LATER_CODE: "Сервис проверки чеков просит повторить запрос позже.",
    PROVERKACHEKA_UNKNOWN_ERROR_CODE: "Сервис проверки чеков не вернул данные чека.",
}

OPERATION_TYPE_LABELS = {
    1: "Приход",
    2: "Возврат прихода",
    3: "Расход",
    4: "Возврат расхода",
}


class ReceiptProviderError(RuntimeError):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        provider_code: int | None = None,
        field_errors: dict[str, str] | None = None,
        response_payload: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.provider_code = provider_code
        self.field_errors = field_errors or {}
        self.response_payload = response_payload or {}
        super().__init__(message)


@dataclass(frozen=True)
class ReceiptProviderRequest:
    qr_raw: str
    fiscal_drive_number: str
    fiscal_document_number: str
    fiscal_sign: str
    date_time: str
    operation_type_code: str
    total_amount: Decimal

    @classmethod
    def from_qr_data(cls, qr_data: FiscalReceiptQRData) -> "ReceiptProviderRequest":
        return cls(
            qr_raw=qr_data.canonical,
            fiscal_drive_number=qr_data.fiscal_drive_number,
            fiscal_document_number=qr_data.fiscal_document_number,
            fiscal_sign=qr_data.fiscal_sign,
            date_time=qr_data.fields["t"],
            operation_type_code=qr_data.operation_type_code,
            total_amount=qr_data.total_amount,
        )


@dataclass(frozen=True)
class ReceiptLineItem:
    name: str
    quantity: Decimal
    price: Decimal
    amount: Decimal
    raw: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "quantity": str(self.quantity),
            "price": str(self.price),
            "amount": str(self.amount),
            "raw": dict(self.raw),
        }


@dataclass(frozen=True)
class FiscalReceiptDetails:
    provider: str
    provider_code: int
    first: bool
    organization_name: str
    retail_place_address: str
    seller_inn: str
    ticket_date: str
    request_number: str
    shift_number: str
    operator: str
    operation_type_code: int | None
    operation_type_label: str
    total_amount: Decimal
    cash_total_amount: Decimal
    card_total_amount: Decimal
    fiscal_drive_number: str
    fiscal_document_number: str
    fiscal_sign: str
    items: tuple[ReceiptLineItem, ...]
    raw_json: dict[str, Any] = field(default_factory=dict)
    raw_response: dict[str, Any] = field(default_factory=dict)

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
            "provider": self.provider,
            "providerCode": self.provider_code,
            "first": self.first,
            "organizationName": self.organization_name,
            "retailPlaceAddress": self.retail_place_address,
            "sellerInn": self.seller_inn,
            "ticketDate": self.ticket_date,
            "requestNumber": self.request_number,
            "shiftNumber": self.shift_number,
            "operator": self.operator,
            "operationTypeCode": self.operation_type_code,
            "operationTypeLabel": self.operation_type_label,
            "totalAmount": str(self.total_amount),
            "cashTotalAmount": str(self.cash_total_amount),
            "cardTotalAmount": str(self.card_total_amount),
            "fiscalDriveNumber": self.fiscal_drive_number,
            "fiscalDocumentNumber": self.fiscal_document_number,
            "fiscalSign": self.fiscal_sign,
            "fiscalKey": self.fiscal_key,
            "items": [item.as_dict() for item in self.items],
            "rawJson": dict(self.raw_json),
            "rawResponse": dict(self.raw_response),
        }


class ProverkaChekaClient:
    def __init__(
        self,
        *,
        token: str | None = None,
        api_url: str | None = None,
        timeout_seconds: int | None = None,
        enabled: bool | None = None,
    ) -> None:
        self.token = token if token is not None else settings.PROVERKACHEKA_API_TOKEN
        self.api_url = api_url or settings.PROVERKACHEKA_API_URL
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else settings.PROVERKACHEKA_TIMEOUT_SECONDS
        )
        self.enabled = enabled if enabled is not None else settings.PROVERKACHEKA_ENABLED

    def fetch_by_qr_raw(self, qr_raw: str) -> FiscalReceiptDetails:
        return self.fetch_by_qr(parse_receipt_qr(qr_raw))

    def fetch_by_qr(self, qr_data: FiscalReceiptQRData) -> FiscalReceiptDetails:
        provider_request = ReceiptProviderRequest.from_qr_data(qr_data)
        payload = self._request_payload(provider_request)
        response_payload = self._post(payload)
        return normalize_proverkacheka_response(response_payload)

    def _request_payload(self, provider_request: ReceiptProviderRequest) -> dict[str, str]:
        self._ensure_configured()
        return {
            "token": self.token,
            "qrraw": provider_request.qr_raw,
        }

    def _ensure_configured(self) -> None:
        if not self.enabled:
            raise ReceiptProviderError(
                code="receipt_provider_disabled",
                message="Интеграция с сервисом проверки чеков отключена.",
            )
        if not self.token:
            raise ReceiptProviderError(
                code="receipt_provider_token_missing",
                message="Не настроен токен доступа к сервису проверки чеков.",
                field_errors={"token": "Укажите PROVERKACHEKA_API_TOKEN в .env."},
            )

    def _post(self, payload: dict[str, str]) -> dict[str, Any]:
        encoded_payload = urlencode(payload).encode("utf-8")
        request = Request(
            self.api_url,
            data=encoded_payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                response_body = response.read().decode("utf-8")
        except HTTPError as exc:
            logger.warning(
                "Receipt provider returned HTTP error. provider=%s status=%s",
                PROVIDER_PROVERKACHEKA,
                exc.code,
            )
            raise ReceiptProviderError(
                code="receipt_provider_http_error",
                message="Сервис проверки чеков вернул ошибку HTTP.",
            ) from exc
        except URLError as exc:
            logger.warning(
                "Receipt provider is unavailable. provider=%s reason=%s",
                PROVIDER_PROVERKACHEKA,
                exc.reason,
            )
            raise ReceiptProviderError(
                code="receipt_provider_unavailable",
                message="Сервис проверки чеков временно недоступен.",
            ) from exc
        except TimeoutError as exc:
            logger.warning(
                "Receipt provider request timed out. provider=%s",
                PROVIDER_PROVERKACHEKA,
            )
            raise ReceiptProviderError(
                code="receipt_provider_timeout",
                message="Сервис проверки чеков не ответил вовремя.",
            ) from exc

        try:
            decoded = json.loads(response_body)
        except json.JSONDecodeError as exc:
            raise ReceiptProviderError(
                code="receipt_provider_invalid_json",
                message="Сервис проверки чеков вернул некорректный JSON.",
            ) from exc

        if not isinstance(decoded, dict):
            raise ReceiptProviderError(
                code="receipt_provider_invalid_response",
                message="Сервис проверки чеков вернул ответ в неожиданном формате.",
            )

        return decoded


class MockReceiptProviderClient:
    def __init__(self, receipt: FiscalReceiptDetails | None = None) -> None:
        self.receipt = receipt

    def fetch_by_qr_raw(self, qr_raw: str) -> FiscalReceiptDetails:
        parse_receipt_qr(qr_raw)
        return self.fetch_by_qr(parse_receipt_qr(qr_raw))

    def fetch_by_qr(self, qr_data: FiscalReceiptQRData) -> FiscalReceiptDetails:
        if self.receipt is None:
            raise ReceiptProviderError(
                code="receipt_provider_mock_empty",
                message="Mock-провайдер чека не настроен.",
            )
        return self.receipt


def get_receipt_provider_client() -> ProverkaChekaClient:
    return ProverkaChekaClient()


def normalize_proverkacheka_response(response_payload: dict[str, Any]) -> FiscalReceiptDetails:
    provider_code = _safe_int(response_payload.get("code"))
    if provider_code != PROVERKACHEKA_SUCCESS_CODE:
        raise ReceiptProviderError(
            code=_provider_error_code(provider_code),
            message=PROVERKACHEKA_CODE_MESSAGES.get(
                provider_code,
                "Сервис проверки чеков не вернул данные чека.",
            ),
            provider_code=provider_code,
            response_payload=response_payload,
        )

    data = response_payload.get("data")
    if not isinstance(data, dict):
        raise ReceiptProviderError(
            code="receipt_provider_invalid_response",
            message="В ответе сервиса проверки чеков отсутствует блок data.",
            provider_code=provider_code,
            response_payload=response_payload,
        )

    receipt_json = data.get("json")
    if not isinstance(receipt_json, dict):
        raise ReceiptProviderError(
            code="receipt_provider_invalid_response",
            message="В ответе сервиса проверки чеков отсутствует блок data.json.",
            provider_code=provider_code,
            response_payload=response_payload,
        )

    operation_type_code = _safe_int(receipt_json.get("operationType"))
    items = tuple(_normalize_item(item) for item in receipt_json.get("items") or [])

    return FiscalReceiptDetails(
        provider=PROVIDER_PROVERKACHEKA,
        provider_code=provider_code,
        first=str(response_payload.get("first", "0")) == "1",
        organization_name=str(receipt_json.get("user") or ""),
        retail_place_address=str(
            receipt_json.get("retailPlaceAddres")
            or receipt_json.get("retailPlaceAddress")
            or ""
        ),
        seller_inn=str(receipt_json.get("userInn") or ""),
        ticket_date=str(receipt_json.get("ticketDate") or ""),
        request_number=str(receipt_json.get("requestNumber") or ""),
        shift_number=str(receipt_json.get("shiftNumber") or ""),
        operator=str(receipt_json.get("operator") or ""),
        operation_type_code=operation_type_code,
        operation_type_label=OPERATION_TYPE_LABELS.get(operation_type_code, ""),
        total_amount=_kopecks_to_money(receipt_json.get("totalSum")),
        cash_total_amount=_kopecks_to_money(receipt_json.get("cashTotalSum")),
        card_total_amount=_kopecks_to_money(receipt_json.get("ecashTotalSum")),
        fiscal_drive_number=str(receipt_json.get("fiscalDriveNumber") or ""),
        fiscal_document_number=str(receipt_json.get("fiscalDocumentNumber") or ""),
        fiscal_sign=str(receipt_json.get("fiscalSign") or ""),
        items=items,
        raw_json=receipt_json,
        raw_response=response_payload,
    )


def _normalize_item(item: Any) -> ReceiptLineItem:
    if not isinstance(item, dict):
        item = {}
    return ReceiptLineItem(
        name=str(item.get("name") or ""),
        quantity=_to_decimal(item.get("quantity"), default="0"),
        price=_kopecks_to_money(item.get("price")),
        amount=_kopecks_to_money(item.get("sum")),
        raw=dict(item),
    )


def _provider_error_code(provider_code: int | None) -> str:
    return {
        PROVERKACHEKA_INVALID_CODE: "receipt_provider_invalid_receipt",
        PROVERKACHEKA_PENDING_CODE: "receipt_provider_pending",
        PROVERKACHEKA_LIMIT_CODE: "receipt_provider_limit_exceeded",
        PROVERKACHEKA_RETRY_LATER_CODE: "receipt_provider_retry_later",
        PROVERKACHEKA_UNKNOWN_ERROR_CODE: "receipt_provider_no_data",
    }.get(provider_code, "receipt_provider_no_data")


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_decimal(value: Any, *, default: str = "0") -> Decimal:
    try:
        return Decimal(str(value if value is not None else default))
    except (InvalidOperation, ValueError):
        return Decimal(default)


def _kopecks_to_money(value: Any) -> Decimal:
    return (_to_decimal(value) / Decimal("100")).quantize(
        MONEY_QUANT,
        rounding=ROUND_HALF_UP,
    )
