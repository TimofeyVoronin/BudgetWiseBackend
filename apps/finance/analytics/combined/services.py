from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Mapping, Sequence

from django.db.models import Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework.exceptions import ValidationError

from apps.finance.currencies.conversion import (
    CurrencyConversionService,
    get_currency_conversion_service,
)
from apps.finance.currencies.money import quantize_money
from apps.finance.models import Account, Category, Transaction, TransactionType
from apps.users.app_settings.formatting import get_user_app_today


COMBINED_ANALYTICS_PERIOD_WEEK = "week"
COMBINED_ANALYTICS_PERIOD_MONTH = "month"
COMBINED_ANALYTICS_PERIOD_QUARTER = "quarter"
COMBINED_ANALYTICS_PERIOD_YEAR = "year"
COMBINED_ANALYTICS_PERIOD_CUSTOM = "custom"

COMBINED_ANALYTICS_PERIOD_PRESETS = {
    COMBINED_ANALYTICS_PERIOD_WEEK,
    COMBINED_ANALYTICS_PERIOD_MONTH,
    COMBINED_ANALYTICS_PERIOD_QUARTER,
    COMBINED_ANALYTICS_PERIOD_YEAR,
    COMBINED_ANALYTICS_PERIOD_CUSTOM,
}

COMBINED_ANALYTICS_OPERATION_EXPENSE = TransactionType.EXPENSE.value
COMBINED_ANALYTICS_OPERATION_INCOME = TransactionType.INCOME.value
COMBINED_ANALYTICS_OPERATION_TRANSFER = "transfer"

COMBINED_ANALYTICS_OPERATION_TYPES = {
    COMBINED_ANALYTICS_OPERATION_EXPENSE,
    COMBINED_ANALYTICS_OPERATION_INCOME,
    COMBINED_ANALYTICS_OPERATION_TRANSFER,
}

COMBINED_ANALYTICS_EXPORT_FORMATS = {"csv", "xlsx", "pdf"}
COMBINED_ANALYTICS_EXPORT_SECTIONS = {"pie", "bar", "line", "table"}

DEFAULT_COMBINED_ANALYTICS_PERIOD = COMBINED_ANALYTICS_PERIOD_MONTH
DEFAULT_COMBINED_ANALYTICS_OPERATION_TYPE = COMBINED_ANALYTICS_OPERATION_EXPENSE
DEFAULT_COMBINED_ANALYTICS_CURRENCY = "RUB"
DEFAULT_TREND_MONTHS = 6

MONTH_NAMES = {
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


@dataclass(frozen=True)
class CombinedAnalyticsPeriod:
    preset: str
    period_id: str
    date_from: date
    date_to: date
    previous_date_from: date
    previous_date_to: date
    trend_date_from: date
    trend_date_to: date
    period_label: str
    previous_period_label: str
    current_period_label: str


@dataclass(frozen=True)
class CombinedAnalyticsFilters:
    period: CombinedAnalyticsPeriod
    account_ids: list[int]
    category_ids: list[int]
    operation_type: str
    display_currency: str


@dataclass
class CategoryAmount:
    category_id: int
    category_name: str
    category_color: str
    amount: Decimal = Decimal("0.00")


def build_combined_analytics_meta(*, user) -> dict:
    today = get_user_app_today(user)
    period = resolve_combined_analytics_period(
        user=user,
        period_preset=DEFAULT_COMBINED_ANALYTICS_PERIOD,
        period_id=None,
        date_from=None,
        date_to=None,
    )

    active_accounts = list(
        Account.objects
        .filter(user=user, is_active=True, is_archived=False)
        .order_by("-is_default", "name", "id")
    )
    active_categories = list(
        Category.objects
        .filter(user=user, is_active=True, is_archived=False)
        .order_by("type", "parent_id", "sort_order", "name", "id")
    )

    return {
        "period_presets": [
            {"value": COMBINED_ANALYTICS_PERIOD_WEEK, "label": "Неделя"},
            {"value": COMBINED_ANALYTICS_PERIOD_MONTH, "label": "Месяц"},
            {"value": COMBINED_ANALYTICS_PERIOD_QUARTER, "label": "Квартал"},
            {"value": COMBINED_ANALYTICS_PERIOD_YEAR, "label": "Год"},
            {"value": COMBINED_ANALYTICS_PERIOD_CUSTOM, "label": "Произвольный"},
        ],
        "period_options": build_recent_month_options(today),
        "account_options": [
            {"value": "all", "label": "Все"},
            *[
                {"value": str(account.id), "label": account.name}
                for account in active_accounts
            ],
        ],
        "category_options": [
            {"value": "all", "label": "Все"},
            *[
                {"value": str(category.id), "label": category.name}
                for category in active_categories
            ],
        ],
        "type_options": [
            {"value": COMBINED_ANALYTICS_OPERATION_EXPENSE, "label": "Расходы"},
            {"value": COMBINED_ANALYTICS_OPERATION_INCOME, "label": "Доходы"},
            {"value": COMBINED_ANALYTICS_OPERATION_TRANSFER, "label": "Переводы"},
        ],
        "filter_categories": [
            {"id": str(category.id), "label": category.name}
            for category in active_categories
        ],
        "filter_accounts": [
            {"id": str(account.id), "label": account.name}
            for account in active_accounts
        ],
        "export_sections": [
            {"id": "pie", "label": "Включить круговую диаграмму", "icon": "mdi-chart-donut"},
            {"id": "bar", "label": "Включить столбчатую диаграмму", "icon": "mdi-chart-bar"},
            {"id": "line", "label": "Включить линейный график", "icon": "mdi-chart-line"},
            {"id": "table", "label": "Включить таблицу агрегатов", "icon": "mdi-table"},
        ],
        "default_period_id": period.period_id,
        "default_date_from": format_meta_date(period.date_from),
        "default_date_to": format_meta_date(period.date_to),
        "default_account_ids": [],
        "default_category_ids": [],
        "default_operation_type": DEFAULT_COMBINED_ANALYTICS_OPERATION_TYPE,
    }


def build_combined_analytics_aggregates_from_query(*, user, query_params) -> dict:
    filters = build_combined_analytics_filters_from_query(user=user, query_params=query_params)
    converter = get_currency_conversion_service(
        user=user,
        display_currency=filters.display_currency,
    )
    return build_combined_analytics_aggregates(
        user=user,
        filters=filters,
        converter=converter,
    )


def build_combined_analytics_aggregates_from_body(*, user, payload: Mapping[str, object]) -> dict:
    filters = build_combined_analytics_filters_from_body(user=user, payload=payload)
    converter = get_currency_conversion_service(
        user=user,
        display_currency=filters.display_currency,
    )
    return build_combined_analytics_aggregates(
        user=user,
        filters=filters,
        converter=converter,
    )


def build_combined_analytics_filters_from_query(*, user, query_params) -> CombinedAnalyticsFilters:
    period_preset = get_first_query_value(query_params, "period_preset", "periodPreset")
    period_id = get_first_query_value(query_params, "period_id", "periodId")
    date_from = get_date_value(query_params, "date_from", "dateFrom")
    date_to = get_date_value(query_params, "date_to", "dateTo")
    account_ids = parse_repeated_id_values(
        get_repeated_query_values(query_params, "account_ids", "accountIds"),
        field_name="account_ids",
    )
    category_ids = parse_repeated_id_values(
        get_repeated_query_values(query_params, "category_ids", "categoryIds"),
        field_name="category_ids",
    )
    operation_type = normalize_operation_type(
        get_first_query_value(query_params, "operation_type", "operationType")
    )
    display_currency = get_first_query_value(query_params, "currency") or DEFAULT_COMBINED_ANALYTICS_CURRENCY

    return build_combined_analytics_filters(
        user=user,
        period_preset=period_preset,
        period_id=period_id,
        date_from=date_from,
        date_to=date_to,
        account_ids=account_ids,
        category_ids=category_ids,
        operation_type=operation_type,
        display_currency=display_currency,
    )


def build_combined_analytics_filters_from_body(*, user, payload: Mapping[str, object]) -> CombinedAnalyticsFilters:
    period_preset = get_body_value(payload, "period_preset", "periodPreset")
    period_id = get_body_value(payload, "period_id", "periodId")
    date_from = parse_body_date(get_body_value(payload, "date_from", "dateFrom"), "date_from")
    date_to = parse_body_date(get_body_value(payload, "date_to", "dateTo"), "date_to")
    account_ids = parse_repeated_id_values(
        get_body_value(payload, "account_ids", "accountIds") or [],
        field_name="account_ids",
    )
    category_ids = parse_repeated_id_values(
        get_body_value(payload, "category_ids", "categoryIds") or [],
        field_name="category_ids",
    )
    operation_type = normalize_operation_type(
        get_body_value(payload, "operation_type", "operationType")
    )
    display_currency = get_body_value(payload, "currency") or DEFAULT_COMBINED_ANALYTICS_CURRENCY

    return build_combined_analytics_filters(
        user=user,
        period_preset=period_preset,
        period_id=period_id,
        date_from=date_from,
        date_to=date_to,
        account_ids=account_ids,
        category_ids=category_ids,
        operation_type=operation_type,
        display_currency=display_currency,
    )


def build_combined_analytics_filters(
    *,
    user,
    period_preset: str | None,
    period_id: str | None,
    date_from: date | None,
    date_to: date | None,
    account_ids: list[int] | None,
    category_ids: list[int] | None,
    operation_type: str | None,
    display_currency: str | None,
) -> CombinedAnalyticsFilters:
    period = resolve_combined_analytics_period(
        user=user,
        period_preset=period_preset,
        period_id=period_id,
        date_from=date_from,
        date_to=date_to,
    )
    resolved_account_ids = account_ids or []
    resolved_category_ids = category_ids or []

    validate_user_account_ids(user=user, account_ids=resolved_account_ids)
    validate_user_category_ids(user=user, category_ids=resolved_category_ids)

    return CombinedAnalyticsFilters(
        period=period,
        account_ids=resolved_account_ids,
        category_ids=resolved_category_ids,
        operation_type=operation_type or DEFAULT_COMBINED_ANALYTICS_OPERATION_TYPE,
        display_currency=(display_currency or DEFAULT_COMBINED_ANALYTICS_CURRENCY).strip().upper(),
    )


def build_combined_analytics_aggregates(
    *,
    user,
    filters: CombinedAnalyticsFilters,
    converter: CurrencyConversionService,
) -> dict:
    period = filters.period

    current_category_amounts = get_category_amounts(
        user=user,
        date_from=period.date_from,
        date_to=period.date_to,
        account_ids=filters.account_ids,
        category_ids=filters.category_ids,
        operation_type=filters.operation_type,
        converter=converter,
    )
    previous_category_amounts = get_category_amounts(
        user=user,
        date_from=period.previous_date_from,
        date_to=period.previous_date_to,
        account_ids=filters.account_ids,
        category_ids=filters.category_ids,
        operation_type=filters.operation_type,
        converter=converter,
    )

    pie_slices = build_pie_slices(current_category_amounts)
    aggregate_rows = build_aggregate_rows(pie_slices)
    bar_groups = build_bar_groups(
        current_amounts=current_category_amounts,
        previous_amounts=previous_category_amounts,
    )
    line_points = build_line_points(
        user=user,
        date_from=period.trend_date_from,
        date_to=period.trend_date_to,
        account_ids=filters.account_ids,
        category_ids=filters.category_ids,
        operation_type=filters.operation_type,
        converter=converter,
    )
    totals = get_total_amounts(
        user=user,
        date_from=period.date_from,
        date_to=period.date_to,
        account_ids=filters.account_ids,
        category_ids=filters.category_ids,
        operation_type=filters.operation_type,
        converter=converter,
    )

    has_data = bool(pie_slices) or any(
        point["income_rub"] or point["expense_rub"]
        for point in line_points
    )

    return {
        "has_data": has_data,
        "period_label": period.period_label,
        "total_expense_rub": decimal_to_number(totals[COMBINED_ANALYTICS_OPERATION_EXPENSE]),
        "total_income_rub": decimal_to_number(totals[COMBINED_ANALYTICS_OPERATION_INCOME]),
        "pie_slices": pie_slices,
        "bar_groups": bar_groups,
        "bar_legend": {
            "previous_period_label": period.previous_period_label,
            "current_period_label": period.current_period_label,
        },
        "line_points": line_points,
        "aggregate_rows": aggregate_rows,
    }


def get_category_amounts(
    *,
    user,
    date_from: date,
    date_to: date,
    account_ids: Sequence[int],
    category_ids: Sequence[int],
    operation_type: str,
    converter: CurrencyConversionService,
) -> dict[int, CategoryAmount]:
    if operation_type == COMBINED_ANALYTICS_OPERATION_TRANSFER:
        return {}

    rows = (
        build_transaction_queryset(
            user=user,
            date_from=date_from,
            date_to=date_to,
            account_ids=account_ids,
            category_ids=category_ids,
            operation_types=[operation_type],
        )
        .values(
            "category_id",
            "category__name",
            "category__color",
            "account__currency",
        )
        .annotate(total_amount=Sum("amount"))
        .order_by()
    )

    amounts: dict[int, CategoryAmount] = {}

    for row in rows:
        category_id = row["category_id"]
        converted_amount = converter.convert_to_display(
            row["total_amount"] or Decimal("0.00"),
            source_currency=row["account__currency"],
        ).amount
        category_amount = amounts.setdefault(
            category_id,
            CategoryAmount(
                category_id=category_id,
                category_name=row["category__name"] or "Без категории",
                category_color=row["category__color"] or "#64748B",
            ),
        )
        category_amount.amount += converted_amount

    return amounts


def get_total_amounts(
    *,
    user,
    date_from: date,
    date_to: date,
    account_ids: Sequence[int],
    category_ids: Sequence[int],
    operation_type: str,
    converter: CurrencyConversionService,
) -> dict[str, Decimal]:
    if operation_type == COMBINED_ANALYTICS_OPERATION_TRANSFER:
        return {
            COMBINED_ANALYTICS_OPERATION_INCOME: Decimal("0.00"),
            COMBINED_ANALYTICS_OPERATION_EXPENSE: Decimal("0.00"),
        }

    rows = (
        build_transaction_queryset(
            user=user,
            date_from=date_from,
            date_to=date_to,
            account_ids=account_ids,
            category_ids=category_ids,
            operation_types=[operation_type],
        )
        .values("type", "account__currency")
        .annotate(total_amount=Sum("amount"))
        .order_by()
    )

    totals = {
        COMBINED_ANALYTICS_OPERATION_INCOME: Decimal("0.00"),
        COMBINED_ANALYTICS_OPERATION_EXPENSE: Decimal("0.00"),
    }

    for row in rows:
        transaction_type = row["type"]
        if transaction_type not in totals:
            continue

        converted_amount = converter.convert_to_display(
            row["total_amount"] or Decimal("0.00"),
            source_currency=row["account__currency"],
        ).amount
        totals[transaction_type] += converted_amount

    return totals


def build_line_points(
    *,
    user,
    date_from: date,
    date_to: date,
    account_ids: Sequence[int],
    category_ids: Sequence[int],
    operation_type: str,
    converter: CurrencyConversionService,
) -> list[dict]:
    months = get_month_range(date_from, date_to)
    points_by_month: dict[str, dict[str, Decimal]] = {
        month_key: {
            COMBINED_ANALYTICS_OPERATION_INCOME: Decimal("0.00"),
            COMBINED_ANALYTICS_OPERATION_EXPENSE: Decimal("0.00"),
        }
        for month_key in months
    }

    if operation_type == COMBINED_ANALYTICS_OPERATION_TRANSFER:
        return [build_line_point(month_key, values) for month_key, values in points_by_month.items()]

    rows = (
        build_transaction_queryset(
            user=user,
            date_from=date_from,
            date_to=date_to,
            account_ids=account_ids,
            category_ids=category_ids,
            operation_types=[operation_type],
        )
        .annotate(month=TruncMonth("operation_date"))
        .values("month", "type", "account__currency")
        .annotate(total_amount=Sum("amount"))
        .order_by()
    )

    for row in rows:
        month_value = row["month"]
        if isinstance(month_value, str):
            month_date = parse_date(month_value[:10])
        elif hasattr(month_value, "date"):
            month_date = month_value.date()
        else:
            month_date = month_value

        if month_date is None:
            continue

        month_key = f"{month_date.year:04d}-{month_date.month:02d}"
        transaction_type = row["type"]

        if month_key not in points_by_month or transaction_type not in points_by_month[month_key]:
            continue

        converted_amount = converter.convert_to_display(
            row["total_amount"] or Decimal("0.00"),
            source_currency=row["account__currency"],
        ).amount
        points_by_month[month_key][transaction_type] += converted_amount

    return [
        build_line_point(month_key, values)
        for month_key, values in points_by_month.items()
    ]


def build_line_point(month_key: str, values: Mapping[str, Decimal]) -> dict:
    income = quantize_money(values[COMBINED_ANALYTICS_OPERATION_INCOME])
    expense = quantize_money(values[COMBINED_ANALYTICS_OPERATION_EXPENSE])
    balance = quantize_money(income - expense)

    return {
        "month": month_key,
        "label": get_month_label_from_key(month_key),
        "income_rub": decimal_to_number(income),
        "expense_rub": decimal_to_number(expense),
        "balance_rub": decimal_to_number(balance),
    }


def build_pie_slices(amounts: Mapping[int, CategoryAmount]) -> list[dict]:
    total_amount = sum((item.amount for item in amounts.values()), Decimal("0.00"))

    if total_amount <= 0:
        return []

    slices = []
    for item in sorted(amounts.values(), key=lambda value: (-value.amount, value.category_name)):
        amount = quantize_money(item.amount)
        percent = (amount / total_amount * Decimal("100")).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
        slices.append(
            {
                "category_id": str(item.category_id),
                "category_name": item.category_name,
                "category_color": item.category_color,
                "amount_rub": decimal_to_number(amount),
                "percent": decimal_to_number(percent),
            }
        )

    return slices


def build_aggregate_rows(pie_slices: Sequence[Mapping[str, object]]) -> list[dict]:
    return [
        {
            "category_id": str(slice_item["category_id"]),
            "category_name": str(slice_item["category_name"]),
            "amount_rub": slice_item["amount_rub"],
            "percent": slice_item["percent"],
        }
        for slice_item in pie_slices
    ]


def build_bar_groups(
    *,
    current_amounts: Mapping[int, CategoryAmount],
    previous_amounts: Mapping[int, CategoryAmount],
) -> list[dict]:
    category_ids = set(current_amounts) | set(previous_amounts)
    groups = []

    for category_id in category_ids:
        current_amount = current_amounts.get(category_id)
        previous_amount = previous_amounts.get(category_id)
        category_name = (
            current_amount.category_name
            if current_amount is not None
            else previous_amount.category_name
        )
        current_value = current_amount.amount if current_amount else Decimal("0.00")
        previous_value = previous_amount.amount if previous_amount else Decimal("0.00")

        groups.append(
            {
                "category_id": str(category_id),
                "category_name": category_name,
                "previous_period_amount_rub": decimal_to_number(quantize_money(previous_value)),
                "current_period_amount_rub": decimal_to_number(quantize_money(current_value)),
            }
        )

    return sorted(
        groups,
        key=lambda item: (-item["current_period_amount_rub"], item["category_name"]),
    )


def build_transaction_queryset(
    *,
    user,
    date_from: date,
    date_to: date,
    account_ids: Sequence[int],
    category_ids: Sequence[int],
    operation_types: Sequence[str] | None = None,
):
    queryset = (
        Transaction.objects
        .filter(
            user=user,
            operation_date__gte=date_from,
            operation_date__lte=date_to,
        )
        .select_related("account", "category")
    )

    if operation_types:
        queryset = queryset.filter(type__in=operation_types)

    if account_ids:
        queryset = queryset.filter(account_id__in=account_ids)

    if category_ids:
        queryset = queryset.filter(category_id__in=category_ids)

    return queryset


def resolve_combined_analytics_period(
    *,
    user,
    period_preset: str | None,
    period_id: str | None,
    date_from: date | None,
    date_to: date | None,
) -> CombinedAnalyticsPeriod:
    preset = (period_preset or DEFAULT_COMBINED_ANALYTICS_PERIOD).strip().lower()
    if preset not in COMBINED_ANALYTICS_PERIOD_PRESETS:
        raise ValidationError(
            {"period_preset": ["Допустимые значения: week, month, quarter, year, custom."]}
        )

    today = get_user_app_today(user)
    period_id = (period_id or "").strip()

    if preset == COMBINED_ANALYTICS_PERIOD_CUSTOM:
        if date_from is None or date_to is None:
            raise ValidationError({"date_from": ["Для custom периода укажите date_from и date_to."]})
        resolved_from, resolved_to = date_from, date_to
    elif period_id:
        resolved_from, resolved_to = resolve_period_id_range(
            preset=preset,
            period_id=period_id,
            today=today,
        )
    elif date_from is not None and date_to is not None:
        resolved_from, resolved_to = date_from, date_to
    else:
        resolved_from, resolved_to = resolve_default_period_range(
            preset=preset,
            today=today,
        )

    if resolved_from > resolved_to:
        raise ValidationError({"date_from": ["date_from не может быть позже date_to."]})

    previous_from, previous_to = resolve_previous_period_range(
        preset=preset,
        date_from=resolved_from,
        date_to=resolved_to,
    )
    trend_from, trend_to = resolve_trend_period_range(
        date_from=resolved_from,
        date_to=resolved_to,
    )

    current_period_id = period_id or build_period_id(preset, resolved_from)

    return CombinedAnalyticsPeriod(
        preset=preset,
        period_id=current_period_id,
        date_from=resolved_from,
        date_to=resolved_to,
        previous_date_from=previous_from,
        previous_date_to=previous_to,
        trend_date_from=trend_from,
        trend_date_to=trend_to,
        period_label=format_period_label(resolved_from, resolved_to, preset=preset),
        previous_period_label=format_period_label(previous_from, previous_to, preset=preset),
        current_period_label=format_period_label(resolved_from, resolved_to, preset=preset),
    )


def resolve_period_id_range(*, preset: str, period_id: str, today: date) -> tuple[date, date]:
    if preset == COMBINED_ANALYTICS_PERIOD_MONTH:
        match = re.fullmatch(r"(\d{4})-(\d{2})", period_id)
        if not match:
            raise ValidationError({"period_id": ["Для month используйте формат YYYY-MM."]})
        year = int(match.group(1))
        month = int(match.group(2))
        return get_month_bounds(year, month)

    if preset == COMBINED_ANALYTICS_PERIOD_QUARTER:
        match = re.fullmatch(r"(\d{4})-(?:Q)?([1-4])", period_id, flags=re.IGNORECASE)
        if not match:
            raise ValidationError({"period_id": ["Для quarter используйте формат YYYY-Q1."]})
        year = int(match.group(1))
        quarter = int(match.group(2))
        first_month = (quarter - 1) * 3 + 1
        first_day = date(year, first_month, 1)
        last_month = first_month + 2
        last_day = date(year, last_month, calendar.monthrange(year, last_month)[1])
        return first_day, last_day

    if preset == COMBINED_ANALYTICS_PERIOD_YEAR:
        match = re.fullmatch(r"(\d{4})", period_id)
        if not match:
            raise ValidationError({"period_id": ["Для year используйте формат YYYY."]})
        year = int(match.group(1))
        return date(year, 1, 1), date(year, 12, 31)

    if preset == COMBINED_ANALYTICS_PERIOD_WEEK:
        match = re.fullmatch(r"(\d{4})-W(\d{2})", period_id, flags=re.IGNORECASE)
        if not match:
            raise ValidationError({"period_id": ["Для week используйте формат YYYY-Www, например 2026-W23."]})
        year = int(match.group(1))
        week = int(match.group(2))
        try:
            start = date.fromisocalendar(year, week, 1)
        except ValueError as exc:
            raise ValidationError({"period_id": ["Некорректный номер недели."]}) from exc
        return start, start + timedelta(days=6)

    return resolve_default_period_range(preset=preset, today=today)


def resolve_default_period_range(*, preset: str, today: date) -> tuple[date, date]:
    if preset == COMBINED_ANALYTICS_PERIOD_WEEK:
        start = today - timedelta(days=today.weekday())
        return start, start + timedelta(days=6)

    if preset == COMBINED_ANALYTICS_PERIOD_MONTH:
        return get_month_bounds(today.year, today.month)

    if preset == COMBINED_ANALYTICS_PERIOD_QUARTER:
        quarter = (today.month - 1) // 3 + 1
        first_month = (quarter - 1) * 3 + 1
        first_day = date(today.year, first_month, 1)
        last_month = first_month + 2
        return first_day, date(today.year, last_month, calendar.monthrange(today.year, last_month)[1])

    if preset == COMBINED_ANALYTICS_PERIOD_YEAR:
        return date(today.year, 1, 1), date(today.year, 12, 31)

    return get_month_bounds(today.year, today.month)


def resolve_previous_period_range(*, preset: str, date_from: date, date_to: date) -> tuple[date, date]:
    if preset == COMBINED_ANALYTICS_PERIOD_MONTH:
        previous_month = add_months(date_from.replace(day=1), -1)
        return get_month_bounds(previous_month.year, previous_month.month)

    if preset == COMBINED_ANALYTICS_PERIOD_QUARTER:
        previous_start = add_months(date_from.replace(day=1), -3)
        previous_end_month = add_months(previous_start, 2)
        return previous_start, date(
            previous_end_month.year,
            previous_end_month.month,
            calendar.monthrange(previous_end_month.year, previous_end_month.month)[1],
        )

    if preset == COMBINED_ANALYTICS_PERIOD_YEAR:
        previous_year = date_from.year - 1
        return date(previous_year, 1, 1), date(previous_year, 12, 31)

    if preset == COMBINED_ANALYTICS_PERIOD_WEEK:
        previous_start = date_from - timedelta(days=7)
        return previous_start, previous_start + timedelta(days=6)

    period_length = (date_to - date_from).days + 1
    previous_to = date_from - timedelta(days=1)
    previous_from = previous_to - timedelta(days=period_length - 1)
    return previous_from, previous_to


def resolve_trend_period_range(*, date_from: date, date_to: date) -> tuple[date, date]:
    start_month = date_from.replace(day=1)
    end_month = date_to.replace(day=1)
    month_count = get_month_distance(start_month, end_month) + 1

    if month_count <= 1:
        start_month = add_months(end_month, -(DEFAULT_TREND_MONTHS - 1))

    trend_to = date(end_month.year, end_month.month, calendar.monthrange(end_month.year, end_month.month)[1])
    return start_month, trend_to


def build_recent_month_options(today: date, *, months_count: int = 12) -> list[dict[str, str]]:
    current_month = today.replace(day=1)
    options = []

    for offset in range(months_count):
        month = add_months(current_month, -offset)
        value = f"{month.year:04d}-{month.month:02d}"
        options.append({"value": value, "label": get_month_label(month.year, month.month)})

    return options


def get_month_bounds(year: int, month: int) -> tuple[date, date]:
    if month < 1 or month > 12:
        raise ValidationError({"period_id": ["Месяц должен быть от 1 до 12."]})
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def get_month_distance(start_month: date, end_month: date) -> int:
    return (end_month.year - start_month.year) * 12 + end_month.month - start_month.month


def get_month_range(date_from: date, date_to: date) -> dict[str, date]:
    current = date_from.replace(day=1)
    end = date_to.replace(day=1)
    result: dict[str, date] = {}

    while current <= end:
        result[f"{current.year:04d}-{current.month:02d}"] = current
        current = add_months(current, 1)

    return result


def build_period_id(preset: str, date_from: date) -> str:
    if preset == COMBINED_ANALYTICS_PERIOD_WEEK:
        iso_year, iso_week, _ = date_from.isocalendar()
        return f"{iso_year:04d}-W{iso_week:02d}"

    if preset == COMBINED_ANALYTICS_PERIOD_MONTH:
        return f"{date_from.year:04d}-{date_from.month:02d}"

    if preset == COMBINED_ANALYTICS_PERIOD_QUARTER:
        quarter = (date_from.month - 1) // 3 + 1
        return f"{date_from.year:04d}-Q{quarter}"

    if preset == COMBINED_ANALYTICS_PERIOD_YEAR:
        return f"{date_from.year:04d}"

    return f"{date_from.isoformat()}_{timezone.localdate().isoformat()}"


def format_period_label(date_from: date, date_to: date, *, preset: str) -> str:
    if date_from == date_to:
        return format_meta_date(date_from)

    if preset == COMBINED_ANALYTICS_PERIOD_MONTH and date_from.day == 1 and is_month_end(date_to):
        return get_month_label(date_from.year, date_from.month)

    if preset == COMBINED_ANALYTICS_PERIOD_QUARTER:
        quarter = (date_from.month - 1) // 3 + 1
        return f"{quarter} квартал {date_from.year}"

    if preset == COMBINED_ANALYTICS_PERIOD_YEAR and date_from.month == 1 and date_to.month == 12:
        return f"{date_from.year} год"

    return f"{format_meta_date(date_from)} - {format_meta_date(date_to)}"


def get_month_label(year: int, month: int) -> str:
    return f"{MONTH_NAMES.get(month, str(month))} {year}"


def get_month_label_from_key(month_key: str) -> str:
    year, month = month_key.split("-", maxsplit=1)
    return get_month_label(int(year), int(month))


def is_month_end(value: date) -> bool:
    return value.day == calendar.monthrange(value.year, value.month)[1]


def format_meta_date(value: date) -> str:
    return value.strftime("%d.%m.%Y")


def get_repeated_query_values(query_params, *names: str) -> list[str]:
    values: list[str] = []
    for name in names:
        if hasattr(query_params, "getlist"):
            values.extend(query_params.getlist(name))
        else:
            value = query_params.get(name)
            if value not in (None, ""):
                values.append(value)
    return values


def get_first_query_value(query_params, *names: str) -> str | None:
    for name in names:
        value = query_params.get(name)
        if value not in (None, ""):
            return value
    return None


def get_body_value(payload: Mapping[str, object], *names: str):
    for name in names:
        value = payload.get(name)
        if value not in (None, ""):
            return value
    return None


def get_date_value(query_params, *names: str) -> date | None:
    raw_value = get_first_query_value(query_params, *names)
    return parse_body_date(raw_value, names[0])


def parse_body_date(value, field_name: str) -> date | None:
    if value in (None, ""):
        return None

    if isinstance(value, date):
        return value

    parsed = parse_date(str(value))
    if parsed is None:
        raise ValidationError({field_name: ["Дата должна быть в формате YYYY-MM-DD."]})

    return parsed


def parse_repeated_id_values(values, *, field_name: str) -> list[int]:
    if values in (None, ""):
        return []

    if isinstance(values, (str, int)):
        iterable_values = [values]
    else:
        iterable_values = list(values)

    result: list[int] = []
    for value in iterable_values:
        if value in (None, "", "all"):
            continue

        if isinstance(value, str):
            parts = [part.strip() for part in value.split(",")]
        else:
            parts = [value]

        for part in parts:
            if part in (None, "", "all"):
                continue
            try:
                result.append(int(part))
            except (TypeError, ValueError) as exc:
                raise ValidationError({field_name: ["ID должен быть целым числом."]}) from exc

    return sorted(set(result))


def validate_user_account_ids(*, user, account_ids: Sequence[int]) -> None:
    if not account_ids:
        return

    existing_ids = set(
        Account.objects
        .filter(user=user, id__in=account_ids)
        .values_list("id", flat=True)
    )
    missing_ids = sorted(set(account_ids) - existing_ids)

    if missing_ids:
        raise ValidationError({"account_ids": ["Некорректные id счетов."]})


def validate_user_category_ids(*, user, category_ids: Sequence[int]) -> None:
    if not category_ids:
        return

    existing_ids = set(
        Category.objects
        .filter(user=user, id__in=category_ids)
        .values_list("id", flat=True)
    )
    missing_ids = sorted(set(category_ids) - existing_ids)

    if missing_ids:
        raise ValidationError({"category_ids": ["Некорректные id категорий."]})


def normalize_operation_type(value: str | None) -> str:
    if value in (None, "", "all"):
        return DEFAULT_COMBINED_ANALYTICS_OPERATION_TYPE

    normalized_value = str(value).strip().lower()
    if normalized_value not in COMBINED_ANALYTICS_OPERATION_TYPES:
        allowed_values = ", ".join(sorted(COMBINED_ANALYTICS_OPERATION_TYPES))
        raise ValidationError({"operation_type": [f"Допустимые значения: {allowed_values}."]})

    return normalized_value


def normalize_export_format(value: str | None) -> str:
    export_format = str(value or "").strip().lower()
    if export_format not in COMBINED_ANALYTICS_EXPORT_FORMATS:
        raise ValidationError({"format": ["Формат экспорта должен быть pdf, csv или xlsx."]})
    return export_format


def normalize_export_sections(values: Iterable[str] | str | None) -> list[str]:
    if not values:
        raise ValidationError({"sections": ["Выберите хотя бы одну секцию экспорта."]})

    if isinstance(values, str):
        iterable_values = [part.strip() for part in values.split(",")]
    else:
        iterable_values = values

    sections = []
    for value in iterable_values:
        section = str(value or "").strip().lower()
        if not section:
            continue
        if section not in COMBINED_ANALYTICS_EXPORT_SECTIONS:
            allowed_values = ", ".join(sorted(COMBINED_ANALYTICS_EXPORT_SECTIONS))
            raise ValidationError({"sections": [f"Допустимые значения: {allowed_values}."]})
        if section not in sections:
            sections.append(section)

    if not sections:
        raise ValidationError({"sections": ["Выберите хотя бы одну секцию экспорта."]})

    return sections


def decimal_to_number(value) -> float:
    return float(quantize_money(Decimal(value or "0.00")))
