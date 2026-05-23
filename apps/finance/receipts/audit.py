from __future__ import annotations

import logging
from typing import Any

from apps.finance.models import Receipt, ReceiptAuditAction, ReceiptAuditLog, ReceiptAuditStatus

logger = logging.getLogger("apps")


def log_receipt_audit_event(
    *,
    receipt: Receipt,
    action: str,
    status: str = ReceiptAuditStatus.SUCCESS,
    message: str = "",
    metadata: dict[str, Any] | None = None,
) -> ReceiptAuditLog:
    """
    Store a durable audit event for a receipt import workflow.

    The model keeps who performed the action through receipt.user, when the
    action happened through created_at, and from which receipt/QR/fiscal key it
    originated. A short application log is written as well for operational
    diagnostics.
    """

    metadata = metadata or {}
    audit_log = ReceiptAuditLog.objects.create(
        user=receipt.user,
        receipt=receipt,
        action=action,
        status=status,
        message=message,
        qr_raw_hash=receipt.raw_hash,
        fiscal_key=receipt.fiscal_key,
        provider_name=receipt.provider_name,
        metadata=metadata,
    )

    log_extra = {
        "receipt_id": receipt.id,
        "user_id": receipt.user_id,
        "action": action,
        "status": status,
        "fiscal_key": receipt.fiscal_key,
    }
    if status == ReceiptAuditStatus.ERROR:
        logger.warning("Receipt audit event recorded as error.", extra=log_extra)
    elif status == ReceiptAuditStatus.WARNING:
        logger.info("Receipt audit event recorded as warning.", extra=log_extra)
    else:
        logger.info("Receipt audit event recorded.", extra=log_extra)

    return audit_log


def log_receipt_import_failed(
    *,
    receipt: Receipt,
    code: str,
    message: str,
    field_errors: dict[str, Any] | None = None,
) -> ReceiptAuditLog:
    return log_receipt_audit_event(
        receipt=receipt,
        action=ReceiptAuditAction.IMPORT_FAILED,
        status=ReceiptAuditStatus.ERROR,
        message=message,
        metadata={
            "code": code,
            "fieldErrors": field_errors or {},
        },
    )
