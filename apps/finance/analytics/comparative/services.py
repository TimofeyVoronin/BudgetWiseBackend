from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Mapping, Sequence

from django.db.models import Sum
from django.db.models.functions import TruncMonth
from rest_framework.exceptions import ValidationError

from apps.finance.analytics.combined.services import (
    MONTH_NAMES,
    add_months,
    decimal_to_number,
    get_body_value,
    get_first_query_value,
    get_month_bounds,
    get_month_label,
    get_month_range,
    get_repeated_query_values,
)
from apps.finance.currencies.conversion import (
    CurrencyConversionService,
    get_currency_conversion_service,
)
from apps.finance.currencies.money import quantize_money
from apps.finance.models import Account, Category, Transaction, TransactionType
from apps.users.app_settings.formatting import get_user_app_today

COMPARATIVE_TYPE_PERIODS = "periods"
COMPARATIVE_TYPE_CATEGORIES = "categories"
COMPARATIVE_TYPE_ACCOUNTS = "accounts"
COMPARATIVE_TYPES = {
    COMPARATIVE_TYPE_PERIODS,
    COMPARATIVE_TYPE_CATEGORIES,
    COMPARATIVE_TYPE_ACCOUNTS,
}

COMPARATIVE_METRIC_INCOME = "income"
COMPARATIVE_METRIC_EXPENSE = "expense"
COMPARATIVE_METRIC_BALANCE = "balance"
COMPARATIVE_METRICS = {
    COMPARATIVE_METRIC_INCOME,
    COMPARATIVE_METRIC_EXPENSE,
    COMPARATIVE_METRIC_BALANCE,
}

COMPARATIVE_EXPORT_FORMATS = {"csv", "xlsx", "pdf"}
COMPARATIVE_EXPORT_SECTIONS = {"legend", "differences", "charts"}

DEFAULT_COMPARISON_TYPE = COMPARATIVE_TYPE_PERIODS
DEFAULT_METRIC = COMPARATIVE_METRIC_INCOME
DEFAULT_MAX_ENTITIES = 5
DEFAULT_DISPLAY_CURRENCY = "RUB"
DEFAULT_EXPORT_SECTIONS = ["legend", "differences", "charts"]

METRIC_LABELS = {
    COMPARATIVE_METRIC_INCOME: "Доходы, ₽",
    COMPARATIVE_METRIC_EXPENSE: "Расходы, ₽",
    COMPARATIVE_METRIC_BALANCE: "Прибыль, ₽",
}

METRIC_SHORT_LABELS = {
    COMPARATIVE_METRIC_INCOME: "Доходы",
    COMPARATIVE_METRIC_EXPENSE: "Расходы",
    COMPARATIVE_METRIC_BALANCE: "Сальдо",
}

ENTITY_COLORS = [
    "#F97316",
    "#EAB308",
    "#10B981",
    "#3B82F6",
    "#8B5CF6",
]


@dataclass(frozen=True)
class ComparativeAnalyticsFilters:
    comparison_type: str
    year: int
    metric: str
    entity_ids: list[str]
    convert_to_rub: bool
    display_currency: str = DEFAULT_DISPLAY_CURRENCY


@dataclass(frozen=True)
class ComparativeEntityContext:
    id: str
    label: str
    subtitle: str
    color: str
    currency_code: str
    has_data: bool
    stats: dict[str, Decimal]


class EntityScope:
    def __init__(
        self,
        *,
        date_from: date,
        date_to: date,
        account_ids: Sequence[int] | None = None,
        category_ids: Sequence[int] | None = None,
    ) -> None:
        self.date_from = date_from
        self.date_to = date_to
        self.account_ids = list(account_ids or [])
        self.category_ids = list(category_ids or [])


def build_comparative_analytics_meta(*, user) -> dict:
    today = get_user_app_today(user)
    default_year = today.year
    converter = get_currency_conversion_service(
        user=user,
        display_currency=DEFAULT_DISPLAY_CURRENCY,
    )

    available_entities = {
        COMPARATIVE_TYPE_PERIODS: build_period_entities(
            user=user,
            year=default_year,
            metric=DEFAULT_METRIC,
            converter=converter,
            convert_to_rub=True,
        ),
        COMPARATIVE_TYPE_CATEGORIES: build_category_entities(
            user=user,
            year=default_year,
            metric=DEFAULT_METRIC,
            converter=converter,
            convert_to_rub=True,
        ),
        COMPARATIVE_TYPE_ACCOUNTS: build_account_entities(
            user=user,
            year=default_year,
            metric=DEFAULT_METRIC,
            converter=converter,
            convert_to_rub=True,
        ),
    }

    return {
        "max_entities": DEFAULT_MAX_ENTITIES,
        "comparison_type_options": [
            {"value": COMPARATIVE_TYPE_PERIODS, "label": "Периоды"},
            {"value": COMPARATIVE_TYPE_CATEGORIES, "label": "Категории"},
            {"value": COMPARATIVE_TYPE_ACCOUNTS, "label": "Счета"},
        ],
        "year_options": build_year_options(user=user, today=today),
        "metric_options": [
            {"value": COMPARATIVE_METRIC_INCOME, "label": "Сумма доходов"},
            {"value": COMPARATIVE_METRIC_EXPENSE, "label": "Сумма расходов"},
            {"value": COMPARATIVE_METRIC_BALANCE, "label": "Сальдо"},
        ],
        "report_period_options": build_report_period_options(today=today),
        "export_sections": [
            {"id": "legend", "label": "Включить легенду", "icon": "mdi-format-list-bulleted"},
            {"id": "differences", "label": "Включить таблицу различий", "icon": "mdi-table"},
            {"id": "charts", "label": "Включить графики", "icon": "mdi-chart-bar"},
        ],
        "available_entities": available_entities,
        "default_comparison_type": DEFAULT_COMPARISON_TYPE,
        "default_year": str(default_year),
        "default_metric": DEFAULT_METRIC,
        "default_entity_ids": {
            comparison_type: [entity["id"] for entity in entities[:min(4, DEFAULT_MAX_ENTITIES)]]
            for comparison_type, entities in available_entities.items()
        },
        "default_export_sections": DEFAULT_EXPORT_SECTIONS,
        "default_report_period_id": str(default_year),
    }


def build_comparative_analytics_comparison_from_query(*, user, query_params) -> dict:
    filters = build_filters_from_query(user=user, query_params=query_params)
    converter = get_currency_conversion_service(
        user=user,
        display_currency=filters.display_currency,
    )
    return build_comparative_analytics_comparison(
        user=user,
        filters=filters,
        converter=converter,
    )


def build_comparative_analytics_comparison_from_body(*, user, payload: Mapping[str, object]) -> dict:
    filters = build_filters_from_body(user=user, payload=payload)
    converter = get_currency_conversion_service(
        user=user,
        display_currency=filters.display_currency,
    )
    return build_comparative_analytics_comparison(
        user=user,
        filters=filters,
        converter=converter,
    )


def build_filters_from_query(*, user, query_params) -> ComparativeAnalyticsFilters:
    comparison_type = normalize_comparison_type(
        get_first_query_value(query_params, "comparison_type", "comparisonType")
    )
    year = normalize_year(get_first_query_value(query_params, "year"), user=user)
    metric = normalize_metric(get_first_query_value(query_params, "metric"))
    convert_to_rub = normalize_bool(
        get_first_query_value(query_params, "convert_to_rub", "convertToRub"),
        default=True,
        field_name="convert_to_rub",
    )
    raw_entity_ids = get_repeated_query_values(query_params, "entity_ids", "entityIds")
    entity_ids = normalize_entity_ids(
        user=user,
        comparison_type=comparison_type,
        year=year,
        metric=metric,
        raw_entity_ids=raw_entity_ids,
        allow_defaults=True,
    )
    return ComparativeAnalyticsFilters(
        comparison_type=comparison_type,
        year=year,
        metric=metric,
        entity_ids=entity_ids,
        convert_to_rub=convert_to_rub,
    )


def build_filters_from_body(*, user, payload: Mapping[str, object]) -> ComparativeAnalyticsFilters:
    comparison_type = normalize_comparison_type(
        get_body_value(payload, "comparison_type", "comparisonType")
    )
    year = normalize_year(get_body_value(payload, "year"), user=user)
    metric = normalize_metric(get_body_value(payload, "metric"))
    convert_to_rub = normalize_bool(
        get_body_value(payload, "convert_to_rub", "convertToRub"),
        default=True,
        field_name="convert_to_rub",
    )
    raw_entity_ids = get_body_value(payload, "entity_ids", "entityIds") or []
    entity_ids = normalize_entity_ids(
        user=user,
        comparison_type=comparison_type,
        year=year,
        metric=metric,
        raw_entity_ids=raw_entity_ids,
        allow_defaults=True,
    )
    return ComparativeAnalyticsFilters(
        comparison_type=comparison_type,
        year=year,
        metric=metric,
        entity_ids=entity_ids,
        convert_to_rub=convert_to_rub,
    )


def build_comparative_analytics_comparison(
    *,
    user,
    filters: ComparativeAnalyticsFilters,
    converter: CurrencyConversionService,
) -> dict:
    contexts = resolve_entity_contexts(
        user=user,
        filters=filters,
        converter=converter,
    )
    entities = [context_to_payload(context, metric=filters.metric) for context in contexts]
    has_mixed_currencies = detect_mixed_currencies(user=user, filters=filters)
    bar_groups = build_bar_groups(contexts)
    bar_legend = [
        {
            "id": context.id,
            "label": context.label,
            "color": context.color,
            "has_data": context.has_data,
        }
        for context in contexts
    ]
    summary_cards = build_summary_cards(contexts)
    line_points = build_line_points(
        user=user,
        filters=filters,
        converter=converter,
    )
    category_rows = build_category_rows(
        user=user,
        filters=filters,
        contexts=contexts,
        converter=converter,
    )
    difference_rows = build_difference_rows(contexts)

    return {
        "has_data": any(context.has_data for context in contexts),
        "has_mixed_currencies": has_mixed_currencies,
        "entities": entities,
        "bar_groups": bar_groups,
        "bar_legend": bar_legend,
        "summary_cards": summary_cards,
        "line_points": line_points,
        "category_rows": category_rows,
        "difference_rows": difference_rows,
    }


def resolve_entity_contexts(
    *,
    user,
    filters: ComparativeAnalyticsFilters,
    converter: CurrencyConversionService,
) -> list[ComparativeEntityContext]:
    contexts = []
    for index, entity_id in enumerate(filters.entity_ids):
        scope = build_entity_scope(user=user, filters=filters, entity_id=entity_id)
        stats = get_scope_stats(
            user=user,
            scope=scope,
            converter=converter,
            convert_to_rub=should_convert_scope(filters),
        )
        label, subtitle, currency_code = resolve_entity_labels(
            user=user,
            filters=filters,
            entity_id=entity_id,
            convert_to_rub=filters.convert_to_rub,
        )
        contexts.append(
            ComparativeEntityContext(
                id=entity_id,
                label=label,
                subtitle=subtitle,
                color=ENTITY_COLORS[index % len(ENTITY_COLORS)],
                currency_code=currency_code,
                has_data=stats[COMPARATIVE_METRIC_INCOME] > 0 or stats[COMPARATIVE_METRIC_EXPENSE] > 0,
                stats=stats,
            )
        )
    return contexts


def context_to_payload(context: ComparativeEntityContext, *, metric: str) -> dict:
    return {
        "id": context.id,
        "label": context.label,
        "subtitle": context.subtitle,
        "amount_rub": decimal_to_number(context.stats[metric]),
        "color": context.color,
        "has_data": context.has_data,
        "currency_code": context.currency_code,
    }


def build_bar_groups(contexts: Sequence[ComparativeEntityContext]) -> list[dict]:
    groups = []
    for metric in [COMPARATIVE_METRIC_INCOME, COMPARATIVE_METRIC_EXPENSE, COMPARATIVE_METRIC_BALANCE]:
        groups.append(
            {
                "key": metric,
                "label": METRIC_SHORT_LABELS[metric],
                "values": [decimal_to_number(context.stats[metric]) for context in contexts],
            }
        )
    return groups


def build_summary_cards(contexts: Sequence[ComparativeEntityContext]) -> list[dict]:
    cards = []
    for metric in [COMPARATIVE_METRIC_INCOME, COMPARATIVE_METRIC_EXPENSE, COMPARATIVE_METRIC_BALANCE]:
        amount = sum((context.stats[metric] for context in contexts), Decimal("0.00"))
        value_a = contexts[0].stats[metric] if contexts else Decimal("0.00")
        value_b = contexts[1].stats[metric] if len(contexts) > 1 else Decimal("0.00")
        cards.append(
            {
                "label": METRIC_SHORT_LABELS[metric],
                "amount_rub": decimal_to_number(amount),
                "delta_percent": decimal_to_number(calculate_delta_percent(value_a, value_b)),
                "delta_label": build_delta_label(value_a, value_b),
                "positive_is_good": metric != COMPARATIVE_METRIC_EXPENSE,
            }
        )
    return cards


def build_line_points(
    *,
    user,
    filters: ComparativeAnalyticsFilters,
    converter: CurrencyConversionService,
) -> list[dict]:
    date_from = date(filters.year, 1, 1)
    date_to = date(filters.year, 12, 31)
    months = get_month_range(date_from, date_to)
    values_by_month = {
        month_key: {
            COMPARATIVE_METRIC_INCOME: Decimal("0.00"),
            COMPARATIVE_METRIC_EXPENSE: Decimal("0.00"),
        }
        for month_key in months
    }

    queryset = Transaction.objects.filter(
        user=user,
        operation_date__gte=date_from,
        operation_date__lte=date_to,
    )
    if filters.comparison_type == COMPARATIVE_TYPE_CATEGORIES:
        queryset = queryset.filter(category_id__in=parse_ids(filters.entity_ids, field_name="entity_ids"))
    elif filters.comparison_type == COMPARATIVE_TYPE_ACCOUNTS:
        queryset = queryset.filter(account_id__in=parse_ids(filters.entity_ids, field_name="entity_ids"))

    rows = (
        queryset
        .annotate(month=TruncMonth("operation_date"))
        .values("month", "type", "account__currency")
        .annotate(total_amount=Sum("amount"))
        .order_by()
    )
    for row in rows:
        month_value = row["month"]
        month_date = month_value.date() if hasattr(month_value, "date") else month_value
        month_key = f"{month_date.year:04d}-{month_date.month:02d}"
        transaction_type = row["type"]
        if month_key not in values_by_month or transaction_type not in values_by_month[month_key]:
            continue
        converted = converter.convert_to_display(
            row["total_amount"] or Decimal("0.00"),
            source_currency=row["account__currency"],
        ).amount
        values_by_month[month_key][transaction_type] += converted

    return [
        {
            "month": month_key,
            "label": get_month_label_from_key(month_key),
            "income_rub": decimal_to_number(values[COMPARATIVE_METRIC_INCOME]),
            "expense_rub": decimal_to_number(values[COMPARATIVE_METRIC_EXPENSE]),
        }
        for month_key, values in values_by_month.items()
    ]


def build_category_rows(
    *,
    user,
    filters: ComparativeAnalyticsFilters,
    contexts: Sequence[ComparativeEntityContext],
    converter: CurrencyConversionService,
) -> list[dict]:
    if len(contexts) < 2:
        return []

    scope_a = build_entity_scope(user=user, filters=filters, entity_id=contexts[0].id)
    scope_b = build_entity_scope(user=user, filters=filters, entity_id=contexts[1].id)
    amounts_a = get_category_metric_amounts(user=user, scope=scope_a, metric=filters.metric, converter=converter)
    amounts_b = get_category_metric_amounts(user=user, scope=scope_b, metric=filters.metric, converter=converter)
    category_ids = set(amounts_a) | set(amounts_b)
    categories = {
        category.id: category.name
        for category in Category.objects.filter(user=user, id__in=category_ids)
    }

    rows = []
    for category_id in category_ids:
        current_amount = amounts_a.get(category_id, Decimal("0.00"))
        previous_amount = amounts_b.get(category_id, Decimal("0.00"))
        rows.append(
            {
                "id": str(category_id),
                "name": categories.get(category_id, "Без категории"),
                "previous_amount_rub": decimal_to_number(previous_amount),
                "current_amount_rub": decimal_to_number(current_amount),
                "delta_percent": decimal_to_number(calculate_delta_percent(current_amount, previous_amount)),
            }
        )

    return sorted(rows, key=lambda item: (-abs(item["current_amount_rub"]), item["name"]))


def build_difference_rows(contexts: Sequence[ComparativeEntityContext]) -> list[dict]:
    if len(contexts) < 2:
        return []
    first = contexts[0]
    second = contexts[1]
    rows = []
    for metric in [COMPARATIVE_METRIC_INCOME, COMPARATIVE_METRIC_EXPENSE, COMPARATIVE_METRIC_BALANCE]:
        value_a = first.stats[metric]
        value_b = second.stats[metric]
        delta = value_a - value_b
        rows.append(
            {
                "id": metric,
                "metric": METRIC_LABELS[metric],
                "value_a": decimal_to_number(value_a),
                "value_b": decimal_to_number(value_b),
                "delta_rub": decimal_to_number(delta),
                "delta_percent": decimal_to_number(calculate_delta_percent(value_a, value_b)),
                "positive_is_good": metric != COMPARATIVE_METRIC_EXPENSE,
                "label_a": first.label,
                "label_b": second.label,
            }
        )
    return rows


def build_entity_scope(*, user, filters: ComparativeAnalyticsFilters, entity_id: str) -> EntityScope:
    if filters.comparison_type == COMPARATIVE_TYPE_PERIODS:
        period_date_from, period_date_to = resolve_month_entity_id(entity_id)
        return EntityScope(date_from=period_date_from, date_to=period_date_to)

    if filters.comparison_type == COMPARATIVE_TYPE_CATEGORIES:
        category_id = int(entity_id)
        return EntityScope(
            date_from=date(filters.year, 1, 1),
            date_to=date(filters.year, 12, 31),
            category_ids=[category_id],
        )

    account_id = int(entity_id)
    return EntityScope(
        date_from=date(filters.year, 1, 1),
        date_to=date(filters.year, 12, 31),
        account_ids=[account_id],
    )


def get_scope_stats(
    *,
    user,
    scope: EntityScope,
    converter: CurrencyConversionService,
    convert_to_rub: bool,
) -> dict[str, Decimal]:
    rows = (
        build_scope_queryset(user=user, scope=scope)
        .values("type", "account__currency")
        .annotate(total_amount=Sum("amount"))
        .order_by()
    )
    stats = {
        COMPARATIVE_METRIC_INCOME: Decimal("0.00"),
        COMPARATIVE_METRIC_EXPENSE: Decimal("0.00"),
        COMPARATIVE_METRIC_BALANCE: Decimal("0.00"),
    }
    for row in rows:
        transaction_type = row["type"]
        if transaction_type not in (TransactionType.INCOME.value, TransactionType.EXPENSE.value):
            continue
        amount = row["total_amount"] or Decimal("0.00")
        if convert_to_rub:
            amount = converter.convert_to_display(
                amount,
                source_currency=row["account__currency"],
            ).amount
        stats[transaction_type] += amount

    stats[COMPARATIVE_METRIC_BALANCE] = (
        stats[COMPARATIVE_METRIC_INCOME]
        - stats[COMPARATIVE_METRIC_EXPENSE]
    )
    return {key: quantize_money(value) for key, value in stats.items()}


def get_category_metric_amounts(
    *,
    user,
    scope: EntityScope,
    metric: str,
    converter: CurrencyConversionService,
) -> dict[int, Decimal]:
    rows = (
        build_scope_queryset(user=user, scope=scope)
        .values("category_id", "type", "account__currency")
        .annotate(total_amount=Sum("amount"))
        .order_by()
    )
    values: dict[int, dict[str, Decimal]] = {}
    for row in rows:
        category_id = row["category_id"]
        transaction_type = row["type"]
        if transaction_type not in (TransactionType.INCOME.value, TransactionType.EXPENSE.value):
            continue
        converted = converter.convert_to_display(
            row["total_amount"] or Decimal("0.00"),
            source_currency=row["account__currency"],
        ).amount
        values.setdefault(
            category_id,
            {
                COMPARATIVE_METRIC_INCOME: Decimal("0.00"),
                COMPARATIVE_METRIC_EXPENSE: Decimal("0.00"),
            },
        )[transaction_type] += converted

    result = {}
    for category_id, metric_values in values.items():
        if metric == COMPARATIVE_METRIC_BALANCE:
            result[category_id] = quantize_money(
                metric_values[COMPARATIVE_METRIC_INCOME] - metric_values[COMPARATIVE_METRIC_EXPENSE]
            )
        else:
            result[category_id] = quantize_money(metric_values[metric])
    return result


def build_scope_queryset(*, user, scope: EntityScope):
    queryset = Transaction.objects.filter(
        user=user,
        operation_date__gte=scope.date_from,
        operation_date__lte=scope.date_to,
    ).select_related("account", "category")
    if scope.account_ids:
        queryset = queryset.filter(account_id__in=scope.account_ids)
    if scope.category_ids:
        queryset = queryset.filter(category_id__in=scope.category_ids)
    return queryset


def should_convert_scope(filters: ComparativeAnalyticsFilters) -> bool:
    if filters.comparison_type == COMPARATIVE_TYPE_ACCOUNTS:
        return filters.convert_to_rub
    return True


def detect_mixed_currencies(*, user, filters: ComparativeAnalyticsFilters) -> bool:
    if filters.comparison_type != COMPARATIVE_TYPE_ACCOUNTS:
        return False
    currencies = set(
        Account.objects
        .filter(user=user, id__in=parse_ids(filters.entity_ids, field_name="entity_ids"))
        .values_list("currency", flat=True)
    )
    return len(currencies) > 1


def resolve_entity_labels(
    *,
    user,
    filters: ComparativeAnalyticsFilters,
    entity_id: str,
    convert_to_rub: bool,
) -> tuple[str, str, str]:
    if filters.comparison_type == COMPARATIVE_TYPE_PERIODS:
        month_from, _ = resolve_month_entity_id(entity_id)
        return get_month_label(month_from.year, month_from.month), "Период", DEFAULT_DISPLAY_CURRENCY

    if filters.comparison_type == COMPARATIVE_TYPE_CATEGORIES:
        category = Category.objects.get(user=user, id=int(entity_id))
        subtitle = "Доходная категория" if category.type == TransactionType.INCOME.value else "Расходная категория"
        return category.name, subtitle, DEFAULT_DISPLAY_CURRENCY

    account = Account.objects.get(user=user, id=int(entity_id))
    currency_code = DEFAULT_DISPLAY_CURRENCY if convert_to_rub else account.currency
    return account.name, account.currency, currency_code


def build_period_entities(
    *,
    user,
    year: int,
    metric: str,
    converter: CurrencyConversionService,
    convert_to_rub: bool,
) -> list[dict]:
    entities = []
    for month in range(12, 0, -1):
        entity_id = f"{year:04d}-{month:02d}"
        month_from, month_to = get_month_bounds(year, month)
        scope = EntityScope(date_from=month_from, date_to=month_to)
        stats = get_scope_stats(user=user, scope=scope, converter=converter, convert_to_rub=convert_to_rub)
        entities.append(
            {
                "id": entity_id,
                "label": get_month_label(year, month),
                "subtitle": "Период",
                "amount_rub": decimal_to_number(stats[metric]),
                "color": ENTITY_COLORS[(12 - month) % len(ENTITY_COLORS)],
                "has_data": stats[COMPARATIVE_METRIC_INCOME] > 0 or stats[COMPARATIVE_METRIC_EXPENSE] > 0,
                "currency_code": DEFAULT_DISPLAY_CURRENCY,
            }
        )
    return entities


def build_category_entities(
    *,
    user,
    year: int,
    metric: str,
    converter: CurrencyConversionService,
    convert_to_rub: bool,
) -> list[dict]:
    categories = list(
        Category.objects
        .filter(user=user, is_active=True, is_archived=False)
        .order_by("type", "sort_order", "name", "id")
    )
    entities = []
    for index, category in enumerate(categories):
        scope = EntityScope(
            date_from=date(year, 1, 1),
            date_to=date(year, 12, 31),
            category_ids=[category.id],
        )
        stats = get_scope_stats(user=user, scope=scope, converter=converter, convert_to_rub=convert_to_rub)
        subtitle = "Доходная категория" if category.type == TransactionType.INCOME.value else "Расходная категория"
        entities.append(
            {
                "id": str(category.id),
                "label": category.name,
                "subtitle": subtitle,
                "amount_rub": decimal_to_number(stats[metric]),
                "color": category.color or ENTITY_COLORS[index % len(ENTITY_COLORS)],
                "has_data": stats[COMPARATIVE_METRIC_INCOME] > 0 or stats[COMPARATIVE_METRIC_EXPENSE] > 0,
                "currency_code": DEFAULT_DISPLAY_CURRENCY,
            }
        )
    return entities


def build_account_entities(
    *,
    user,
    year: int,
    metric: str,
    converter: CurrencyConversionService,
    convert_to_rub: bool,
) -> list[dict]:
    accounts = list(
        Account.objects
        .filter(user=user, is_active=True, is_archived=False)
        .order_by("-is_default", "name", "id")
    )
    entities = []
    for index, account in enumerate(accounts):
        scope = EntityScope(
            date_from=date(year, 1, 1),
            date_to=date(year, 12, 31),
            account_ids=[account.id],
        )
        stats = get_scope_stats(user=user, scope=scope, converter=converter, convert_to_rub=convert_to_rub)
        entities.append(
            {
                "id": str(account.id),
                "label": account.name,
                "subtitle": account.currency,
                "amount_rub": decimal_to_number(stats[metric]),
                "color": account.color or ENTITY_COLORS[index % len(ENTITY_COLORS)],
                "has_data": stats[COMPARATIVE_METRIC_INCOME] > 0 or stats[COMPARATIVE_METRIC_EXPENSE] > 0,
                "currency_code": DEFAULT_DISPLAY_CURRENCY if convert_to_rub else account.currency,
            }
        )
    return entities


def build_year_options(*, user, today: date) -> list[dict[str, str]]:
    years = Transaction.objects.filter(user=user).dates("operation_date", "year")
    year_values = {value.year for value in years if value is not None}
    year_values.add(today.year)
    year_values.add(today.year - 1)
    return [
        {"value": str(year), "label": str(year)}
        for year in sorted(year_values, reverse=True)
    ]


def build_report_period_options(*, today: date) -> list[dict[str, str]]:
    return [
        {"value": str(today.year), "label": f"{today.year} год"},
        {"value": str(today.year - 1), "label": f"{today.year - 1} год"},
    ]


def normalize_comparison_type(value: str | None) -> str:
    comparison_type = str(value or DEFAULT_COMPARISON_TYPE).strip().lower()
    if comparison_type not in COMPARATIVE_TYPES:
        raise ValidationError({"comparison_type": ["Допустимые значения: periods, categories, accounts."]})
    return comparison_type


def normalize_metric(value: str | None) -> str:
    metric = str(value or DEFAULT_METRIC).strip().lower()
    if metric not in COMPARATIVE_METRICS:
        raise ValidationError({"metric": ["Допустимые значения: income, expense, balance."]})
    return metric


def normalize_year(value: str | int | None, *, user) -> int:
    if value in (None, ""):
        return get_user_app_today(user).year
    try:
        year = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValidationError({"year": ["Год должен быть числом."]}) from exc
    if year < 2000 or year > 2100:
        raise ValidationError({"year": ["Год должен быть в диапазоне 2000-2100."]})
    return year


def normalize_bool(value, *, default: bool, field_name: str) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ValidationError({field_name: ["Значение должно быть true или false."]})


def normalize_entity_ids(
    *,
    user,
    comparison_type: str,
    year: int,
    metric: str,
    raw_entity_ids,
    allow_defaults: bool,
) -> list[str]:
    values = normalize_raw_entity_values(raw_entity_ids)
    if not values and allow_defaults:
        return get_default_entity_ids(
            user=user,
            comparison_type=comparison_type,
            year=year,
            metric=metric,
        )
    if not values:
        raise ValidationError({"entity_ids": ["Выберите хотя бы одну сущность для сравнения."]})
    if len(values) > DEFAULT_MAX_ENTITIES:
        raise ValidationError({"entity_ids": [f"Можно сравнить не более {DEFAULT_MAX_ENTITIES} сущностей."]})

    if comparison_type == COMPARATIVE_TYPE_PERIODS:
        for entity_id in values:
            month_from, _ = resolve_month_entity_id(entity_id)
            if month_from.year != year:
                raise ValidationError({"entity_ids": ["Периоды должны относиться к выбранному году."]})
        return values

    numeric_ids = parse_ids(values, field_name="entity_ids")
    if comparison_type == COMPARATIVE_TYPE_CATEGORIES:
        existing_ids = set(
            Category.objects
            .filter(user=user, id__in=numeric_ids)
            .values_list("id", flat=True)
        )
    else:
        existing_ids = set(
            Account.objects
            .filter(user=user, id__in=numeric_ids)
            .values_list("id", flat=True)
        )
    missing_ids = sorted(set(numeric_ids) - existing_ids)
    if missing_ids:
        raise ValidationError({"entity_ids": ["Некорректные id сущностей."]})
    return [str(value) for value in numeric_ids]


def normalize_raw_entity_values(raw_values) -> list[str]:
    if raw_values in (None, ""):
        return []
    if isinstance(raw_values, (str, int)):
        iterable = [raw_values]
    else:
        iterable = list(raw_values)
    result = []
    for value in iterable:
        if value in (None, ""):
            continue
        if isinstance(value, str):
            parts = [part.strip() for part in value.split(",")]
        else:
            parts = [str(value)]
        for part in parts:
            if part and part not in result:
                result.append(part)
    return result


def get_default_entity_ids(*, user, comparison_type: str, year: int, metric: str) -> list[str]:
    if comparison_type == COMPARATIVE_TYPE_PERIODS:
        today = get_user_app_today(user)
        start_month = min(today.month, 12) if year == today.year else 12
        ids = [f"{year:04d}-{month:02d}" for month in range(start_month, max(start_month - 4, 0), -1)]
        return ids[:DEFAULT_MAX_ENTITIES]
    if comparison_type == COMPARATIVE_TYPE_CATEGORIES:
        return [
            str(category_id)
            for category_id in Category.objects
            .filter(user=user, is_active=True, is_archived=False)
            .order_by("type", "sort_order", "name", "id")
            .values_list("id", flat=True)[:DEFAULT_MAX_ENTITIES]
        ]
    return [
        str(account_id)
        for account_id in Account.objects
        .filter(user=user, is_active=True, is_archived=False)
        .order_by("-is_default", "name", "id")
        .values_list("id", flat=True)[:DEFAULT_MAX_ENTITIES]
    ]


def parse_ids(values, *, field_name: str) -> list[int]:
    raw_values = normalize_raw_entity_values(values)
    result: list[int] = []
    for value in raw_values:
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ValidationError({field_name: ["ID должен быть целым числом."]}) from exc
        if parsed not in result:
            result.append(parsed)
    return result


def resolve_month_entity_id(entity_id: str) -> tuple[date, date]:
    match = re.fullmatch(r"(\d{4})-(\d{2})", str(entity_id or "").strip())
    if not match:
        raise ValidationError({"entity_ids": ["Для периодов используйте формат YYYY-MM."]})
    year = int(match.group(1))
    month = int(match.group(2))
    return get_month_bounds(year, month)


def normalize_export_format(value: str | None) -> str:
    export_format = str(value or "").strip().lower()
    if export_format not in COMPARATIVE_EXPORT_FORMATS:
        raise ValidationError({"format": ["Формат экспорта должен быть pdf, csv или xlsx."]})
    return export_format


def normalize_export_sections(values: Iterable[str] | str | None) -> list[str]:
    if not values:
        raise ValidationError({"sections": ["Выберите хотя бы одну секцию экспорта."]})
    iterable = [part.strip() for part in values.split(",")] if isinstance(values, str) else values
    sections = []
    for value in iterable:
        section = str(value or "").strip().lower()
        if not section:
            continue
        if section not in COMPARATIVE_EXPORT_SECTIONS:
            raise ValidationError({"sections": ["Допустимые значения: legend, differences, charts."]})
        if section not in sections:
            sections.append(section)
    if not sections:
        raise ValidationError({"sections": ["Выберите хотя бы одну секцию экспорта."]})
    return sections


def calculate_delta_percent(value_a: Decimal, value_b: Decimal) -> Decimal:
    value_a = Decimal(value_a or "0.00")
    value_b = Decimal(value_b or "0.00")
    if value_b == 0:
        if value_a == 0:
            return Decimal("0.00")
        return Decimal("100.00")
    return ((value_a - value_b) / abs(value_b) * Decimal("100")).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def build_delta_label(value_a: Decimal, value_b: Decimal) -> str:
    delta = calculate_delta_percent(value_a, value_b)
    sign = "+" if delta > 0 else ""
    return f"{sign}{decimal_to_number(delta)}% к предыдущему"


def get_month_label_from_key(month_key: str) -> str:
    year, month = month_key.split("-", maxsplit=1)
    return get_month_label(int(year), int(month))
