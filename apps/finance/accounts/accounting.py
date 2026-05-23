from __future__ import annotations

from decimal import Decimal

from django.db import transaction as db_transaction
from django.db.models import F

from apps.finance.models import Account, Transaction, TransactionType


def create_transaction_with_balance_update(serializer) -> Transaction:
    """Create a transaction and apply its effect to the account balance."""
    with db_transaction.atomic():
        account = serializer.validated_data["account"]
        locked_account = _lock_account(account.pk)

        serializer.validated_data["account"] = locked_account
        transaction = serializer.save()

        _apply_transaction_effect(transaction)

        return transaction


def update_transaction_with_balance_update(serializer) -> Transaction:
    """Update a transaction and recalculate affected account balances."""
    with db_transaction.atomic():
        old_transaction = (
            Transaction.objects
            .select_for_update()
            .select_related("account")
            .get(pk=serializer.instance.pk)
        )

        new_account = serializer.validated_data.get(
            "account",
            old_transaction.account,
        )
        locked_accounts = _lock_accounts(
            old_transaction.account_id,
            new_account.pk,
        )

        _rollback_transaction_effect(old_transaction)

        if "account" in serializer.validated_data:
            serializer.validated_data["account"] = locked_accounts[new_account.pk]

        serializer.instance = old_transaction
        updated_transaction = serializer.save()

        _apply_transaction_effect(updated_transaction)

        return updated_transaction


def delete_transaction_with_balance_update(instance: Transaction) -> None:
    """Delete a transaction and rollback its effect from the account balance."""
    with db_transaction.atomic():
        transaction = (
            Transaction.objects
            .select_for_update()
            .select_related("account")
            .get(pk=instance.pk)
        )

        _lock_account(transaction.account_id)
        _rollback_transaction_effect(transaction)
        transaction.delete()


def _apply_transaction_effect(transaction: Transaction) -> None:
    delta = get_transaction_balance_delta(
        transaction_type=transaction.type,
        amount=transaction.amount,
    )
    _apply_account_balance_delta(
        account_id=transaction.account_id,
        delta=delta,
    )


def _rollback_transaction_effect(transaction: Transaction) -> None:
    delta = get_transaction_balance_delta(
        transaction_type=transaction.type,
        amount=transaction.amount,
    )
    _apply_account_balance_delta(
        account_id=transaction.account_id,
        delta=-delta,
    )


def get_transaction_balance_delta(
    *,
    transaction_type: str,
    amount: Decimal,
) -> Decimal:
    normalized_amount = abs(amount)

    if transaction_type == TransactionType.INCOME:
        return normalized_amount

    if transaction_type == TransactionType.EXPENSE:
        return -normalized_amount

    raise ValueError("Unsupported transaction type for balance update.")


def _apply_account_balance_delta(
    *,
    account_id: int,
    delta: Decimal,
) -> None:
    Account.objects.filter(pk=account_id).update(
        balance=F("balance") + delta,
    )


def _lock_account(account_id: int) -> Account:
    return Account.objects.select_for_update().get(pk=account_id)


def _lock_accounts(*account_ids: int) -> dict[int, Account]:
    unique_account_ids = sorted(set(account_ids))

    return {
        account.pk: account
        for account in Account.objects.select_for_update().filter(
            pk__in=unique_account_ids,
        )
    }
