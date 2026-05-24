from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

from django.db import transaction as db_transaction
from django.db.models import F, Max
from django.utils import timezone

from apps.finance.currencies.services import validate_user_currency_available
from apps.finance.models import (
    Account,
    Category,
    Receipt,
    ReceiptItem,
    ReceiptOperationType,
    ReceiptStatus,
    Transaction,
    TransactionLineItem,
    TransactionType,
)
from apps.finance.accounts.accounting import get_transaction_balance_delta


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
    receipt_item_id: int | None = None
    category_id: int | None = None
    name: str = ""
    quantity: Decimal | None = None
    price: Decimal | None = None
    amount: Decimal | None = None

    @property
    def is_existing_item(self) -> bool:
        return self.receipt_item_id is not None


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
    try:
        return _create_transactions_from_receipt_impl(
            user=user,
            receipt=receipt,
            account=account,
            mode=mode,
            category=category,
            items=items,
            description=description,
        )
    except ReceiptTransactionCreationError as exc:
        if getattr(receipt, "user_id", None) == getattr(user, "id", None):
            from apps.finance.receipts.audit import log_receipt_import_failed

            log_receipt_import_failed(
                receipt=receipt,
                code=exc.code,
                message=exc.message,
                field_errors=exc.field_errors,
            )
        raise


def _create_transactions_from_receipt_impl(
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

        from apps.finance.models import ReceiptAuditAction, ReceiptAuditStatus
        from apps.finance.receipts.audit import log_receipt_audit_event

        log_receipt_audit_event(
            receipt=locked_receipt,
            action=ReceiptAuditAction.TRANSACTIONS_CREATED,
            status=ReceiptAuditStatus.SUCCESS,
            message="По чеку созданы финансовые операции.",
            metadata={
                "mode": mode,
                "createdCount": len(transactions),
                "transactionIds": [transaction.id for transaction in transactions],
                "accountId": locked_account.id,
            },
        )

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
    existing_item_ids = [
        item.receipt_item_id
        for item in item_inputs
        if item.receipt_item_id is not None
    ]
    if len(existing_item_ids) != len(set(existing_item_ids)):
        raise ReceiptTransactionCreationError(
            code="duplicate_receipt_items",
            message="Позиции чека не должны повторяться.",
            field_errors={"items": "Удалите повторяющиеся позиции."},
        )

    receipt_items = {
        item.pk: item
        for item in ReceiptItem.objects.select_for_update().filter(
            receipt=receipt,
            pk__in=existing_item_ids,
        )
    }
    missing_item_ids = [item_id for item_id in existing_item_ids if item_id not in receipt_items]
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
    next_line_number = _get_next_receipt_item_line_number(receipt)

    for item_input in item_inputs:
        category = _resolve_receipt_item_category(
            user=user,
            transaction_type=transaction_type,
            item_input=item_input,
            categories=categories,
        )
        receipt_item = _resolve_receipt_item(
            receipt=receipt,
            item_input=item_input,
            existing_items=receipt_items,
            category=category,
            line_number=next_line_number,
        )
        if not item_input.is_existing_item:
            next_line_number += 1

        category = category or receipt_item.suggested_category
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


def _resolve_receipt_item_category(
    *,
    user,
    transaction_type: str,
    item_input: ReceiptItemTransactionInput,
    categories: dict[int, Category],
) -> Category | None:
    category = None
    if item_input.category_id is not None:
        category = categories.get(item_input.category_id)
        if category is None:
            raise ReceiptTransactionCreationError(
                code="category_not_found",
                message="Категория позиции чека не найдена.",
                field_errors={"items": f"Категория {item_input.category_id} недоступна."},
            )

    if category is not None:
        _validate_category(user=user, category=category, transaction_type=transaction_type)
        return category

    if not item_input.is_existing_item:
        raise ReceiptTransactionCreationError(
            code="category_required",
            message="Для каждой ручной позиции чека нужно выбрать категорию.",
            field_errors={"items": "Укажите категорию для каждой ручной позиции."},
        )

    return category


def _resolve_receipt_item(
    *,
    receipt: Receipt,
    item_input: ReceiptItemTransactionInput,
    existing_items: dict[int, ReceiptItem],
    category: Category | None,
    line_number: int,
) -> ReceiptItem:
    if item_input.is_existing_item:
        receipt_item = existing_items[item_input.receipt_item_id]
        if category is None:
            category = receipt_item.suggested_category

        if category is None:
            raise ReceiptTransactionCreationError(
                code="category_required",
                message="Для каждой позиции чека нужно выбрать категорию.",
                field_errors={"items": f"Укажите категорию для позиции {receipt_item.id}."},
            )

        return receipt_item

    if category is None:
        raise ReceiptTransactionCreationError(
            code="category_required",
            message="Для ручной позиции чека нужно выбрать категорию.",
            field_errors={"items": "Укажите категорию для ручной позиции."},
        )

    amount = _quantize_money(item_input.amount)
    quantity = _quantize_quantity(item_input.quantity or Decimal("1.000"))
    price = _quantize_money(item_input.price or amount)

    return ReceiptItem.objects.create(
        receipt=receipt,
        line_number=line_number,
        name=(item_input.name or "Позиция чека").strip(),
        quantity=quantity,
        price=price,
        amount=amount,
        suggested_category=category,
        mapping_confidence=Decimal("1.00"),
        mapping_reason="Позиция добавлена вручную при создании операций.",
        provider_payload={"source": "manual_create_transaction"},
    )


def _get_next_receipt_item_line_number(receipt: Receipt) -> int:
    max_line_number = receipt.items.aggregate(max_line_number=Max("line_number"))["max_line_number"]
    return int(max_line_number or 0) + 1


def _quantize_money(value: Decimal | None) -> Decimal:
    if value is None:
        raise ReceiptTransactionCreationError(
            code="receipt_item_amount_required",
            message="Для ручной позиции чека нужно указать сумму.",
            field_errors={"items": "Передайте amount или price."},
        )
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _quantize_quantity(value: Decimal | None) -> Decimal:
    if value is None:
        return Decimal("1.000")
    return Decimal(value).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


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
    if receipt_item is not None:
        _copy_receipt_items_to_transaction(
            transaction=transaction,
            receipt_items=[receipt_item],
        )
    else:
        _copy_receipt_items_to_transaction(
            transaction=transaction,
            receipt_items=receipt.items.order_by("line_number", "id"),
        )

    _apply_account_balance_delta(transaction)
    return transaction


def _copy_receipt_items_to_transaction(
    *,
    transaction: Transaction,
    receipt_items: Iterable[ReceiptItem],
) -> None:
    line_items = [
        TransactionLineItem(
            transaction=transaction,
            line_number=index,
            name=receipt_item.name,
            quantity=receipt_item.quantity or Decimal("1.000"),
            unit_price=receipt_item.price or receipt_item.amount,
            amount=receipt_item.amount,
        )
        for index, receipt_item in enumerate(receipt_items, start=1)
    ]
    if line_items:
        TransactionLineItem.objects.bulk_create(line_items)


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
