from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.finance.models import Receipt, ReceiptAuditAction, ReceiptAuditStatus, ReceiptStatus
from apps.finance.receipts.provider import FiscalReceiptDetails
from apps.finance.receipts.qr import FiscalReceiptQRData, parse_receipt_qr


class ReceiptDuplicateError(ValueError):
    def __init__(self, *, receipt: Receipt, message: str | None = None) -> None:
        self.receipt = receipt
        super().__init__(message or "Чек уже был импортирован.")


@dataclass(frozen=True)
class ReceiptDuplicateCheckResult:
    is_duplicate: bool
    existing_receipt: Receipt | None
    deduplication_key: str
    fiscal_key: str


@dataclass(frozen=True)
class ReceiptRegistrationResult:
    receipt: Receipt
    created: bool
    is_duplicate: bool


def build_receipt_import_deduplication_key(qr_data: FiscalReceiptQRData) -> str:
    """
    Build a stable user-scoped key from the fiscal receipt identity.

    The key intentionally includes date, amount, FN, FD and FP. This follows the
    product requirement for duplicate detection and still keeps the short
    `fiscal_key` separately for searching/debugging.
    """

    receipt_moment = timezone.localtime(qr_data.date_time).strftime("%Y%m%dT%H%M%S")
    amount = qr_data.total_amount.quantize(Decimal("0.01"))
    return ":".join(
        [
            "receipt",
            receipt_moment,
            str(amount),
            qr_data.fiscal_drive_number,
            qr_data.fiscal_document_number,
            qr_data.fiscal_sign,
        ]
    )


def check_receipt_duplicate(user, qr_data: FiscalReceiptQRData) -> ReceiptDuplicateCheckResult:
    deduplication_key = build_receipt_import_deduplication_key(qr_data)
    existing_receipt = (
        Receipt.objects.filter(user=user, deduplication_key=deduplication_key)
        .order_by("id")
        .first()
    )

    return ReceiptDuplicateCheckResult(
        is_duplicate=existing_receipt is not None,
        existing_receipt=existing_receipt,
        deduplication_key=deduplication_key,
        fiscal_key=qr_data.fiscal_key,
    )


def ensure_receipt_not_duplicate(user, qr_data: FiscalReceiptQRData) -> None:
    duplicate_check = check_receipt_duplicate(user, qr_data)
    if duplicate_check.existing_receipt is not None:
        raise ReceiptDuplicateError(receipt=duplicate_check.existing_receipt)


def register_receipt_from_qr(
    *,
    user,
    qr_raw: str | None = None,
    qr_data: FiscalReceiptQRData | None = None,
    provider_details: FiscalReceiptDetails | None = None,
    status: str = ReceiptStatus.PARSED,
) -> ReceiptRegistrationResult:
    if qr_data is None:
        if qr_raw is None:
            raise ValueError("qr_raw or qr_data is required.")
        qr_data = parse_receipt_qr(qr_raw)

    duplicate_check = check_receipt_duplicate(user, qr_data)
    if duplicate_check.existing_receipt is not None:
        from apps.finance.receipts.audit import log_receipt_audit_event

        log_receipt_audit_event(
            receipt=duplicate_check.existing_receipt,
            action=ReceiptAuditAction.DUPLICATE_DETECTED,
            status=ReceiptAuditStatus.WARNING,
            message="Повторная попытка импорта уже зарегистрированного чека.",
            metadata={
                "deduplicationKey": duplicate_check.deduplication_key,
                "fiscalKey": duplicate_check.fiscal_key,
            },
        )
        return ReceiptRegistrationResult(
            receipt=duplicate_check.existing_receipt,
            created=False,
            is_duplicate=True,
        )

    receipt_kwargs = _receipt_kwargs_from_qr(
        user=user,
        qr_data=qr_data,
        deduplication_key=duplicate_check.deduplication_key,
        provider_details=provider_details,
        status=status,
    )

    try:
        with transaction.atomic():
            receipt = Receipt.objects.create(**receipt_kwargs)
    except IntegrityError:
        # Another request imported the same receipt between the duplicate check
        # and insert. Return the existing row instead of leaking a 500.
        existing_receipt = Receipt.objects.get(
            user=user,
            deduplication_key=duplicate_check.deduplication_key,
        )
        from apps.finance.receipts.audit import log_receipt_audit_event

        log_receipt_audit_event(
            receipt=existing_receipt,
            action=ReceiptAuditAction.DUPLICATE_DETECTED,
            status=ReceiptAuditStatus.WARNING,
            message="Повторная попытка импорта уже зарегистрированного чека.",
            metadata={
                "deduplicationKey": duplicate_check.deduplication_key,
                "fiscalKey": duplicate_check.fiscal_key,
                "raceConditionHandled": True,
            },
        )
        return ReceiptRegistrationResult(
            receipt=existing_receipt,
            created=False,
            is_duplicate=True,
        )

    from apps.finance.receipts.audit import log_receipt_audit_event

    log_receipt_audit_event(
        receipt=receipt,
        action=(
            ReceiptAuditAction.PROVIDER_FETCH_SUCCESS
            if provider_details is not None
            else ReceiptAuditAction.QR_PARSED
        ),
        status=ReceiptAuditStatus.SUCCESS,
        message=(
            "Чек получен от внешнего провайдера."
            if provider_details is not None
            else "QR-код чека распознан и зарегистрирован."
        ),
        metadata={
            "receiptStatus": receipt.status,
            "providerCode": receipt.provider_code,
            "totalAmount": str(receipt.total_amount),
        },
    )

    if provider_details is not None:
        from apps.finance.receipts.item_mapper import map_receipt_details_to_items

        created_items = map_receipt_details_to_items(receipt, provider_details)
        log_receipt_audit_event(
            receipt=receipt,
            action=ReceiptAuditAction.ITEMS_MAPPED,
            status=ReceiptAuditStatus.SUCCESS,
            message="Позиции чека сопоставлены с внутренними сущностями.",
            metadata={"itemsCount": len(created_items)},
        )

    return ReceiptRegistrationResult(
        receipt=receipt,
        created=True,
        is_duplicate=False,
    )


def update_receipt_from_provider_details(
    *,
    receipt: Receipt,
    provider_details: FiscalReceiptDetails,
    status: str = ReceiptStatus.FETCHED,
) -> list:
    """Update an existing parsed receipt with provider data and remap items."""

    receipt.status = status
    receipt.provider_name = provider_details.provider
    receipt.provider_code = provider_details.provider_code
    receipt.store_name = provider_details.organization_name
    receipt.seller_inn = provider_details.seller_inn
    receipt.provider_payload = dict(provider_details.raw_response)
    receipt.total_amount = provider_details.total_amount or receipt.total_amount
    receipt.save(
        update_fields=[
            "status",
            "provider_name",
            "provider_code",
            "store_name",
            "seller_inn",
            "provider_payload",
            "total_amount",
            "updated_at",
        ]
    )

    from apps.finance.receipts.audit import log_receipt_audit_event
    from apps.finance.receipts.item_mapper import map_receipt_details_to_items

    log_receipt_audit_event(
        receipt=receipt,
        action=ReceiptAuditAction.PROVIDER_FETCH_SUCCESS,
        status=ReceiptAuditStatus.SUCCESS,
        message="Существующий чек обновлён данными внешнего провайдера.",
        metadata={
            "receiptStatus": receipt.status,
            "providerCode": receipt.provider_code,
            "totalAmount": str(receipt.total_amount),
        },
    )

    created_items = map_receipt_details_to_items(receipt, provider_details)
    log_receipt_audit_event(
        receipt=receipt,
        action=ReceiptAuditAction.ITEMS_MAPPED,
        status=ReceiptAuditStatus.SUCCESS,
        message="Позиции существующего чека сопоставлены с внутренними сущностями.",
        metadata={"itemsCount": len(created_items)},
    )

    return created_items


def _receipt_kwargs_from_qr(
    *,
    user,
    qr_data: FiscalReceiptQRData,
    deduplication_key: str,
    provider_details: FiscalReceiptDetails | None,
    status: str,
) -> dict[str, Any]:
    provider_payload: dict[str, Any] = {}
    provider_name = ""
    provider_code = None
    store_name = ""
    seller_inn = ""

    if provider_details is not None:
        provider_payload = dict(provider_details.raw_response)
        provider_name = provider_details.provider
        provider_code = provider_details.provider_code
        store_name = provider_details.organization_name
        seller_inn = provider_details.seller_inn

    return {
        "user": user,
        "qr_raw": qr_data.canonical,
        "raw_hash": qr_data.raw_hash,
        "deduplication_key": deduplication_key,
        "fiscal_key": qr_data.fiscal_key,
        "fiscal_drive_number": qr_data.fiscal_drive_number,
        "fiscal_document_number": qr_data.fiscal_document_number,
        "fiscal_sign": qr_data.fiscal_sign,
        "operation_type_code": qr_data.operation_type_code,
        "operation_type": qr_data.operation_type,
        "receipt_datetime": qr_data.date_time,
        "total_amount": qr_data.total_amount,
        "status": status,
        "provider_name": provider_name,
        "provider_code": provider_code,
        "store_name": store_name,
        "seller_inn": seller_inn,
        "provider_payload": provider_payload,
    }
