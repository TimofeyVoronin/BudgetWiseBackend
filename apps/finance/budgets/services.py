from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Sum
from django.utils import timezone

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
    category_ids = [budget.category_id]
    queue = [budget.category_id]

    while queue:
        parent_id = queue.pop(0)
        child_ids = list(
            Category.objects
            .filter(user=budget.user, parent_id=parent_id)
            .values_list("id", flat=True)
        )

        for child_id in child_ids:
            if child_id not in category_ids:
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


def get_budget_spent_amount(budget: Budget) -> Decimal:
    aggregate = get_budget_transactions_queryset(budget).aggregate(total=Sum("amount"))
    return (aggregate.get("total") or Decimal("0.00")).quantize(MONEY_QUANT)


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


def get_budget_usage(budget: Budget) -> BudgetUsage:
    spent_amount = get_budget_spent_amount(budget)
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

    return BudgetUsage(
        spent_amount=spent_amount,
        remaining_amount=remaining_amount,
        usage_percent=usage_percent,
        usage_status=usage_status,
        forecast_amount=forecast_amount,
        forecast_within_limit=forecast_amount <= budget.amount_limit,
        average_daily_amount=average_daily_amount,
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


def build_budget_list_summary(budgets: list[Budget]) -> dict:
    normal_count = 0
    attention_count = 0

    for budget in budgets:
        usage = get_budget_usage(budget)

        if usage.usage_status == BudgetUsageStatus.NORMAL:
            normal_count += 1
        else:
            attention_count += 1

    return {
        "totalCount": len(budgets),
        "normalCount": normal_count,
        "attentionCount": attention_count,
    }


def build_budget_detail_stats(budget: Budget) -> dict:
    usage = get_budget_usage(budget)

    return {
        "limitRub": decimal_to_number(budget.amount_limit),
        "spentRub": decimal_to_number(usage.spent_amount),
        "remainingRub": decimal_to_number(usage.remaining_amount),
        "avgDailyRub": decimal_to_number(usage.average_daily_amount),
        "forecastRub": decimal_to_number(usage.forecast_amount),
        "forecastWithinLimit": usage.forecast_within_limit,
    }


def build_budget_chart(budget: Budget) -> list[dict]:
    total_days = get_budget_total_days(budget)
    usage = get_budget_usage(budget)
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
        fact_amount = (
            get_budget_transactions_queryset(budget)
            .filter(operation_date__lte=point_date)
            .aggregate(total=Sum("amount"))
            .get("total")
            or Decimal("0.00")
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


def build_budget_operations(budget: Budget, *, limit: int = 10) -> list[dict]:
    transactions = get_budget_transactions_queryset(budget).order_by(
        "-operation_date",
        "-created_at",
        "-id",
    )[:limit]

    return [
        {
            "id": str(transaction.pk),
            "title": transaction.description or transaction.category.name,
            "subtitle": (
                f"{transaction.category.name} • {transaction.account.name} • "
                f"{transaction.operation_date.strftime('%d.%m.%Y')}"
            ),
            "dateLabel": transaction.operation_date.strftime("%d.%m.%Y"),
            "amountRub": decimal_to_number(transaction.amount),
            "icon": transaction.category.icon,
        }
        for transaction in transactions
    ]


def get_budget_warning_message(*, budget: Budget, usage: BudgetUsage) -> str:
    if usage.usage_status == BudgetUsageStatus.EXCEEDED:
        over_amount = usage.spent_amount - budget.amount_limit

        if budget.kind == BudgetKind.EXPENSE:
            return f"Бюджет превышен на {decimal_to_number(over_amount):.2f} ₽."

        return "Плановое значение бюджета превышено."

    if usage.usage_status == BudgetUsageStatus.WARNING:
        return "Бюджет близок к лимиту."

    return "Бюджет в норме."


def build_budget_warning_item(budget: Budget) -> dict:
    usage = get_budget_usage(budget)

    return {
        "budgetId": str(budget.pk),
        "categoryName": budget.category.name,
        "periodLabel": get_period_label(budget),
        "status": usage.usage_status,
        "percent": percent_to_number(usage.usage_percent),
        "spentRub": decimal_to_number(usage.spent_amount),
        "limitRub": decimal_to_number(budget.amount_limit),
        "remainingRub": decimal_to_number(usage.remaining_amount),
        "message": get_budget_warning_message(budget=budget, usage=usage),
    }
