from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from django.db import transaction as db_transaction
from django.db.models import F
from django.utils import timezone

from apps.finance.accounting import get_transaction_balance_delta
from apps.finance.models import (
    Account,
    Category,
    PlannedStatus,
    PlannedTransaction,
    Transaction,
    TransactionType,
)


logger = logging.getLogger(__name__)

PLANNED_ERROR_ACCOUNT_INACTIVE = "ACCOUNT_INACTIVE"
PLANNED_ERROR_ACCOUNT_ARCHIVED = "ACCOUNT_ARCHIVED"
PLANNED_ERROR_CATEGORY_INACTIVE = "CATEGORY_INACTIVE"
PLANNED_ERROR_CATEGORY_ARCHIVED = "CATEGORY_ARCHIVED"
PLANNED_ERROR_CATEGORY_TYPE_MISMATCH = "CATEGORY_TYPE_MISMATCH"
PLANNED_ERROR_INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
PLANNED_ERROR_NOT_CONVERTIBLE = "PLANNED_NOT_CONVERTIBLE"
PLANNED_ERROR_UNEXPECTED = "UNEXPECTED_ERROR"

PLANNED_CONVERSION_CONVERTED = "converted"
PLANNED_CONVERSION_FAILED = "failed"
PLANNED_CONVERSION_SKIPPED = "skipped"

CONVERTIBLE_PLANNED_STATUSES = {
    PlannedStatus.PENDING,
    PlannedStatus.CONFIRMED,
    PlannedStatus.OVERDUE,
}


class PlannedConversionError(Exception):
    def __init__(self, *, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass
class PlannedConversionResult:
    planned: PlannedTransaction
    transaction: Transaction | None
    status: str
    message: str = ""
    error_code: str = ""

    @property
    def planned_id(self) -> int:
        return self.planned.pk

    @property
    def transaction_id(self) -> int | None:
        return self.transaction.pk if self.transaction else self.planned.converted_transaction_id


@dataclass
class PlannedRunItem:
    planned_id: int
    planned_date: date | None
    status: str
    message: str = ""
    transaction_id: int | None = None
    error_code: str = ""


@dataclass
class PlannedRunSummary:
    processed_count: int = 0
    converted_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    items: list[PlannedRunItem] = field(default_factory=list)

    def add_item(self, item: PlannedRunItem) -> None:
        self.items.append(item)

        if item.status == PLANNED_CONVERSION_CONVERTED:
            self.converted_count += 1

        elif item.status == PLANNED_CONVERSION_FAILED:
            self.failed_count += 1

        elif item.status == PLANNED_CONVERSION_SKIPPED:
            self.skipped_count += 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "processed_count": self.processed_count,
            "converted_count": self.converted_count,
            "failed_count": self.failed_count,
            "skipped_count": self.skipped_count,
            "items": [
                {
                    "planned_id": item.planned_id,
                    "planned_date": (
                        item.planned_date.isoformat()
                        if item.planned_date
                        else None
                    ),
                    "status": item.status,
                    "message": item.message,
                    "transaction_id": item.transaction_id,
                    "error_code": item.error_code,
                }
                for item in self.items
            ],
        }


def run_due_planned_transactions(
    *,
    run_date: date | None = None,
    limit: int | None = None,
    dry_run: bool = False,
) -> PlannedRunSummary:
    """Convert due planned transactions into ordinary transactions.

    This function is intentionally independent from Celery. It can be called by
    a management command, cron job, Celery Beat task or a different scheduler.
    """
    if run_date is None:
        run_date = timezone.localdate()

    queryset = (
        PlannedTransaction.objects
        .filter(
            status__in=[
                PlannedStatus.PENDING,
                PlannedStatus.CONFIRMED,
            ],
            planned_date__lte=run_date,
        )
        .order_by("planned_date", "id")
    )

    if limit is not None:
        queryset = queryset[:limit]

    planned_ids = list(queryset.values_list("id", flat=True))

    if dry_run:
        return _build_dry_run_summary(
            planned_ids=planned_ids,
            run_date=run_date,
        )

    summary = PlannedRunSummary(processed_count=len(planned_ids))

    for planned_id in planned_ids:
        try:
            result = convert_planned_transaction(
                planned_id=planned_id,
                operation_date=run_date,
                mark_overdue_on_failure=True,
            )
            summary.add_item(
                PlannedRunItem(
                    planned_id=result.planned_id,
                    planned_date=result.planned.planned_date,
                    status=result.status,
                    message=result.message,
                    transaction_id=result.transaction_id,
                    error_code=result.error_code,
                )
            )
        except PlannedConversionError as exc:
            summary.add_item(
                PlannedRunItem(
                    planned_id=planned_id,
                    planned_date=None,
                    status=PLANNED_CONVERSION_FAILED,
                    message=exc.message,
                    error_code=exc.code,
                )
            )
        except Exception as exc:  # pragma: no cover - defensive background safety.
            logger.exception(
                "Unexpected planned transaction conversion error. planned_id=%s",
                planned_id,
            )
            summary.add_item(
                PlannedRunItem(
                    planned_id=planned_id,
                    planned_date=None,
                    status=PLANNED_CONVERSION_FAILED,
                    message=str(exc),
                    error_code=PLANNED_ERROR_UNEXPECTED,
                )
            )

    return summary


def convert_planned_transaction(
    *,
    planned_id: int,
    user=None,
    operation_date: date | None = None,
    mark_overdue_on_failure: bool = True,
) -> PlannedConversionResult:
    """Convert a planned transaction into an ordinary Transaction.

    The function is idempotent for already converted planned transactions: it
    returns the existing operation instead of creating a duplicate.
    """
    with db_transaction.atomic():
        planned_queryset = (
            PlannedTransaction.objects
            .select_for_update()
            .select_related("account", "category")
        )

        if user is not None:
            planned_queryset = planned_queryset.filter(user=user)

        try:
            planned = planned_queryset.get(pk=planned_id)
        except PlannedTransaction.DoesNotExist as exc:
            raise PlannedConversionError(
                code=PLANNED_ERROR_NOT_CONVERTIBLE,
                message="Планируемая операция не найдена.",
            ) from exc

        if planned.status == PlannedStatus.CONVERTED:
            return PlannedConversionResult(
                planned=planned,
                transaction=planned.converted_transaction,
                status=PLANNED_CONVERSION_SKIPPED,
                message="Планируемая операция уже конвертирована.",
            )

        if planned.status not in CONVERTIBLE_PLANNED_STATUSES:
            raise PlannedConversionError(
                code=PLANNED_ERROR_NOT_CONVERTIBLE,
                message="Планируемую операцию в текущем статусе нельзя конвертировать.",
            )

        scheduled_operation_date = operation_date or planned.planned_date
        locked_account = Account.objects.select_for_update().get(pk=planned.account_id)
        category = Category.objects.get(pk=planned.category_id)

        error = get_planned_conversion_error(
            planned=planned,
            account=locked_account,
            category=category,
        )

        if error:
            _mark_planned_failed(
                planned=planned,
                error_code=error["code"],
                error_message=error["message"],
                mark_overdue=mark_overdue_on_failure,
            )
            raise PlannedConversionError(
                code=error["code"],
                message=error["message"],
            )

        transaction = _create_transaction_from_planned(
            planned=planned,
            account=locked_account,
            category=category,
            operation_date=scheduled_operation_date,
        )
        _mark_planned_converted(
            planned=planned,
            transaction=transaction,
        )

        return PlannedConversionResult(
            planned=planned,
            transaction=transaction,
            status=PLANNED_CONVERSION_CONVERTED,
            message="Планируемая операция конвертирована.",
        )


def get_planned_conversion_error(
    *,
    planned: PlannedTransaction,
    account: Account,
    category: Category,
) -> dict[str, str] | None:
    if not account.is_active:
        return {
            "code": PLANNED_ERROR_ACCOUNT_INACTIVE,
            "message": "Счёт планируемой операции неактивен.",
        }

    if account.is_archived:
        return {
            "code": PLANNED_ERROR_ACCOUNT_ARCHIVED,
            "message": "Счёт планируемой операции находится в архиве.",
        }

    if not category.is_active:
        return {
            "code": PLANNED_ERROR_CATEGORY_INACTIVE,
            "message": "Категория планируемой операции неактивна.",
        }

    if category.is_archived:
        return {
            "code": PLANNED_ERROR_CATEGORY_ARCHIVED,
            "message": "Категория планируемой операции находится в архиве.",
        }

    if category.type != planned.type:
        return {
            "code": PLANNED_ERROR_CATEGORY_TYPE_MISMATCH,
            "message": "Тип категории не совпадает с типом планируемой операции.",
        }

    if (
        planned.type == TransactionType.EXPENSE
        and account.available_balance < planned.amount
    ):
        return {
            "code": PLANNED_ERROR_INSUFFICIENT_FUNDS,
            "message": "Недостаточно средств для конвертации планируемой операции.",
        }

    return None


def _create_transaction_from_planned(
    *,
    planned: PlannedTransaction,
    account: Account,
    category: Category,
    operation_date: date,
) -> Transaction:
    transaction = Transaction.objects.create(
        user=planned.user,
        account=account,
        category=category,
        type=planned.type,
        amount=planned.amount,
        description=_build_transaction_description(planned),
        operation_date=operation_date,
    )
    delta = get_transaction_balance_delta(
        transaction_type=transaction.type,
        amount=transaction.amount,
    )

    Account.objects.filter(pk=account.pk).update(
        balance=F("balance") + delta,
    )
    account.balance = account.balance + delta

    return transaction


def _build_transaction_description(planned: PlannedTransaction) -> str:
    if planned.comment:
        return planned.comment

    return f"Планируемая операция: {planned.name}"


def _mark_planned_converted(
    *,
    planned: PlannedTransaction,
    transaction: Transaction,
) -> None:
    planned.status = PlannedStatus.CONVERTED
    planned.converted_transaction = transaction
    planned.converted_at = timezone.now()
    planned.last_error_code = ""
    planned.last_error_message = ""
    planned.last_failed_at = None
    planned.save(
        update_fields=[
            "status",
            "converted_transaction",
            "converted_at",
            "last_error_code",
            "last_error_message",
            "last_failed_at",
            "updated_at",
        ]
    )


def _mark_planned_failed(
    *,
    planned: PlannedTransaction,
    error_code: str,
    error_message: str,
    mark_overdue: bool,
) -> None:
    if mark_overdue:
        planned.status = PlannedStatus.OVERDUE

    planned.last_error_code = error_code
    planned.last_error_message = error_message
    planned.last_failed_at = timezone.now()
    update_fields = [
        "last_error_code",
        "last_error_message",
        "last_failed_at",
        "updated_at",
    ]

    if mark_overdue:
        update_fields.insert(0, "status")

    planned.save(update_fields=update_fields)


def _build_dry_run_summary(
    *,
    planned_ids: list[int],
    run_date: date,
) -> PlannedRunSummary:
    summary = PlannedRunSummary(processed_count=len(planned_ids))

    planned_items = (
        PlannedTransaction.objects
        .filter(pk__in=planned_ids)
        .order_by("planned_date", "id")
    )

    for planned in planned_items:
        summary.add_item(
            PlannedRunItem(
                planned_id=planned.pk,
                planned_date=planned.planned_date,
                status=PLANNED_CONVERSION_SKIPPED,
                message=(
                    "Тестовый запуск: планируемая операция должна быть "
                    f"конвертирована не позднее {run_date.isoformat()}."
                ),
            )
        )

    return summary
