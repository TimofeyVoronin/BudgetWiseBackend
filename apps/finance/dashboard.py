from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from apps.finance.models import Account, Transaction, TransactionType


DEFAULT_DASHBOARD_CURRENCY = "RUB"
DEFAULT_DASHBOARD_RECENT_LIMIT = 5
MAX_DASHBOARD_RECENT_LIMIT = 20
DASHBOARD_TOP_CATEGORIES_LIMIT = 5


def build_dashboard_summary(
    *,
    user,
    recent_limit: int = DEFAULT_DASHBOARD_RECENT_LIMIT,
) -> dict:
    today = timezone.localdate()
    date_from = _get_month_start(today)
    date_to = today
    currency = DEFAULT_DASHBOARD_CURRENCY

    accounts_balance = _get_accounts_balance(
        user=user,
        currency=currency,
    )
    income = _get_period_amount(
        user=user,
        currency=currency,
        transaction_type=TransactionType.INCOME,
        date_from=date_from,
        date_to=date_to,
    )
    expense = _get_period_amount(
        user=user,
        currency=currency,
        transaction_type=TransactionType.EXPENSE,
        date_from=date_from,
        date_to=date_to,
    )

    return {
        "period": {
            "date_from": date_from,
            "date_to": date_to,
        },
        "currency": currency,
        "totals": {
            "accounts_balance": _format_money(accounts_balance),
            "income": _format_money(income),
            "expense": _format_money(expense),
            "net": _format_money(income - expense),
        },
        "recent_transactions": _get_recent_transactions(
            user=user,
            currency=currency,
            limit=recent_limit,
        ),
        "top_expense_categories": _get_top_expense_categories(
            user=user,
            currency=currency,
            date_from=date_from,
            date_to=date_to,
        ),
        "reminders": _get_reserved_reminders_block(),
    }


def _get_month_start(value: date) -> date:
    return value.replace(day=1)


def _get_accounts_balance(*, user, currency: str) -> Decimal:
    value = (
        Account.objects
        .filter(
            user=user,
            currency=currency,
            is_active=True,
        )
        .aggregate(total=Sum("balance"))
        .get("total")
    )

    return value or Decimal("0.00")


def _get_period_amount(
    *,
    user,
    currency: str,
    transaction_type: str,
    date_from: date,
    date_to: date,
) -> Decimal:
    value = (
        Transaction.objects
        .filter(
            user=user,
            account__currency=currency,
            type=transaction_type,
            operation_date__gte=date_from,
            operation_date__lte=date_to,
        )
        .aggregate(total=Sum("amount"))
        .get("total")
    )

    return value or Decimal("0.00")


def _get_recent_transactions(*, user, currency: str, limit: int):
    return (
        Transaction.objects
        .filter(
            user=user,
            account__currency=currency,
        )
        .select_related("account", "category")
        .order_by("-operation_date", "-created_at", "-id")[:limit]
    )


def _get_top_expense_categories(
    *,
    user,
    currency: str,
    date_from: date,
    date_to: date,
) -> list[dict]:
    rows = (
        Transaction.objects
        .filter(
            user=user,
            account__currency=currency,
            type=TransactionType.EXPENSE,
            operation_date__gte=date_from,
            operation_date__lte=date_to,
        )
        .values(
            "category_id",
            "category__name",
            "category__icon",
            "category__color",
        )
        .annotate(total=Sum("amount"))
        .order_by("-total", "category__name", "category_id")[
            :DASHBOARD_TOP_CATEGORIES_LIMIT
        ]
    )

    return [
        {
            "category": row["category_id"],
            "category_name": row["category__name"],
            "category_icon": row["category__icon"],
            "category_color": row["category__color"],
            "total": _format_money(row["total"] or Decimal("0.00")),
        }
        for row in rows
    ]


def _get_reserved_reminders_block() -> dict:
    return {
        "title": "Напоминания",
        "headerIcon": "bell",
        "rows": [],
        "footerLinkLabel": "Все напоминания",
    }


def _format_money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01")))