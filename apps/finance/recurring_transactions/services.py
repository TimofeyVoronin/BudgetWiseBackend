from __future__ import annotations

import calendar
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.db import transaction as db_transaction
from django.db.models import F
from django.utils import timezone

from apps.finance.accounts.accounting import get_transaction_balance_delta
from apps.finance.models import (
    Account,
    Category,
    RecurringChargeStatus,
    RecurringFrequency,
    RecurringStatus,
    RecurringTransaction,
    RecurringTransactionCharge,
    Transaction,
    TransactionType,
)


logger = logging.getLogger(__name__)

MAX_RECURRING_CATCH_UP_RUNS = 24


RECURRING_ERROR_ACCOUNT_INACTIVE = "ACCOUNT_INACTIVE"
RECURRING_ERROR_ACCOUNT_ARCHIVED = "ACCOUNT_ARCHIVED"
RECURRING_ERROR_CATEGORY_INACTIVE = "CATEGORY_INACTIVE"
RECURRING_ERROR_CATEGORY_ARCHIVED = "CATEGORY_ARCHIVED"
RECURRING_ERROR_CATEGORY_TYPE_MISMATCH = "CATEGORY_TYPE_MISMATCH"
RECURRING_ERROR_INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
RECURRING_ERROR_UNEXPECTED = "UNEXPECTED_ERROR"


@dataclass
class RecurringRunItem:
    recurring_id: int
    scheduled_date: date | None
    status: str
    message: str = ""
    transaction_id: int | None = None
    charge_id: int | None = None
    error_code: str = ""


@dataclass
class RecurringRunSummary:
    processed_count: int = 0
    created_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    completed_count: int = 0
    items: list[RecurringRunItem] = field(default_factory=list)

    def add_item(self, item: RecurringRunItem) -> None:
        self.items.append(item)

        if item.status == RecurringChargeStatus.SUCCESS:
            self.created_count += 1

        elif item.status == RecurringChargeStatus.FAILED:
            self.failed_count += 1

        elif item.status == RecurringChargeStatus.SKIPPED:
            self.skipped_count += 1

        elif item.status == RecurringStatus.COMPLETED:
            self.completed_count += 1

    def merge(self, other: "RecurringRunSummary") -> None:
        self.processed_count += other.processed_count
        self.created_count += other.created_count
        self.failed_count += other.failed_count
        self.skipped_count += other.skipped_count
        self.completed_count += other.completed_count
        self.items.extend(other.items)

    def as_dict(self) -> dict[str, Any]:
        return {
            "processed_count": self.processed_count,
            "created_count": self.created_count,
            "failed_count": self.failed_count,
            "skipped_count": self.skipped_count,
            "completed_count": self.completed_count,
            "items": [
                {
                    "recurring_id": item.recurring_id,
                    "scheduled_date": (
                        item.scheduled_date.isoformat()
                        if item.scheduled_date
                        else None
                    ),
                    "status": item.status,
                    "message": item.message,
                    "transaction_id": item.transaction_id,
                    "charge_id": item.charge_id,
                    "error_code": item.error_code,
                }
                for item in self.items
            ],
        }


def month_date(year: int, month: int, day: int) -> date:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day, last_day))


def add_months(value: date, months: int, *, day_of_month: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return month_date(year, month, day_of_month)


def get_next_charge_date(
    *,
    frequency: str,
    previous_date: date,
    day_of_month: int | None = None,
) -> date:
    if frequency == RecurringFrequency.DAILY:
        return previous_date + timedelta(days=1)

    if frequency == RecurringFrequency.WEEKLY:
        return previous_date + timedelta(days=7)

    if frequency == RecurringFrequency.MONTHLY:
        return add_months(
            previous_date,
            1,
            day_of_month=day_of_month or previous_date.day,
        )

    if frequency == RecurringFrequency.YEARLY:
        return month_date(
            previous_date.year + 1,
            previous_date.month,
            day_of_month or previous_date.day,
        )

    raise ValueError("Unsupported recurring frequency.")


def run_due_recurring_transactions(
    *,
    run_date: date | None = None,
    limit: int | None = None,
    dry_run: bool = False,
) -> RecurringRunSummary:
    """Run active recurring transactions due on or before run_date.

    This function is intended to be called by a cron job, management command or
    task scheduler. It creates ordinary Transaction records and stores every
    attempt in RecurringTransactionCharge.
    """
    if run_date is None:
        run_date = timezone.localdate()

    queryset = (
        RecurringTransaction.objects
        .filter(
            status=RecurringStatus.ACTIVE,
            next_charge_date__lte=run_date,
        )
        .order_by("next_charge_date", "id")
    )

    if limit is not None:
        queryset = queryset[:limit]

    recurring_ids = list(queryset.values_list("id", flat=True))

    if dry_run:
        return _build_dry_run_summary(
            recurring_ids=recurring_ids,
            run_date=run_date,
        )

    summary = RecurringRunSummary()

    for recurring_id in recurring_ids:
        try:
            item_summary = run_single_recurring_transaction(
                recurring_id=recurring_id,
                run_date=run_date,
            )
        except Exception as exc:  # pragma: no cover - defensive background safety.
            logger.exception(
                "Unexpected recurring transaction execution error. recurring_id=%s",
                recurring_id,
            )
            item_summary = record_unexpected_recurring_error(
                recurring_id=recurring_id,
                run_date=run_date,
                error=exc,
            )

        summary.merge(item_summary)

    return summary


def run_single_recurring_transaction(
    *,
    recurring_id: int,
    run_date: date | None = None,
) -> RecurringRunSummary:
    if run_date is None:
        run_date = timezone.localdate()

    summary = RecurringRunSummary(processed_count=1)

    with db_transaction.atomic():
        recurring = (
            RecurringTransaction.objects
            .select_for_update()
            .select_related("account", "category")
            .get(pk=recurring_id)
        )

        if recurring.status != RecurringStatus.ACTIVE:
            summary.add_item(
                RecurringRunItem(
                    recurring_id=recurring.pk,
                    scheduled_date=recurring.next_charge_date,
                    status=RecurringChargeStatus.SKIPPED,
                    message="Регулярная операция не активна.",
                )
            )
            return summary

        runs_count = 0

        while recurring.next_charge_date <= run_date:
            if runs_count >= MAX_RECURRING_CATCH_UP_RUNS:
                summary.add_item(
                    RecurringRunItem(
                        recurring_id=recurring.pk,
                        scheduled_date=recurring.next_charge_date,
                        status=RecurringChargeStatus.SKIPPED,
                        message=(
                            "Достигнут лимит обработок за один запуск. "
                            "Повторите команду для продолжения."
                        ),
                    )
                )
                break

            scheduled_date = recurring.next_charge_date

            if (
                recurring.has_end
                and recurring.end_date
                and scheduled_date > recurring.end_date
            ):
                _mark_recurring_completed(recurring)
                summary.add_item(
                    RecurringRunItem(
                        recurring_id=recurring.pk,
                        scheduled_date=scheduled_date,
                        status=RecurringStatus.COMPLETED,
                        message="Регулярная операция завершена.",
                    )
                )
                break

            if _charge_already_exists(
                recurring=recurring,
                scheduled_date=scheduled_date,
            ):
                _advance_recurring_after_skip(
                    recurring=recurring,
                    scheduled_date=scheduled_date,
                )
                summary.add_item(
                    RecurringRunItem(
                        recurring_id=recurring.pk,
                        scheduled_date=scheduled_date,
                        status=RecurringChargeStatus.SKIPPED,
                        message="Списание за эту дату уже обработано.",
                    )
                )
                runs_count += 1
                continue

            locked_account = (
                Account.objects
                .select_for_update()
                .get(pk=recurring.account_id)
            )
            category = Category.objects.get(pk=recurring.category_id)

            error = _get_recurring_execution_error(
                recurring=recurring,
                account=locked_account,
                category=category,
            )

            if error:
                charge = _create_failed_charge(
                    recurring=recurring,
                    scheduled_date=scheduled_date,
                    error_code=error["code"],
                    error_message=error["message"],
                )
                _mark_recurring_failed(
                    recurring=recurring,
                    scheduled_date=scheduled_date,
                    error_code=error["code"],
                    error_message=error["message"],
                )
                summary.add_item(
                    RecurringRunItem(
                        recurring_id=recurring.pk,
                        scheduled_date=scheduled_date,
                        status=RecurringChargeStatus.FAILED,
                        message=error["message"],
                        charge_id=charge.pk,
                        error_code=error["code"],
                    )
                )
                break

            transaction = _create_transaction_from_recurring(
                recurring=recurring,
                account=locked_account,
                category=category,
                scheduled_date=scheduled_date,
            )
            charge = RecurringTransactionCharge.objects.create(
                user=recurring.user,
                recurring_transaction=recurring,
                transaction=transaction,
                scheduled_date=scheduled_date,
                amount=recurring.amount,
                status=RecurringChargeStatus.SUCCESS,
            )
            _mark_recurring_success(
                recurring=recurring,
                scheduled_date=scheduled_date,
            )

            summary.add_item(
                RecurringRunItem(
                    recurring_id=recurring.pk,
                    scheduled_date=scheduled_date,
                    status=RecurringChargeStatus.SUCCESS,
                    message="Операция создана.",
                    transaction_id=transaction.pk,
                    charge_id=charge.pk,
                )
            )

            runs_count += 1

            if recurring.status == RecurringStatus.COMPLETED:
                summary.add_item(
                    RecurringRunItem(
                        recurring_id=recurring.pk,
                        scheduled_date=recurring.next_charge_date,
                        status=RecurringStatus.COMPLETED,
                        message="Регулярная операция завершена.",
                    )
                )
                break

    return summary


def record_unexpected_recurring_error(
    *,
    recurring_id: int,
    run_date: date,
    error: Exception,
) -> RecurringRunSummary:
    summary = RecurringRunSummary(processed_count=1)

    with db_transaction.atomic():
        recurring = (
            RecurringTransaction.objects
            .select_for_update()
            .get(pk=recurring_id)
        )
        scheduled_date = recurring.next_charge_date

        if scheduled_date > run_date:
            summary.add_item(
                RecurringRunItem(
                    recurring_id=recurring.pk,
                    scheduled_date=scheduled_date,
                    status=RecurringChargeStatus.SKIPPED,
                    message="Регулярная операция уже не требует обработки.",
                )
            )
            return summary

        charge = _create_failed_charge(
            recurring=recurring,
            scheduled_date=scheduled_date,
            error_code=RECURRING_ERROR_UNEXPECTED,
            error_message=str(error),
        )
        _mark_recurring_failed(
            recurring=recurring,
            scheduled_date=scheduled_date,
            error_code=RECURRING_ERROR_UNEXPECTED,
            error_message=str(error),
        )

        summary.add_item(
            RecurringRunItem(
                recurring_id=recurring.pk,
                scheduled_date=scheduled_date,
                status=RecurringChargeStatus.FAILED,
                message=str(error),
                charge_id=charge.pk,
                error_code=RECURRING_ERROR_UNEXPECTED,
            )
        )

    return summary


def _build_dry_run_summary(
    *,
    recurring_ids: list[int],
    run_date: date,
) -> RecurringRunSummary:
    summary = RecurringRunSummary(processed_count=len(recurring_ids))

    recurring_items = (
        RecurringTransaction.objects
        .filter(pk__in=recurring_ids)
        .order_by("next_charge_date", "id")
    )

    for recurring in recurring_items:
        summary.add_item(
            RecurringRunItem(
                recurring_id=recurring.pk,
                scheduled_date=recurring.next_charge_date,
                status=RecurringChargeStatus.SKIPPED,
                message=(
                    "Тестовый запуск: операция должна быть обработана "
                    f"не позднее {run_date.isoformat()}."
                ),
            )
        )

    return summary


def _create_transaction_from_recurring(
    *,
    recurring: RecurringTransaction,
    account: Account,
    category: Category,
    scheduled_date: date,
) -> Transaction:
    transaction = Transaction.objects.create(
        user=recurring.user,
        account=account,
        category=category,
        type=recurring.type,
        amount=recurring.amount,
        description=_build_transaction_description(recurring),
        operation_date=scheduled_date,
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


def _build_transaction_description(recurring: RecurringTransaction) -> str:
    if recurring.comment:
        return recurring.comment

    return f"Регулярная операция: {recurring.name}"


def _get_recurring_execution_error(
    *,
    recurring: RecurringTransaction,
    account: Account,
    category: Category,
) -> dict[str, str] | None:
    if not account.is_active:
        return {
            "code": RECURRING_ERROR_ACCOUNT_INACTIVE,
            "message": "Счёт регулярной операции неактивен.",
        }

    if account.is_archived:
        return {
            "code": RECURRING_ERROR_ACCOUNT_ARCHIVED,
            "message": "Счёт регулярной операции находится в архиве.",
        }

    if not category.is_active:
        return {
            "code": RECURRING_ERROR_CATEGORY_INACTIVE,
            "message": "Категория регулярной операции неактивна.",
        }

    if category.is_archived:
        return {
            "code": RECURRING_ERROR_CATEGORY_ARCHIVED,
            "message": "Категория регулярной операции находится в архиве.",
        }

    if category.type != recurring.type:
        return {
            "code": RECURRING_ERROR_CATEGORY_TYPE_MISMATCH,
            "message": "Тип категории не совпадает с типом регулярной операции.",
        }

    if (
        recurring.type == TransactionType.EXPENSE
        and account.available_balance < recurring.amount
    ):
        return {
            "code": RECURRING_ERROR_INSUFFICIENT_FUNDS,
            "message": "Недостаточно средств для выполнения регулярной операции.",
        }

    return None


def _charge_already_exists(
    *,
    recurring: RecurringTransaction,
    scheduled_date: date,
) -> bool:
    return RecurringTransactionCharge.objects.filter(
        recurring_transaction=recurring,
        scheduled_date=scheduled_date,
    ).exists()


def _create_failed_charge(
    *,
    recurring: RecurringTransaction,
    scheduled_date: date,
    error_code: str,
    error_message: str,
) -> RecurringTransactionCharge:
    return RecurringTransactionCharge.objects.create(
        user=recurring.user,
        recurring_transaction=recurring,
        scheduled_date=scheduled_date,
        amount=recurring.amount,
        status=RecurringChargeStatus.FAILED,
        error_code=error_code,
        error_message=error_message,
    )


def _mark_recurring_success(
    *,
    recurring: RecurringTransaction,
    scheduled_date: date,
) -> None:
    next_charge_date = get_next_charge_date(
        frequency=recurring.frequency,
        previous_date=scheduled_date,
        day_of_month=recurring.day_of_month,
    )
    status = RecurringStatus.ACTIVE

    if (
        recurring.has_end
        and recurring.end_date
        and next_charge_date > recurring.end_date
    ):
        status = RecurringStatus.COMPLETED

    recurring.last_charge_date = scheduled_date
    recurring.next_charge_date = next_charge_date
    recurring.created_count += 1
    recurring.status = status
    recurring.last_error_code = ""
    recurring.last_error_message = ""
    recurring.last_failed_at = None
    recurring.save(
        update_fields=[
            "last_charge_date",
            "next_charge_date",
            "created_count",
            "status",
            "last_error_code",
            "last_error_message",
            "last_failed_at",
            "updated_at",
        ]
    )


def _mark_recurring_failed(
    *,
    recurring: RecurringTransaction,
    scheduled_date: date,
    error_code: str,
    error_message: str,
) -> None:
    recurring.next_charge_date = get_next_charge_date(
        frequency=recurring.frequency,
        previous_date=scheduled_date,
        day_of_month=recurring.day_of_month,
    )
    recurring.status = RecurringStatus.ERROR
    recurring.last_error_code = error_code
    recurring.last_error_message = error_message
    recurring.last_failed_at = timezone.now()
    recurring.save(
        update_fields=[
            "next_charge_date",
            "status",
            "last_error_code",
            "last_error_message",
            "last_failed_at",
            "updated_at",
        ]
    )


def _advance_recurring_after_skip(
    *,
    recurring: RecurringTransaction,
    scheduled_date: date,
) -> None:
    recurring.next_charge_date = get_next_charge_date(
        frequency=recurring.frequency,
        previous_date=scheduled_date,
        day_of_month=recurring.day_of_month,
    )
    recurring.save(update_fields=["next_charge_date", "updated_at"])


def _mark_recurring_completed(recurring: RecurringTransaction) -> None:
    recurring.status = RecurringStatus.COMPLETED
    recurring.save(update_fields=["status", "updated_at"])
