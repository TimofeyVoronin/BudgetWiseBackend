from __future__ import annotations

import hashlib
import json
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from django.core.cache import cache
from django.db.models import Q, Sum
from django.utils import timezone

from apps.finance.currencies import get_user_default_currency_code, get_visible_user_currencies
from apps.finance.models import Account, Goal, GoalStatus, Transaction, TransactionType
from apps.users.app_settings.formatting import get_user_app_today


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


DASHBOARD_WIDGET_PERIOD_TYPES = {
    DASHBOARD_PERIOD_WEEK,
    DASHBOARD_PERIOD_MONTH,
    DASHBOARD_PERIOD_YEAR,
}

DASHBOARD_PERIOD_LABELS = {
    DASHBOARD_PERIOD_WEEK: "Неделя",
    DASHBOARD_PERIOD_MONTH: "Месяц",
    DASHBOARD_PERIOD_YEAR: "Год",
}

DASHBOARD_PREVIOUS_PERIOD_LABELS = {
    DASHBOARD_PERIOD_WEEK: "прошлой неделе",
    DASHBOARD_PERIOD_MONTH: "прошлому месяцу",
    DASHBOARD_PERIOD_YEAR: "прошлому году",
}

DASHBOARD_MONTH_NAMES = {
    1: "Январь",
    2: "Февраль",
    3: "Март",
    4: "Апрель",
    5: "Май",
    6: "Июнь",
    7: "Июль",
    8: "Август",
    9: "Сентябрь",
    10: "Октябрь",
    11: "Ноябрь",
    12: "Декабрь",
}

DASHBOARD_CURRENCY_TITLES = {
    "RUB": "Руб.",
    "USD": "Долл.",
    "EUR": "Евро",
}

DASHBOARD_ACCOUNTS_PREVIEW_LIMIT = 5
DASHBOARD_GOALS_PREVIEW_LIMIT = 5
DASHBOARD_Y_AXIS_LABELS = ["0", "25", "50", "75", "100"]


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

def build_dashboard_period_currency_bar(*, user) -> dict:
    return {
        "defaultPeriod": DEFAULT_DASHBOARD_PERIOD,
        "defaultCurrency": get_user_default_currency_code(user),
        "periodOptions": [
            {
                "value": period,
                "label": DASHBOARD_PERIOD_LABELS[period],
            }
            for period in [
                DASHBOARD_PERIOD_WEEK,
                DASHBOARD_PERIOD_MONTH,
                DASHBOARD_PERIOD_YEAR,
            ]
        ],
        "currencies": [
            {
                "title": DASHBOARD_CURRENCY_TITLES.get(item.code, item.display_name),
                "value": item.code,
            }
            for item in get_visible_user_currencies(user)
        ],
    }


def build_dashboard_balance_summary(
    *,
    user,
    period_type: str = DEFAULT_DASHBOARD_PERIOD,
    currency: str = DEFAULT_DASHBOARD_CURRENCY,
) -> dict:
    normalized_currency = currency.upper()
    today = get_user_app_today(user)
    date_from, date_to = resolve_dashboard_period(
        period_type=period_type,
        today=today,
    )
    previous_date_from, previous_date_to = resolve_previous_dashboard_period(
        period_type=period_type,
        date_from=date_from,
        date_to=date_to,
    )

    balance = _get_accounts_balance(
        user=user,
        currency=normalized_currency,
    )
    current_net = _get_period_net_amount(
        user=user,
        currency=normalized_currency,
        date_from=date_from,
        date_to=date_to,
    )
    previous_net = _get_period_net_amount(
        user=user,
        currency=normalized_currency,
        date_from=previous_date_from,
        date_to=previous_date_to,
    )

    return {
        "title": "Текущий баланс",
        "headerIcon": "wallet",
        "amountRub": _to_number(balance),
        "trendLabel": build_trend_label(
            current_value=current_net,
            previous_value=previous_net,
            period_type=period_type,
        ),
    }


def build_dashboard_accounts_summary(
    *,
    user,
    period_type: str = DEFAULT_DASHBOARD_PERIOD,
    currency: str = DEFAULT_DASHBOARD_CURRENCY,
) -> dict:
    normalized_currency = currency.upper()
    accounts = (
        Account.objects
        .filter(
            user=user,
            currency=normalized_currency,
            is_active=True,
            is_archived=False,
        )
        .order_by("-is_default", "name", "id")[:DASHBOARD_ACCOUNTS_PREVIEW_LIMIT]
    )

    return {
        "title": "Счета",
        "headerIcon": "credit-card",
        "rows": [
            {
                "id": str(account.id),
                "name": account.name,
                "amountRub": _to_number(account.balance),
                "icon": account.icon,
            }
            for account in accounts
        ],
        "footerLinkLabel": "Все счета",
    }


def build_dashboard_goals_summary(
    *,
    user,
    currency: str = DEFAULT_DASHBOARD_CURRENCY,
) -> dict:
    normalized_currency = currency.upper()
    default_currency = get_user_default_currency_code(user)
    queryset = (
        Goal.objects
        .filter(user=user, status=GoalStatus.ACTIVE)
        .select_related("account")
    )

    if normalized_currency == default_currency:
        queryset = queryset.filter(
            Q(account__currency=normalized_currency) | Q(account__isnull=True)
        )
    else:
        queryset = queryset.filter(account__currency=normalized_currency)

    goals = queryset.order_by("deadline", "name", "id")[:DASHBOARD_GOALS_PREVIEW_LIMIT]

    return {
        "title": "Цели",
        "headerIcon": "target",
        "goals": [
            {
                "id": str(goal.id),
                "name": goal.name,
                "targetRub": _to_number(goal.target_amount),
                "currentRub": _to_number(goal.current_amount),
                "percent": _to_number(goal.progress_percent),
            }
            for goal in goals
        ],
    }


def build_dashboard_expense_dynamics(
    *,
    user,
    month: date,
    currency: str = DEFAULT_DASHBOARD_CURRENCY,
) -> dict:
    normalized_currency = currency.upper()
    buckets = build_month_week_buckets(month)
    month_start = buckets[0][0]
    month_end = buckets[-1][1]
    rows = (
        Transaction.objects
        .filter(
            user=user,
            account__currency=normalized_currency,
            operation_date__gte=month_start,
            operation_date__lte=month_end,
        )
        .values("type", "operation_date")
        .annotate(total=Sum("amount"))
    )

    bucket_values = [
        {
            "income": Decimal("0.00"),
            "expenses": Decimal("0.00"),
        }
        for _ in buckets
    ]

    for row in rows:
        bucket_index = get_week_bucket_index(row["operation_date"], buckets)
        if bucket_index is None:
            continue

        total = row["total"] or Decimal("0.00")
        if row["type"] == TransactionType.INCOME:
            bucket_values[bucket_index]["income"] += total
        elif row["type"] == TransactionType.EXPENSE:
            bucket_values[bucket_index]["expenses"] += total

    max_value = max(
        [Decimal("0.00")]
        + [value["income"] for value in bucket_values]
        + [value["expenses"] for value in bucket_values]
    )

    return {
        "title": "Динамика расходов и доходов",
        "headerIcon": "bar-chart-3",
        "monthLabel": DASHBOARD_MONTH_NAMES[month.month],
        "legendIncome": "Доходы",
        "legendExpenses": "Расходы",
        "yAxisLabels": DASHBOARD_Y_AXIS_LABELS,
        "weeks": [
            {
                "label": f"{index + 1} неделя",
                "income": _to_relative_percent(value["income"], max_value),
                "expenses": _to_relative_percent(value["expenses"], max_value),
            }
            for index, value in enumerate(bucket_values)
        ],
    }


def resolve_previous_dashboard_period(
    *,
    period_type: str,
    date_from: date,
    date_to: date,
) -> tuple[date, date]:
    period_days = (date_to - date_from).days + 1

    if period_type == DASHBOARD_PERIOD_WEEK:
        previous_date_to = date_from - timedelta(days=1)
        previous_date_from = previous_date_to - timedelta(days=period_days - 1)
        return previous_date_from, previous_date_to

    if period_type == DASHBOARD_PERIOD_MONTH:
        previous_month_last = date_from - timedelta(days=1)
        return previous_month_last.replace(day=1), previous_month_last

    if period_type == DASHBOARD_PERIOD_YEAR:
        previous_year = date_from.year - 1
        return date(previous_year, 1, 1), date(previous_year, 12, 31)

    previous_date_to = date_from - timedelta(days=1)
    previous_date_from = previous_date_to - timedelta(days=period_days - 1)
    return previous_date_from, previous_date_to


def build_month_week_buckets(month: date) -> list[tuple[date, date]]:
    _, days_in_month = monthrange(month.year, month.month)
    buckets = []

    for day_start in range(1, days_in_month + 1, 7):
        day_end = min(day_start + 6, days_in_month)
        buckets.append(
            (
                date(month.year, month.month, day_start),
                date(month.year, month.month, day_end),
            )
        )

    return buckets


def get_week_bucket_index(
    value: date,
    buckets: list[tuple[date, date]],
) -> int | None:
    for index, (date_from, date_to) in enumerate(buckets):
        if date_from <= value <= date_to:
            return index

    return None


def _get_period_net_amount(
    *,
    user,
    currency: str,
    date_from: date,
    date_to: date,
) -> Decimal:
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
    return income - expense


def build_trend_label(
    *,
    current_value: Decimal,
    previous_value: Decimal,
    period_type: str,
) -> str:
    previous_period_label = DASHBOARD_PREVIOUS_PERIOD_LABELS.get(
        period_type,
        "прошлому периоду",
    )

    if previous_value == Decimal("0.00"):
        if current_value == Decimal("0.00"):
            return "Нет данных для сравнения"
        return f"Новый результат к {previous_period_label}"

    delta_percent = ((current_value - previous_value) / abs(previous_value) * Decimal("100")).quantize(Decimal("0.1"))
    sign = "+" if delta_percent > 0 else ""
    return f"{sign}{delta_percent}% к {previous_period_label}"


def _to_relative_percent(value: Decimal, max_value: Decimal) -> int:
    if max_value <= Decimal("0.00"):
        return 0

    return int((value / max_value * Decimal("100")).quantize(Decimal("1")))


def _to_number(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01")))
