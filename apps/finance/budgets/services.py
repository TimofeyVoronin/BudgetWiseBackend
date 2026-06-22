from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Sum
from django.utils import timezone

from apps.finance.currencies.money import build_money_payload
from apps.finance.models import (
    Budget,
    BudgetCategoryGroup,
    BudgetKind,
    BudgetPeriodType,
    BudgetUsageStatus,
    Category,
    Transaction,
)


BUDGET_WARNING_THRESHOLD_PERCENT = Decimal("90.00")
BUDGET_PERCENT_QUANT = Decimal("0.01")
MONEY_QUANT = Decimal("0.01")

BUDGET_CATEGORY_GROUP_OPTIONS = [
    {
        "title": BudgetCategoryGroup.MAIN.label,
        "value": BudgetCategoryGroup.MAIN,
    },
    {
        "title": BudgetCategoryGroup.FAMILY.label,
        "value": BudgetCategoryGroup.FAMILY,
    },
    {
        "title": BudgetCategoryGroup.PERSONAL.label,
        "value": BudgetCategoryGroup.PERSONAL,
    },
]

BUDGET_PERIOD_TYPE_OPTIONS = [
    {
        "title": BudgetPeriodType.MONTH.label,
        "value": BudgetPeriodType.MONTH,
    },
    {
        "title": BudgetPeriodType.QUARTER.label,
        "value": BudgetPeriodType.QUARTER,
    },
    {
        "title": BudgetPeriodType.YEAR.label,
        "value": BudgetPeriodType.YEAR,
    },
]

BUDGET_CURRENCY_OPTIONS = [
    {
        "title": "Российский рубль",
        "value": "RUB",
    },
]

BUDGET_KIND_OPTIONS = [
    {
        "title": BudgetKind.EXPENSE.label,
        "value": BudgetKind.EXPENSE,
    },
    {
        "title": BudgetKind.INCOME.label,
        "value": BudgetKind.INCOME,
    },
]

BUDGET_USAGE_STATUS_OPTIONS = [
    {
        "title": BudgetUsageStatus.NORMAL.label,
        "value": BudgetUsageStatus.NORMAL,
    },
    {
        "title": BudgetUsageStatus.WARNING.label,
        "value": BudgetUsageStatus.WARNING,
    },
    {
        "title": BudgetUsageStatus.EXCEEDED.label,
        "value": BudgetUsageStatus.EXCEEDED,
    },
]


@dataclass(frozen=True)
class BudgetUsage:
    spent_amount: Decimal
    remaining_amount: Decimal
    usage_percent: Decimal
    usage_status: str
    forecast_amount: Decimal
    forecast_within_limit: bool
    average_daily_amount: Decimal


def decimal_to_number(value: Decimal | int | float | None) -> float:
    if value is None:
        return 0.0

    if not isinstance(value, Decimal):
        value = Decimal(str(value))

    return float(value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP))


def percent_to_number(value: Decimal | int | float | None) -> float:
    if value is None:
        return 0.0

    if not isinstance(value, Decimal):
        value = Decimal(str(value))

    return float(value.quantize(BUDGET_PERCENT_QUANT, rounding=ROUND_HALF_UP))


def get_budget_category_ids(budget: Budget) -> list[int]:
    """Return budget category id and ids of its direct/indirect children."""
    cached_category_ids = getattr(budget, "_category_ids_cache", None)
    if cached_category_ids is not None:
        return list(cached_category_ids)

    descendants_by_parent = getattr(budget, "_category_children_cache", None)
    if descendants_by_parent is None:
        descendants_by_parent = _build_category_children_map(user_id=budget.user_id)

    category_ids = _collect_category_tree_ids(
        root_id=budget.category_id,
        descendants_by_parent=descendants_by_parent,
    )
    budget._category_ids_cache = category_ids
    return list(category_ids)


def preload_budget_category_ids(budgets: list[Budget]) -> list[Budget]:
    if not budgets:
        return budgets

    user_id = budgets[0].user_id
    descendants_by_parent = _build_category_children_map(user_id=user_id)

    for budget in budgets:
        budget._category_children_cache = descendants_by_parent
        budget._category_ids_cache = _collect_category_tree_ids(
            root_id=budget.category_id,
            descendants_by_parent=descendants_by_parent,
        )

    return budgets


def _build_category_children_map(*, user=None, user_id: int | None = None) -> dict[int | None, list[int]]:
    if user_id is None and user is not None:
        user_id = user.id

    rows = Category.objects.filter(user_id=user_id).values_list("parent_id", "id")
    descendants_by_parent: dict[int | None, list[int]] = {}

    for parent_id, category_id in rows:
        descendants_by_parent.setdefault(parent_id, []).append(category_id)

    return descendants_by_parent


def _collect_category_tree_ids(
    *,
    root_id: int,
    descendants_by_parent: dict[int | None, list[int]],
) -> list[int]:
    category_ids = [root_id]
    queue = [root_id]
    seen = {root_id}

    while queue:
        parent_id = queue.pop(0)
        for child_id in descendants_by_parent.get(parent_id, []):
            if child_id in seen:
                continue
            seen.add(child_id)
            category_ids.append(child_id)
            queue.append(child_id)

    return category_ids

def get_budget_transactions_queryset(budget: Budget):
    return (
        Transaction.objects
        .filter(
            user=budget.user,
            type=budget.kind,
            operation_date__gte=budget.period_start,
            operation_date__lte=budget.period_end,
            category_id__in=get_budget_category_ids(budget),
        )
        .select_related("account", "category")
    )


def get_transaction_source_currency(transaction: Transaction, *, fallback_currency: str) -> str:
    if transaction.account_id and transaction.account:
        return transaction.account.currency

    return fallback_currency


def get_budget_spent_amount(
    budget: Budget,
    *,
    converter=None,
    target_currency: str | None = None,
    until_date: date | None = None,
) -> Decimal:
    queryset = get_budget_transactions_queryset(budget)

    if until_date is not None:
        queryset = queryset.filter(operation_date__lte=until_date)

    if converter is None:
        aggregate = queryset.aggregate(total=Sum("amount"))
        return (aggregate.get("total") or Decimal("0.00")).quantize(MONEY_QUANT)

    total = Decimal("0.00")
    target_code = target_currency or budget.currency
    rows = (
        queryset
        .values("account__currency")
        .annotate(total=Sum("amount"))
    )

    for row in rows:
        source_currency = row["account__currency"] or budget.currency
        total += converter.convert(
            row["total"] or Decimal("0.00"),
            source_currency=source_currency,
            target_currency=target_code,
            quantize=False,
        ).amount

    return total.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def get_budget_usage_percent(*, spent_amount: Decimal, limit_amount: Decimal) -> Decimal:
    if limit_amount <= 0:
        return Decimal("0.00")

    return (
        spent_amount / limit_amount * Decimal("100")
    ).quantize(BUDGET_PERCENT_QUANT, rounding=ROUND_HALF_UP)


def get_budget_usage_status(*, budget: Budget, usage_percent: Decimal) -> str:
    if budget.paused or not budget.is_active:
        return BudgetUsageStatus.NORMAL

    if usage_percent > Decimal("100.00"):
        return BudgetUsageStatus.EXCEEDED

    if usage_percent >= BUDGET_WARNING_THRESHOLD_PERCENT:
        return BudgetUsageStatus.WARNING

    return BudgetUsageStatus.NORMAL


def get_budget_elapsed_days(budget: Budget, *, today: date | None = None) -> int:
    today = today or timezone.localdate()

    if today < budget.period_start:
        return 0

    if today > budget.period_end:
        return (budget.period_end - budget.period_start).days + 1

    return (today - budget.period_start).days + 1


def get_budget_total_days(budget: Budget) -> int:
    return max((budget.period_end - budget.period_start).days + 1, 1)


def get_budget_usage(budget: Budget, *, converter=None) -> BudgetUsage:
    cache_key = _get_budget_usage_cache_key(converter=converter)
    usage_cache = getattr(budget, "_budget_usage_cache", {})

    if cache_key in usage_cache:
        return usage_cache[cache_key]

    spent_amount = get_budget_spent_amount(
        budget,
        converter=converter,
        target_currency=budget.currency,
    )
    remaining_amount = (budget.amount_limit - spent_amount).quantize(MONEY_QUANT)
    usage_percent = get_budget_usage_percent(
        spent_amount=spent_amount,
        limit_amount=budget.amount_limit,
    )
    usage_status = get_budget_usage_status(
        budget=budget,
        usage_percent=usage_percent,
    )

    total_days = get_budget_total_days(budget)
    elapsed_days = get_budget_elapsed_days(budget)

    if elapsed_days <= 0:
        average_daily_amount = Decimal("0.00")
        forecast_amount = Decimal("0.00")
    elif elapsed_days >= total_days:
        average_daily_amount = spent_amount / Decimal(str(total_days))
        forecast_amount = spent_amount
    else:
        average_daily_amount = spent_amount / Decimal(str(elapsed_days))
        forecast_amount = average_daily_amount * Decimal(str(total_days))

    average_daily_amount = average_daily_amount.quantize(
        MONEY_QUANT,
        rounding=ROUND_HALF_UP,
    )
    forecast_amount = forecast_amount.quantize(
        MONEY_QUANT,
        rounding=ROUND_HALF_UP,
    )

    usage = BudgetUsage(
        spent_amount=spent_amount,
        remaining_amount=remaining_amount,
        usage_percent=usage_percent,
        usage_status=usage_status,
        forecast_amount=forecast_amount,
        forecast_within_limit=forecast_amount <= budget.amount_limit,
        average_daily_amount=average_daily_amount,
    )
    usage_cache[cache_key] = usage
    budget._budget_usage_cache = usage_cache
    return usage


def _get_budget_usage_cache_key(*, converter=None) -> tuple[str | None, str | None, bool | None]:
    if converter is None:
        return (None, None, None)

    return (
        getattr(converter, "display_currency", None),
        getattr(converter, "primary_currency", None),
        getattr(converter, "using_cached_rates", None),
    )

def get_period_label(budget: Budget) -> str:
    if budget.period_type == BudgetPeriodType.YEAR:
        return str(budget.period_start.year)

    if budget.period_type == BudgetPeriodType.QUARTER:
        quarter = ((budget.period_start.month - 1) // 3) + 1
        return f"{quarter_to_roman(quarter)} кв. {budget.period_start.year}"

    month_names = {
        1: "январь",
        2: "февраль",
        3: "март",
        4: "апрель",
        5: "май",
        6: "июнь",
        7: "июль",
        8: "август",
        9: "сентябрь",
        10: "октябрь",
        11: "ноябрь",
        12: "декабрь",
    }
    return f"{month_names[budget.period_start.month]} {budget.period_start.year}"


def quarter_to_roman(quarter: int) -> str:
    return {
        1: "I",
        2: "II",
        3: "III",
        4: "IV",
    }.get(quarter, str(quarter))


def budget_duplicate_exists(
    *,
    user,
    category: Category,
    kind: str,
    period_type: str,
    period_start: date,
    period_end: date | None = None,
    exclude_id: int | None = None,
) -> bool:
    queryset = Budget.objects.filter(
        user=user,
        category=category,
        kind=kind,
        period_type=period_type,
        period_start=period_start,
    )

    if period_end is not None:
        queryset = queryset.filter(period_end=period_end)

    if exclude_id:
        queryset = queryset.exclude(pk=exclude_id)

    return queryset.exists()


def build_budget_list_summary(budgets: list[Budget], *, converter=None) -> dict:
    normal_count = 0
    attention_count = 0

    for budget in budgets:
        usage = get_budget_usage(budget, converter=converter)

        if usage.usage_status == BudgetUsageStatus.NORMAL:
            normal_count += 1
        else:
            attention_count += 1

    return {
        "totalCount": len(budgets),
        "normalCount": normal_count,
        "attentionCount": attention_count,
    }


def build_display_money_payload(
    value,
    *,
    source_currency: str,
    converter=None,
) -> dict:
    if converter is None:
        return build_money_payload(value, currency=source_currency)

    return converter.display_amount_payload(
        value,
        source_currency=source_currency,
    )


def build_budget_detail_stats(budget: Budget, *, converter=None) -> dict:
    usage = get_budget_usage(budget, converter=converter)

    limit = build_display_money_payload(
        budget.amount_limit,
        source_currency=budget.currency,
        converter=converter,
    )
    spent = build_display_money_payload(
        usage.spent_amount,
        source_currency=budget.currency,
        converter=converter,
    )
    remaining = build_display_money_payload(
        usage.remaining_amount,
        source_currency=budget.currency,
        converter=converter,
    )
    avg_daily = build_display_money_payload(
        usage.average_daily_amount,
        source_currency=budget.currency,
        converter=converter,
    )
    forecast = build_display_money_payload(
        usage.forecast_amount,
        source_currency=budget.currency,
        converter=converter,
    )

    return {
        "limitRub": decimal_to_number(limit["amount"]),
        "spentRub": decimal_to_number(spent["amount"]),
        "remainingRub": decimal_to_number(remaining["amount"]),
        "avgDailyRub": decimal_to_number(avg_daily["amount"]),
        "forecastRub": decimal_to_number(forecast["amount"]),
        "limit": limit,
        "spent": spent,
        "remaining": remaining,
        "avgDaily": avg_daily,
        "forecast": forecast,
        "currency": limit["currency"],
        "forecastWithinLimit": usage.forecast_within_limit,
    }


def build_budget_chart(budget: Budget, *, converter=None) -> list[dict]:
    total_days = get_budget_total_days(budget)
    usage = get_budget_usage(budget, converter=converter)
    average_daily = usage.average_daily_amount

    checkpoints = sorted(
        {
            0,
            max(total_days // 4, 0),
            max(total_days // 2, 0),
            max(total_days * 3 // 4, 0),
            total_days - 1,
        }
    )

    items = []

    for day_offset in checkpoints:
        point_date = budget.period_start + timedelta(days=day_offset)
        fact_amount = get_budget_spent_amount(
            budget,
            converter=converter,
            target_currency=budget.currency,
            until_date=point_date,
        )
        forecast_amount = average_daily * Decimal(str(day_offset + 1))

        items.append(
            {
                "label": format_budget_chart_label(point_date),
                "factPct": percent_to_number(
                    get_budget_usage_percent(
                        spent_amount=fact_amount,
                        limit_amount=budget.amount_limit,
                    )
                ),
                "forecastPct": percent_to_number(
                    get_budget_usage_percent(
                        spent_amount=forecast_amount,
                        limit_amount=budget.amount_limit,
                    )
                ),
            }
        )

    return items


def format_budget_chart_label(value: date) -> str:
    return value.strftime("%d.%m")


def build_budget_operations(
    budget: Budget,
    *,
    limit: int = 10,
    converter=None,
) -> list[dict]:
    transactions = get_budget_transactions_queryset(budget).order_by(
        "-operation_date",
        "-created_at",
        "-id",
    )[:limit]

    items = []

    for transaction in transactions:
        source_currency = get_transaction_source_currency(
            transaction,
            fallback_currency=budget.currency,
        )
        amount = build_display_money_payload(
            transaction.amount,
            source_currency=source_currency,
            converter=converter,
        )

        items.append(
            {
                "id": str(transaction.pk),
                "title": transaction.description or transaction.category.name,
                "subtitle": (
                    f"{transaction.category.name} • {transaction.account.name} • "
                    f"{transaction.operation_date.strftime('%d.%m.%Y')}"
                ),
                "dateLabel": transaction.operation_date.strftime("%d.%m.%Y"),
                "amountRub": decimal_to_number(amount["amount"]),
                "amount": amount,
                "sourceCurrency": source_currency,
                "icon": transaction.category.icon,
            }
        )

    return items


def get_budget_warning_message(*, budget: Budget, usage: BudgetUsage) -> str:
    if usage.usage_status == BudgetUsageStatus.EXCEEDED:
        over_amount = usage.spent_amount - budget.amount_limit

        if budget.kind == BudgetKind.EXPENSE:
            return f"Бюджет превышен на {decimal_to_number(over_amount):.2f} {budget.currency}."

        return "Плановое значение бюджета превышено."

    if usage.usage_status == BudgetUsageStatus.WARNING:
        return "Бюджет близок к лимиту."

    return "Бюджет в норме."


def build_budget_warning_item(budget: Budget, *, converter=None) -> dict:
    usage = get_budget_usage(budget, converter=converter)
    spent = build_display_money_payload(
        usage.spent_amount,
        source_currency=budget.currency,
        converter=converter,
    )
    limit = build_display_money_payload(
        budget.amount_limit,
        source_currency=budget.currency,
        converter=converter,
    )
    remaining = build_display_money_payload(
        usage.remaining_amount,
        source_currency=budget.currency,
        converter=converter,
    )

    return {
        "budgetId": str(budget.pk),
        "categoryName": budget.category.name,
        "periodLabel": get_period_label(budget),
        "status": usage.usage_status,
        "percent": percent_to_number(usage.usage_percent),
        "spentRub": decimal_to_number(spent["amount"]),
        "limitRub": decimal_to_number(limit["amount"]),
        "remainingRub": decimal_to_number(remaining["amount"]),
        "spent": spent,
        "limit": limit,
        "remaining": remaining,
        "sourceCurrency": budget.currency,
        "message": get_budget_warning_message(budget=budget, usage=usage),
    }
