from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from django.utils.dateparse import parse_date
from rest_framework.exceptions import ValidationError

from apps.finance.currencies.conversion import (
    CurrencyConversionService,
    get_currency_conversion_service,
)
from apps.finance.currencies.money import build_money_payload, quantize_money
from apps.finance.health_check.constants import (
    FINANCIAL_HEALTH_DEFAULT_PERIOD,
    FINANCIAL_HEALTH_PERIOD_CUSTOM,
    FINANCIAL_HEALTH_PERIOD_MONTH,
    FINANCIAL_HEALTH_PERIOD_QUARTER,
    FINANCIAL_HEALTH_PERIOD_YEAR,
    FINANCIAL_HEALTH_PERIODS,
    METRIC_BUDGET_USAGE,
    METRIC_CASH_GAP_RISK,
    METRIC_EMERGENCY_FUND_PROGRESS,
    METRIC_EXPENSE_STABILITY,
    METRIC_INCOME_EXPENSE_RATIO,
    METRIC_PLANNED_PAYMENTS_LOAD,
    METRIC_SAVINGS_RATE,
)
from apps.finance.models import (
    Account,
    Budget,
    BudgetKind,
    Goal,
    GoalCategory,
    GoalStatus,
    PlannedStatus,
    PlannedTransaction,
    Transaction,
    TransactionType,
)
from apps.users.app_settings.formatting import get_user_app_today

DECIMAL_ZERO = Decimal("0.00")
PERCENT_QUANT = Decimal("0.01")
RATIO_QUANT = Decimal("0.0001")


@dataclass(frozen=True)
class FinancialHealthPeriod:
    type: str
    date_from: date
    date_to: date
    label: str

    @property
    def days(self) -> int:
        return (self.date_to - self.date_from).days + 1

    def as_payload(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "dateFrom": self.date_from.isoformat(),
            "dateTo": self.date_to.isoformat(),
            "label": self.label,
            "days": self.days,
        }


def build_financial_health_aggregates(
    *,
    user,
    period: str | None = None,
    date_from: date | str | None = None,
    date_to: date | str | None = None,
    currency: str | None = None,
) -> dict[str, Any]:
    """Return read-only aggregate indicators for Financial Health Check.

    This service intentionally does not calculate the final 0..100 score yet.
    BUD-1152 is responsible only for collecting user data and building stable
    aggregated values that the next scoring layer can reuse.
    """

    resolved_period = resolve_financial_health_period(
        user=user,
        period=period,
        date_from=date_from,
        date_to=date_to,
    )
    converter = get_currency_conversion_service(
        user=user,
        display_currency=currency,
        refresh_rates=False,
    )

    transactions = list(
        Transaction.objects
        .filter(
            user=user,
            operation_date__gte=resolved_period.date_from,
            operation_date__lte=resolved_period.date_to,
        )
        .select_related("account", "category")
        .order_by("operation_date", "id")
    )

    account_aggregates = _build_account_aggregates(user=user, converter=converter)
    cashflow_aggregates = _build_cashflow_aggregates(
        transactions=transactions,
        converter=converter,
    )
    budget_aggregates = _build_budget_aggregates(
        user=user,
        period=resolved_period,
        converter=converter,
    )
    goal_aggregates = _build_goal_aggregates(user=user, converter=converter)
    planned_aggregates = _build_planned_transaction_aggregates(
        user=user,
        period=resolved_period,
        converter=converter,
    )
    expense_stability = _build_expense_stability_aggregates(
        transactions=transactions,
        period=resolved_period,
        converter=converter,
    )
    cash_gap = _build_cash_gap_aggregates(
        account_aggregates=account_aggregates,
        planned_aggregates=planned_aggregates,
        converter=converter,
    )

    income = cashflow_aggregates["income"]
    expenses = cashflow_aggregates["expenses"]
    net_balance = income - expenses

    return {
        "period": resolved_period.as_payload(),
        "currency": converter.display_currency,
        "totals": {
            "income": money_payload(income, converter),
            "expenses": money_payload(expenses, converter),
            "netBalance": money_payload(net_balance, converter),
            "accountsBalance": money_payload(account_aggregates["balance"], converter),
            "availableBalance": money_payload(account_aggregates["available_balance"], converter),
        },
        "metrics": {
            METRIC_INCOME_EXPENSE_RATIO: _build_income_expense_ratio_payload(
                income=income,
                expenses=expenses,
                converter=converter,
            ),
            METRIC_SAVINGS_RATE: _build_savings_rate_payload(
                income=income,
                expenses=expenses,
                converter=converter,
            ),
            METRIC_BUDGET_USAGE: budget_aggregates,
            METRIC_EMERGENCY_FUND_PROGRESS: goal_aggregates,
            METRIC_PLANNED_PAYMENTS_LOAD: _build_planned_payments_load_payload(
                planned_aggregates=planned_aggregates,
                income=income,
                converter=converter,
            ),
            METRIC_CASH_GAP_RISK: cash_gap,
            METRIC_EXPENSE_STABILITY: expense_stability,
        },
        "dataQuality": {
            "hasEnoughData": bool(transactions),
            "transactionCount": len(transactions),
            "accountCount": account_aggregates["account_count"],
            "budgetCount": budget_aggregates["budgetCount"],
            "goalCount": goal_aggregates["goalCount"],
            "plannedTransactionCount": planned_aggregates["plannedTransactionCount"],
            "periodDays": resolved_period.days,
            "warnings": _build_data_quality_warnings(
                transactions=transactions,
                account_count=account_aggregates["account_count"],
                budget_count=budget_aggregates["budgetCount"],
                goal_count=goal_aggregates["goalCount"],
            ),
        },
    }


def resolve_financial_health_period(
    *,
    user,
    period: str | None = None,
    date_from: date | str | None = None,
    date_to: date | str | None = None,
    today: date | None = None,
) -> FinancialHealthPeriod:
    today = today or get_user_app_today(user)
    period_type = normalize_period(period)

    if period_type == FINANCIAL_HEALTH_PERIOD_MONTH:
        start = today.replace(day=1)
        return FinancialHealthPeriod(
            type=period_type,
            date_from=start,
            date_to=today,
            label="Текущий месяц",
        )

    if period_type == FINANCIAL_HEALTH_PERIOD_QUARTER:
        quarter_start_month = ((today.month - 1) // 3) * 3 + 1
        start = today.replace(month=quarter_start_month, day=1)
        return FinancialHealthPeriod(
            type=period_type,
            date_from=start,
            date_to=today,
            label="Текущий квартал",
        )

    if period_type == FINANCIAL_HEALTH_PERIOD_YEAR:
        start = today.replace(month=1, day=1)
        return FinancialHealthPeriod(
            type=period_type,
            date_from=start,
            date_to=today,
            label="Текущий год",
        )

    start = parse_period_date(date_from, "date_from")
    end = parse_period_date(date_to, "date_to")
    if start is None or end is None:
        raise ValidationError(
            {"period": ["Для периода custom нужно указать date_from и date_to."]}
        )
    if end < start:
        raise ValidationError(
            {"date_to": ["Дата окончания периода не может быть раньше даты начала."]}
        )

    return FinancialHealthPeriod(
        type=period_type,
        date_from=start,
        date_to=end,
        label="Произвольный период",
    )


def normalize_period(value: str | None) -> str:
    period = str(value or FINANCIAL_HEALTH_DEFAULT_PERIOD).strip() or FINANCIAL_HEALTH_DEFAULT_PERIOD
    if period not in FINANCIAL_HEALTH_PERIODS:
        raise ValidationError({"period": ["Недопустимый период расчёта."]})
    return period


def parse_period_date(value: date | str | None, field_name: str) -> date | None:
    if value is None or isinstance(value, date):
        return value

    parsed = parse_date(str(value).strip())
    if parsed is None:
        raise ValidationError({field_name: ["Дата должна быть указана в формате YYYY-MM-DD."]})
    return parsed


def money_payload(amount: Decimal, converter: CurrencyConversionService) -> dict[str, Any]:
    return build_money_payload(amount, currency=converter.display_currency)


def decimal_percent(part: Decimal, whole: Decimal) -> Decimal | None:
    if whole <= DECIMAL_ZERO:
        return None
    return ((part / whole) * Decimal("100")).quantize(PERCENT_QUANT, rounding=ROUND_HALF_UP)


def decimal_ratio(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if denominator <= DECIMAL_ZERO:
        return None
    return (numerator / denominator).quantize(RATIO_QUANT, rounding=ROUND_HALF_UP)


def decimal_to_float(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _convert_amount(
    amount: Decimal,
    *,
    source_currency: str | None,
    converter: CurrencyConversionService,
) -> Decimal:
    return converter.convert_to_display(
        amount,
        source_currency=source_currency,
    ).amount


def _build_account_aggregates(*, user, converter: CurrencyConversionService) -> dict[str, Any]:
    balance = DECIMAL_ZERO
    available_balance = DECIMAL_ZERO
    account_count = 0

    accounts = (
        Account.objects
        .filter(user=user, is_active=True, is_archived=False)
        .order_by("id")
    )
    for account in accounts:
        account_count += 1
        balance += _convert_amount(
            account.balance,
            source_currency=account.currency,
            converter=converter,
        )
        available_balance += _convert_amount(
            account.available_balance,
            source_currency=account.currency,
            converter=converter,
        )

    return {
        "balance": quantize_money(balance),
        "available_balance": quantize_money(available_balance),
        "account_count": account_count,
    }


def _build_cashflow_aggregates(
    *,
    transactions: list[Transaction],
    converter: CurrencyConversionService,
) -> dict[str, Decimal]:
    income = DECIMAL_ZERO
    expenses = DECIMAL_ZERO

    for transaction in transactions:
        amount = _convert_amount(
            transaction.amount,
            source_currency=transaction.account.currency,
            converter=converter,
        )
        if transaction.type == TransactionType.INCOME:
            income += amount
        elif transaction.type == TransactionType.EXPENSE:
            expenses += amount

    return {
        "income": quantize_money(income),
        "expenses": quantize_money(expenses),
    }


def _build_income_expense_ratio_payload(
    *,
    income: Decimal,
    expenses: Decimal,
    converter: CurrencyConversionService,
) -> dict[str, Any]:
    ratio = decimal_ratio(income, expenses)
    return {
        "value": decimal_to_float(ratio),
        "income": money_payload(income, converter),
        "expenses": money_payload(expenses, converter),
        "details": {
            "incomeCoversExpenses": ratio is not None and ratio >= Decimal("1.00"),
        },
    }


def _build_savings_rate_payload(
    *,
    income: Decimal,
    expenses: Decimal,
    converter: CurrencyConversionService,
) -> dict[str, Any]:
    net_balance = income - expenses
    savings_rate = decimal_percent(max(net_balance, DECIMAL_ZERO), income)
    return {
        "value": decimal_to_float(savings_rate),
        "netBalance": money_payload(net_balance, converter),
        "income": money_payload(income, converter),
        "details": {
            "hasPositiveCashflow": net_balance > DECIMAL_ZERO,
        },
    }


def _build_budget_aggregates(
    *,
    user,
    period: FinancialHealthPeriod,
    converter: CurrencyConversionService,
) -> dict[str, Any]:
    budgets = list(
        Budget.objects
        .filter(
            user=user,
            kind=BudgetKind.EXPENSE,
            is_active=True,
            paused=False,
            period_start__lte=period.date_to,
            period_end__gte=period.date_from,
        )
        .select_related("category")
        .order_by("category__name", "id")
    )
    total_limit = DECIMAL_ZERO
    total_spent = DECIMAL_ZERO
    items = []

    for budget in budgets:
        overlap_start = max(period.date_from, budget.period_start)
        overlap_end = min(period.date_to, budget.period_end)
        limit = _convert_amount(
            budget.amount_limit,
            source_currency=budget.currency,
            converter=converter,
        )
        spent = _sum_transactions_for_category(
            user=user,
            category_id=budget.category_id,
            date_from=overlap_start,
            date_to=overlap_end,
            converter=converter,
        )
        usage = decimal_percent(spent, limit)
        total_limit += limit
        total_spent += spent
        items.append(
            {
                "budgetId": budget.id,
                "categoryId": budget.category_id,
                "categoryName": budget.category.name,
                "periodStart": budget.period_start.isoformat(),
                "periodEnd": budget.period_end.isoformat(),
                "limit": money_payload(limit, converter),
                "spent": money_payload(spent, converter),
                "usagePercent": decimal_to_float(usage),
            }
        )

    usage_percent = decimal_percent(total_spent, total_limit)
    return {
        "value": decimal_to_float(usage_percent),
        "budgetCount": len(budgets),
        "totalLimit": money_payload(total_limit, converter),
        "totalSpent": money_payload(total_spent, converter),
        "overLimit": total_limit > DECIMAL_ZERO and total_spent > total_limit,
        "items": items,
    }


def _sum_transactions_for_category(
    *,
    user,
    category_id: int,
    date_from: date,
    date_to: date,
    converter: CurrencyConversionService,
) -> Decimal:
    total = DECIMAL_ZERO
    transactions = (
        Transaction.objects
        .filter(
            user=user,
            category_id=category_id,
            type=TransactionType.EXPENSE,
            operation_date__gte=date_from,
            operation_date__lte=date_to,
        )
        .select_related("account")
        .order_by("id")
    )
    for transaction in transactions:
        total += _convert_amount(
            transaction.amount,
            source_currency=transaction.account.currency,
            converter=converter,
        )
    return quantize_money(total)


def _build_goal_aggregates(*, user, converter: CurrencyConversionService) -> dict[str, Any]:
    goals = list(
        Goal.objects
        .filter(
            user=user,
            status=GoalStatus.ACTIVE,
            category=GoalCategory.SAVINGS,
        )
        .select_related("account")
        .order_by("deadline", "name", "id")
    )
    total_current = DECIMAL_ZERO
    total_target = DECIMAL_ZERO
    items = []

    for goal in goals:
        source_currency = goal.account.currency if goal.account_id else converter.display_currency
        current = _convert_amount(
            goal.current_amount,
            source_currency=source_currency,
            converter=converter,
        )
        target = _convert_amount(
            goal.target_amount,
            source_currency=source_currency,
            converter=converter,
        )
        progress = decimal_percent(current, target)
        total_current += current
        total_target += target
        items.append(
            {
                "goalId": goal.id,
                "name": goal.name,
                "targetAmount": money_payload(target, converter),
                "currentAmount": money_payload(current, converter),
                "progressPercent": decimal_to_float(progress),
                "deadline": goal.deadline.isoformat() if goal.deadline else None,
            }
        )

    overall_progress = decimal_percent(total_current, total_target)
    return {
        "value": decimal_to_float(overall_progress),
        "goalCount": len(goals),
        "targetAmount": money_payload(total_target, converter),
        "currentAmount": money_payload(total_current, converter),
        "items": items,
    }


def _build_planned_transaction_aggregates(
    *,
    user,
    period: FinancialHealthPeriod,
    converter: CurrencyConversionService,
) -> dict[str, Any]:
    planned_transactions = list(
        PlannedTransaction.objects
        .filter(
            user=user,
            include_in_forecast=True,
            status__in=[PlannedStatus.PENDING, PlannedStatus.CONFIRMED],
            planned_date__gte=period.date_from,
            planned_date__lte=period.date_to,
        )
        .select_related("account", "category")
        .order_by("planned_date", "id")
    )
    planned_income = DECIMAL_ZERO
    planned_expenses = DECIMAL_ZERO

    for planned in planned_transactions:
        amount = _convert_amount(
            planned.amount,
            source_currency=planned.account.currency,
            converter=converter,
        )
        if planned.type == TransactionType.INCOME:
            planned_income += amount
        elif planned.type == TransactionType.EXPENSE:
            planned_expenses += amount

    return {
        "plannedIncome": quantize_money(planned_income),
        "plannedExpenses": quantize_money(planned_expenses),
        "plannedNet": quantize_money(planned_income - planned_expenses),
        "plannedTransactionCount": len(planned_transactions),
    }


def _build_planned_payments_load_payload(
    *,
    planned_aggregates: dict[str, Any],
    income: Decimal,
    converter: CurrencyConversionService,
) -> dict[str, Any]:
    planned_expenses = planned_aggregates["plannedExpenses"]
    load_percent = decimal_percent(planned_expenses, income)
    return {
        "value": decimal_to_float(load_percent),
        "plannedIncome": money_payload(planned_aggregates["plannedIncome"], converter),
        "plannedExpenses": money_payload(planned_expenses, converter),
        "plannedNet": money_payload(planned_aggregates["plannedNet"], converter),
        "plannedTransactionCount": planned_aggregates["plannedTransactionCount"],
    }


def _build_cash_gap_aggregates(
    *,
    account_aggregates: dict[str, Any],
    planned_aggregates: dict[str, Any],
    converter: CurrencyConversionService,
) -> dict[str, Any]:
    available_balance = account_aggregates["available_balance"]
    projected_balance = available_balance + planned_aggregates["plannedNet"]
    gap_amount = abs(projected_balance) if projected_balance < DECIMAL_ZERO else DECIMAL_ZERO

    return {
        "value": decimal_to_float(gap_amount),
        "availableBalance": money_payload(available_balance, converter),
        "plannedNet": money_payload(planned_aggregates["plannedNet"], converter),
        "projectedBalance": money_payload(projected_balance, converter),
        "gapAmount": money_payload(gap_amount, converter),
        "hasCashGapRisk": projected_balance < DECIMAL_ZERO,
    }


def _build_expense_stability_aggregates(
    *,
    transactions: list[Transaction],
    period: FinancialHealthPeriod,
    converter: CurrencyConversionService,
) -> dict[str, Any]:
    daily_expenses: dict[date, Decimal] = defaultdict(lambda: DECIMAL_ZERO)
    for transaction in transactions:
        if transaction.type != TransactionType.EXPENSE:
            continue
        daily_expenses[transaction.operation_date] += _convert_amount(
            transaction.amount,
            source_currency=transaction.account.currency,
            converter=converter,
        )

    expense_days = len(daily_expenses)
    total_expenses = sum(daily_expenses.values(), DECIMAL_ZERO)
    average_daily_expense = quantize_money(total_expenses / Decimal(period.days)) if period.days else DECIMAL_ZERO
    max_daily_expense = quantize_money(max(daily_expenses.values(), default=DECIMAL_ZERO))
    active_days_rate = decimal_percent(Decimal(expense_days), Decimal(period.days))
    concentration_ratio = decimal_ratio(max_daily_expense, average_daily_expense)

    return {
        "value": decimal_to_float(active_days_rate),
        "daysWithExpenses": expense_days,
        "periodDays": period.days,
        "activeDaysRate": decimal_to_float(active_days_rate),
        "averageDailyExpense": money_payload(average_daily_expense, converter),
        "maxDailyExpense": money_payload(max_daily_expense, converter),
        "concentrationRatio": decimal_to_float(concentration_ratio),
        "dailyExpenses": [
            {
                "date": day.isoformat(),
                "amount": money_payload(quantize_money(amount), converter),
            }
            for day, amount in sorted(daily_expenses.items())
        ],
    }


def _build_data_quality_warnings(
    *,
    transactions: list[Transaction],
    account_count: int,
    budget_count: int,
    goal_count: int,
) -> list[str]:
    warnings = []
    if account_count == 0:
        warnings.append("У пользователя нет активных счетов для расчёта финансового здоровья.")
    if not transactions:
        warnings.append("За выбранный период нет операций, часть метрик может быть пустой.")
    if budget_count == 0:
        warnings.append("Нет активных бюджетов за выбранный период.")
    if goal_count == 0:
        warnings.append("Нет активных целей накоплений для оценки финансовой подушки.")
    return warnings
