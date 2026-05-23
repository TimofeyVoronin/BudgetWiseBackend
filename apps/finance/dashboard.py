from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from decimal import Decimal

from django.core.cache import cache
from django.db.models import Sum
from django.utils import timezone

from apps.finance.models import Account, Transaction, TransactionType
from apps.users.app_settings_formatting import get_user_app_today


DASHBOARD_PERIOD_WEEK = "week"
DASHBOARD_PERIOD_MONTH = "month"
DASHBOARD_PERIOD_YEAR = "year"
DASHBOARD_PERIOD_CUSTOM = "custom"

DASHBOARD_PERIOD_TYPES = {
    DASHBOARD_PERIOD_WEEK,
    DASHBOARD_PERIOD_MONTH,
    DASHBOARD_PERIOD_YEAR,
    DASHBOARD_PERIOD_CUSTOM,
}

DEFAULT_DASHBOARD_PERIOD = DASHBOARD_PERIOD_MONTH
DEFAULT_DASHBOARD_CURRENCY = "RUB"
DEFAULT_DASHBOARD_RECENT_LIMIT = 5
MAX_DASHBOARD_RECENT_LIMIT = 20
DASHBOARD_TOP_CATEGORIES_LIMIT = 5
DASHBOARD_SUMMARY_CACHE_TIMEOUT = 60


def get_cached_dashboard_summary(
    *,
    user,
    period_type: str = DEFAULT_DASHBOARD_PERIOD,
    date_from: date | None = None,
    date_to: date | None = None,
    currency: str = DEFAULT_DASHBOARD_CURRENCY,
    recent_limit: int = DEFAULT_DASHBOARD_RECENT_LIMIT,
    tag_ids: list[int] | None = None,
) -> dict:
    cache_key = build_dashboard_summary_cache_key(
        user_id=user.id,
        period_type=period_type,
        date_from=date_from,
        date_to=date_to,
        currency=currency,
        recent_limit=recent_limit,
        tag_ids=tag_ids,
    )
    cached_value = cache.get(cache_key)

    if cached_value is not None:
        return cached_value

    dashboard_data = build_dashboard_summary(
        user=user,
        period_type=period_type,
        date_from=date_from,
        date_to=date_to,
        currency=currency,
        recent_limit=recent_limit,
        tag_ids=tag_ids,
    )
    cache.set(
        cache_key,
        dashboard_data,
        timeout=DASHBOARD_SUMMARY_CACHE_TIMEOUT,
    )

    return dashboard_data


def build_dashboard_summary(
    *,
    user,
    period_type: str = DEFAULT_DASHBOARD_PERIOD,
    date_from: date | None = None,
    date_to: date | None = None,
    currency: str = DEFAULT_DASHBOARD_CURRENCY,
    recent_limit: int = DEFAULT_DASHBOARD_RECENT_LIMIT,
    tag_ids: list[int] | None = None,
) -> dict:
    resolved_date_from, resolved_date_to = resolve_dashboard_period(
        period_type=period_type,
        date_from=date_from,
        date_to=date_to,
        today=get_user_app_today(user),
    )
    normalized_currency = currency.upper()

    accounts_balance = _get_accounts_balance(
        user=user,
        currency=normalized_currency,
    )
    income = _get_period_amount(
        user=user,
        currency=normalized_currency,
        transaction_type=TransactionType.INCOME,
        date_from=resolved_date_from,
        date_to=resolved_date_to,
        tag_ids=tag_ids,
    )
    expense = _get_period_amount(
        user=user,
        currency=normalized_currency,
        transaction_type=TransactionType.EXPENSE,
        date_from=resolved_date_from,
        date_to=resolved_date_to,
        tag_ids=tag_ids,
    )

    return {
        "period": {
            "type": period_type,
            "date_from": resolved_date_from,
            "date_to": resolved_date_to,
        },
        "currency": normalized_currency,
        "totals": {
            "accounts_balance": _format_money(accounts_balance),
            "income": _format_money(income),
            "expense": _format_money(expense),
            "net": _format_money(income - expense),
        },
        "recent_transactions": _get_recent_transactions(
            user=user,
            currency=normalized_currency,
            limit=recent_limit,
            tag_ids=tag_ids,
        ),
        "top_expense_categories": _get_top_expense_categories(
            user=user,
            currency=normalized_currency,
            date_from=resolved_date_from,
            date_to=resolved_date_to,
            tag_ids=tag_ids,
        ),
        "reminders": _get_reserved_reminders_block(),
    }


def resolve_dashboard_period(
    *,
    period_type: str,
    date_from: date | None = None,
    date_to: date | None = None,
    today: date | None = None,
) -> tuple[date, date]:
    today = today or timezone.localdate()

    if period_type == DASHBOARD_PERIOD_WEEK:
        week_start = today - timedelta(days=today.weekday())
        return week_start, today

    if period_type == DASHBOARD_PERIOD_MONTH:
        return today.replace(day=1), today

    if period_type == DASHBOARD_PERIOD_YEAR:
        return today.replace(month=1, day=1), today

    if period_type == DASHBOARD_PERIOD_CUSTOM:
        if date_from is None or date_to is None:
            raise ValueError(
                "Для периода custom нужно указать date_from и date_to."
            )

        return date_from, date_to

    raise ValueError("Недопустимый период dashboard.")


def _get_accounts_balance(*, user, currency: str) -> Decimal:
    value = (
        Account.objects
        .filter(
            user=user,
            currency=currency,
            is_active=True,
            is_archived=False,
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
    tag_ids: list[int] | None = None,
) -> Decimal:
    queryset = Transaction.objects.filter(
        user=user,
        account__currency=currency,
        type=transaction_type,
        operation_date__gte=date_from,
        operation_date__lte=date_to,
    )

    queryset = _filter_transactions_by_tags(queryset, tag_ids)

    value = queryset.aggregate(total=Sum("amount")).get("total")

    return value or Decimal("0.00")


def _get_recent_transactions(
    *,
    user,
    currency: str,
    limit: int,
    tag_ids: list[int] | None = None,
):
    queryset = (
        Transaction.objects
        .filter(
            user=user,
            account__currency=currency,
        )
        .select_related("account", "category")
        .prefetch_related("tags__group")
    )

    queryset = _filter_transactions_by_tags(queryset, tag_ids)

    return queryset.order_by("-operation_date", "-created_at", "-id")[:limit]


def _get_top_expense_categories(
    *,
    user,
    currency: str,
    date_from: date,
    date_to: date,
    tag_ids: list[int] | None = None,
) -> list[dict]:
    queryset = Transaction.objects.filter(
        user=user,
        account__currency=currency,
        type=TransactionType.EXPENSE,
        operation_date__gte=date_from,
        operation_date__lte=date_to,
    )

    queryset = _filter_transactions_by_tags(queryset, tag_ids)

    rows = (
        queryset
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



def _filter_transactions_by_tags(queryset, tag_ids: list[int] | None):
    if not tag_ids:
        return queryset

    return queryset.filter(tags__id__in=tag_ids).distinct()

def _get_reserved_reminders_block() -> dict:
    return {
        "title": "Напоминания",
        "headerIcon": "bell",
        "rows": [],
        "footerLinkLabel": "Все напоминания",
    }


def _format_money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01")))


def build_dashboard_summary_cache_key(
    *,
    user_id: int,
    period_type: str,
    date_from: date | None,
    date_to: date | None,
    currency: str,
    recent_limit: int,
    tag_ids: list[int] | None = None,
) -> str:
    payload = {
        "user_id": user_id,
        "period_type": period_type,
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
        "currency": currency.upper(),
        "recent_limit": recent_limit,
        "tag_ids": sorted(tag_ids or []),
    }
    raw_key = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    return f"dashboard:summary:{digest}"