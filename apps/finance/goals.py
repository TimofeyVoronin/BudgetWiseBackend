from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction as db_transaction
from django.db.models import F
from django.utils import timezone

from apps.common.domain_errors import DomainConflictError
from apps.finance.models import (
    Account,
    Category,
    Goal,
    GoalContribution,
    GoalStatus,
    Transaction,
    TransactionType,
)


GOAL_TOPUP_CATEGORY_NAME = "Пополнение целей"


@dataclass(frozen=True)
class GoalFundingResult:
    goal: Goal
    contribution: GoalContribution
    transaction: Transaction


def fund_goal(
    *,
    goal: Goal,
    user,
    amount: Decimal,
    contribution_date,
    account: Account,
    comment: str = "",
) -> GoalFundingResult:
    """Fund a goal and create a linked expense transaction.

    The operation is atomic:
    - goal current_amount increases;
    - account balance decreases;
    - expense transaction is created;
    - contribution history row is created.
    """
    with db_transaction.atomic():
        locked_goal = (
            Goal.objects
            .select_for_update()
            .get(pk=goal.pk, user=user)
        )

        if locked_goal.status != GoalStatus.ACTIVE:
            raise DomainConflictError(
                code="goal_not_active",
                message="Пополнять можно только активную цель.",
                detail={
                    "status": locked_goal.status,
                },
            )

        locked_account = (
            Account.objects
            .select_for_update()
            .get(pk=account.pk, user=user)
        )

        if amount <= Decimal("0.00"):
            raise DomainConflictError(
                code="invalid_goal_topup_amount",
                message="Сумма пополнения цели должна быть больше нуля.",
                detail={
                    "amount": str(amount),
                },
            )

        remaining_amount = locked_goal.target_amount - locked_goal.current_amount

        if remaining_amount <= Decimal("0.00"):
            raise DomainConflictError(
                code="goal_already_funded",
                message="Цель уже достигнута и не требует пополнения.",
                detail={
                    "goal_id": locked_goal.pk,
                    "status": locked_goal.status,
                },
            )

        if amount > remaining_amount:
            raise DomainConflictError(
                code="goal_topup_exceeds_remaining_amount",
                message=(
                    "Сумма пополнения не может быть больше оставшейся "
                    "суммы по цели."
                ),
                detail={
                    "remaining_amount": str(remaining_amount),
                    "amount": str(amount),
                },
            )

        if not locked_account.is_active or locked_account.is_archived:
            raise DomainConflictError(
                code="account_not_available",
                message="Нельзя пополнить цель с неактивного или архивного счёта.",
                detail={
                    "account_id": locked_account.pk,
                },
            )

        if locked_account.available_balance < amount:
            raise DomainConflictError(
                code="insufficient_account_balance",
                message="На счёте недостаточно доступного баланса для пополнения цели.",
                detail={
                    "account_id": locked_account.pk,
                    "available_balance": str(locked_account.available_balance),
                    "amount": str(amount),
                },
            )

        category = get_or_create_goal_topup_category(user=user)
        operation_description = build_goal_topup_description(
            goal=locked_goal,
            comment=comment,
        )

        transaction = Transaction.objects.create(
            user=user,
            account=locked_account,
            category=category,
            type=TransactionType.EXPENSE,
            amount=amount,
            description=operation_description,
            operation_date=contribution_date,
        )

        Account.objects.filter(pk=locked_account.pk).update(
            balance=F("balance") - amount,
        )

        contribution = GoalContribution.objects.create(
            user=user,
            goal=locked_goal,
            account=locked_account,
            transaction=transaction,
            account_name=locked_account.name,
            amount=amount,
            contribution_date=contribution_date,
            comment=comment,
        )

        Goal.objects.filter(pk=locked_goal.pk).update(
            current_amount=F("current_amount") + amount,
        )

        locked_goal.refresh_from_db()
        contribution.refresh_from_db()
        transaction.refresh_from_db()

        if (
            locked_goal.status == GoalStatus.ACTIVE
            and locked_goal.current_amount >= locked_goal.target_amount
        ):
            locked_goal.status = GoalStatus.COMPLETED
            locked_goal.save(update_fields=["status", "updated_at"])

        return GoalFundingResult(
            goal=locked_goal,
            contribution=contribution,
            transaction=transaction,
        )


def get_or_create_goal_topup_category(*, user) -> Category:
    category, created = Category.objects.get_or_create(
        user=user,
        name=GOAL_TOPUP_CATEGORY_NAME,
        type=TransactionType.EXPENSE,
        defaults={
            "icon": "target",
            "color": "#4F46E5",
            "is_active": True,
            "is_archived": False,
        },
    )

    update_fields = []

    if not category.is_active:
        category.is_active = True
        update_fields.append("is_active")

    if category.is_archived:
        category.is_archived = False
        update_fields.append("is_archived")

    if update_fields:
        update_fields.append("updated_at")
        category.save(update_fields=update_fields)

    return category


def build_goal_topup_description(*, goal: Goal, comment: str = "") -> str:
    base_description = f"Пополнение цели: {goal.name}"
    clean_comment = comment.strip()

    if clean_comment:
        return f"{base_description}. {clean_comment}"

    return base_description


def get_default_contribution_date():
    return timezone.localdate()
