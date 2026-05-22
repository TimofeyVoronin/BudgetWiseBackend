from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from django.db import transaction as db_transaction
from django.db.models import F
from django.utils import timezone

from apps.finance.currencies import validate_user_currency_available
from apps.finance.models import (
    Account,
    Category,
    Receipt,
    ReceiptItem,
    ReceiptOperationType,
    ReceiptStatus,
    Transaction,
    TransactionType,
)
from apps.finance.accounting import get_transaction_balance_delta


RECEIPT_TRANSACTION_MODE_SINGLE = "single"
RECEIPT_TRANSACTION_MODE_BY_ITEMS = "by_items"
RECEIPT_TRANSACTION_MODES = {
    RECEIPT_TRANSACTION_MODE_SINGLE,
    RECEIPT_TRANSACTION_MODE_BY_ITEMS,
}


class ReceiptTransactionCreationError(ValueError):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        field_errors: dict[str, str | list[str]] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.field_errors = field_errors or {}
        super().__init__(message)


@dataclass(frozen=True)
class ReceiptItemTransactionInput:
    receipt_item_id: int
    category_id: int | None = None


@dataclass(frozen=True)
class ReceiptTransactionCreationResult:
    receipt: Receipt
    transactions: tuple[Transaction, ...]
    mode: str

    @property
    def created_count(self) -> int:
        return len(self.transactions)


def receipt_operation_to_transaction_type(receipt: Receipt) -> str:
    """
    Convert fiscal receipt operation into the user's finance transaction type.

    In fiscal data, operation type is written from the seller's perspective.
    A regular seller-side income receipt means the user spent money.
    A seller-side income return means the user received a refund.
    """

    if receipt.operation_type == ReceiptOperationType.INCOME:
        return TransactionType.EXPENSE
    if receipt.operation_type == ReceiptOperationType.INCOME_RETURN:
        return TransactionType.INCOME
    if receipt.operation_type == ReceiptOperationType.EXPENSE:
        return TransactionType.INCOME
    if receipt.operation_type == ReceiptOperationType.EXPENSE_RETURN:
        return TransactionType.EXPENSE

    raise ReceiptTransactionCreationError(
        code="unsupported_receipt_operation_type",
        message="Тип операции по чеку не поддерживается для создания операции.",
        field_errors={"receipt": "Недопустимый тип операции по чеку."},
    )


def create_transactions_from_receipt(
    *,
    user,
    receipt: Receipt,
    account: Account,
    mode: str,
    category: Category | None = None,
    items: Iterable[ReceiptItemTransactionInput] | None = None,
    description: str = "",
) -> ReceiptTransactionCreationResult:
    _validate_common(user=user, receipt=receipt, account=account, mode=mode)

    transaction_type = receipt_operation_to_transaction_type(receipt)

    with db_transaction.atomic():
        locked_receipt = (
            Receipt.objects.select_for_update()
            .select_related("user")
            .get(pk=receipt.pk)
        )
        locked_account = Account.objects.select_for_update().get(pk=account.pk)

        if locked_receipt.status == ReceiptStatus.IMPORTED or locked_receipt.transactions.exists():
            raise ReceiptTransactionCreationError(
                code="receipt_already_imported",
                message="По этому чеку уже созданы операции.",
                field_errors={"receipt": "Повторное создание операций по чеку запрещено."},
            )

        if mode == RECEIPT_TRANSACTION_MODE_SINGLE:
            if category is None:
                raise ReceiptTransactionCreationError(
                    code="category_required",
                    message="Для создания одной операции нужно выбрать категорию.",
                    field_errors={"categoryId": "Укажите категорию."},
                )
            _validate_category(user=user, category=category, transaction_type=transaction_type)
            transactions = (
                _create_transaction(
                    user=user,
                    receipt=locked_receipt,
                    receipt_item=None,
                    account=locked_account,
                    category=category,
                    transaction_type=transaction_type,
                    amount=locked_receipt.total_amount,
                    description=description or _default_single_description(locked_receipt),
                ),
            )
        elif mode == RECEIPT_TRANSACTION_MODE_BY_ITEMS:
            item_inputs = list(items or [])
            if not item_inputs:
                raise ReceiptTransactionCreationError(
                    code="items_required",
                    message="Для создания операций по позициям нужно передать позиции чека.",
                    field_errors={"items": "Передайте хотя бы одну позицию чека."},
                )
            transactions = tuple(
                _create_transactions_by_items(
                    user=user,
                    receipt=locked_receipt,
                    account=locked_account,
                    transaction_type=transaction_type,
                    item_inputs=item_inputs,
                )
            )
        else:
            raise ReceiptTransactionCreationError(
                code="invalid_mode",
                message="Недопустимый режим создания операций по чеку.",
                field_errors={"mode": "Поддерживаются режимы single и by_items."},
            )

        locked_receipt.status = ReceiptStatus.IMPORTED
        locked_receipt.save(update_fields=["status", "updated_at"])

    return ReceiptTransactionCreationResult(
        receipt=locked_receipt,
        transactions=transactions,
        mode=mode,
    )


def _create_transactions_by_items(
    *,
    user,
    receipt: Receipt,
    account: Account,
    transaction_type: str,
    item_inputs: list[ReceiptItemTransactionInput],
) -> list[Transaction]:
    receipt_item_ids = [item.receipt_item_id for item in item_inputs]
    if len(receipt_item_ids) != len(set(receipt_item_ids)):
        raise ReceiptTransactionCreationError(
            code="duplicate_receipt_items",
            message="Позиции чека не должны повторяться.",
            field_errors={"items": "Удалите повторяющиеся позиции."},
        )

    receipt_items = {
        item.pk: item
        for item in ReceiptItem.objects.select_for_update().filter(
            receipt=receipt,
            pk__in=receipt_item_ids,
        )
    }
    missing_item_ids = [item_id for item_id in receipt_item_ids if item_id not in receipt_items]
    if missing_item_ids:
        raise ReceiptTransactionCreationError(
            code="receipt_item_not_found",
            message="Одна или несколько позиций чека не найдены.",
            field_errors={"items": f"Недоступные позиции: {', '.join(map(str, missing_item_ids))}."},
        )

    category_ids = [item.category_id for item in item_inputs if item.category_id is not None]
    categories = {
        category.pk: category
        for category in Category.objects.filter(user=user, pk__in=category_ids)
    }

    transactions: list[Transaction] = []
    for item_input in item_inputs:
        receipt_item = receipt_items[item_input.receipt_item_id]
        category = None
        if item_input.category_id is not None:
            category = categories.get(item_input.category_id)
            if category is None:
                raise ReceiptTransactionCreationError(
                    code="category_not_found",
                    message="Категория позиции чека не найдена.",
                    field_errors={"items": f"Категория {item_input.category_id} недоступна."},
                )
        else:
            category = receipt_item.suggested_category

        if category is None:
            raise ReceiptTransactionCreationError(
                code="category_required",
                message="Для каждой позиции чека нужно выбрать категорию.",
                field_errors={"items": f"Укажите категорию для позиции {receipt_item.id}."},
            )

        _validate_category(user=user, category=category, transaction_type=transaction_type)

        transactions.append(
            _create_transaction(
                user=user,
                receipt=receipt,
                receipt_item=receipt_item,
                account=account,
                category=category,
                transaction_type=transaction_type,
                amount=receipt_item.amount,
                description=_default_item_description(receipt, receipt_item),
            )
        )

    return transactions


def _validate_common(*, user, receipt: Receipt, account: Account, mode: str) -> None:
    if mode not in RECEIPT_TRANSACTION_MODES:
        raise ReceiptTransactionCreationError(
            code="invalid_mode",
            message="Недопустимый режим создания операций по чеку.",
            field_errors={"mode": "Поддерживаются режимы single и by_items."},
        )

    if receipt.user_id != user.id:
        raise ReceiptTransactionCreationError(
            code="receipt_not_found",
            message="Чек не найден.",
            field_errors={"receipt": "Чек должен принадлежать текущему пользователю."},
        )

    if account.user_id != user.id:
        raise ReceiptTransactionCreationError(
            code="account_not_found",
            message="Счёт не найден.",
            field_errors={"accountId": "Счёт должен принадлежать текущему пользователю."},
        )

    if not account.is_active or account.is_archived:
        raise ReceiptTransactionCreationError(
            code="account_unavailable",
            message="Нельзя использовать неактивный или архивный счёт.",
            field_errors={"accountId": "Выберите активный счёт."},
        )

    try:
        validate_user_currency_available(
            user,
            account.currency,
            field_name="accountId",
            require_visible=True,
        )
    except Exception as exc:  # DRF validation error, converted to service-level error.
        raise ReceiptTransactionCreationError(
            code="account_currency_unavailable",
            message="Валюта счёта недоступна для создания новой операции.",
            field_errors={"accountId": "Выберите счёт с видимой валютой."},
        ) from exc


def _validate_category(*, user, category: Category, transaction_type: str) -> None:
    if category.user_id != user.id:
        raise ReceiptTransactionCreationError(
            code="category_not_found",
            message="Категория не найдена.",
            field_errors={"categoryId": "Категория должна принадлежать текущему пользователю."},
        )

    if category.type != transaction_type:
        raise ReceiptTransactionCreationError(
            code="category_type_mismatch",
            message="Тип категории должен совпадать с типом операции.",
            field_errors={"categoryId": "Выберите категорию подходящего типа."},
        )

    if not category.is_active or category.is_archived:
        raise ReceiptTransactionCreationError(
            code="category_unavailable",
            message="Нельзя использовать неактивную или архивную категорию.",
            field_errors={"categoryId": "Выберите активную категорию."},
        )


def _create_transaction(
    *,
    user,
    receipt: Receipt,
    receipt_item: ReceiptItem | None,
    account: Account,
    category: Category,
    transaction_type: str,
    amount: Decimal,
    description: str,
) -> Transaction:
    transaction = Transaction.objects.create(
        user=user,
        account=account,
        category=category,
        type=transaction_type,
        amount=abs(amount).quantize(Decimal("0.01")),
        description=description,
        operation_date=timezone.localtime(receipt.receipt_datetime).date(),
        receipt=receipt,
        receipt_item=receipt_item,
    )
    _apply_account_balance_delta(transaction)
    return transaction


def _apply_account_balance_delta(transaction: Transaction) -> None:
    Account.objects.filter(pk=transaction.account_id).update(
        balance=F("balance") + get_transaction_balance_delta(
            transaction_type=transaction.type,
            amount=transaction.amount,
        )
    )


def _default_single_description(receipt: Receipt) -> str:
    store_name = receipt.store_name.strip() if receipt.store_name else "Чек"
    date_label = timezone.localtime(receipt.receipt_datetime).strftime("%d.%m.%Y")
    return f"{store_name} · чек от {date_label}"


def _default_item_description(receipt: Receipt, receipt_item: ReceiptItem) -> str:
    store_name = receipt.store_name.strip() if receipt.store_name else "Чек"
    return f"{store_name} · {receipt_item.name}"
