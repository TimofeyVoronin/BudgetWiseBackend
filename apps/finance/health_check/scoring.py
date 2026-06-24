from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Mapping

from apps.finance.health_check.constants import (
    FINANCIAL_HEALTH_SCORE_MAX,
    FINANCIAL_HEALTH_SCORE_MIN,
    METRIC_BUDGET_USAGE,
    METRIC_CASH_GAP_RISK,
    METRIC_EMERGENCY_FUND_PROGRESS,
    METRIC_EXPENSE_STABILITY,
    METRIC_INCOME_EXPENSE_RATIO,
    METRIC_PLANNED_PAYMENTS_LOAD,
    METRIC_SAVINGS_RATE,
)
from apps.finance.health_check.contracts import (
    METRIC_DEFINITIONS,
    get_financial_health_level,
)
from apps.finance.health_check.services import build_financial_health_aggregates

DECIMAL_ZERO = Decimal("0")
DECIMAL_ONE = Decimal("1")
SCORE_QUANT = Decimal("1")


def build_financial_health_summary(
    *,
    user,
    period: str | None = None,
    date_from=None,
    date_to=None,
    currency: str | None = None,
) -> dict[str, Any]:
    """Return the Financial Health Check summary with score and metric levels.

    The function is read-only: it reuses aggregate values from BUD-1152 and
    only adds scoring data on top of them. It does not create or update user
    accounts, transactions, budgets, goals, or planned operations.
    """

    aggregates = build_financial_health_aggregates(
        user=user,
        period=period,
        date_from=date_from,
        date_to=date_to,
        currency=currency,
    )
    score_payload = build_financial_health_score(aggregates)

    return {
        "score": score_payload["score"],
        "level": score_payload["level"],
        "period": aggregates["period"],
        "currency": aggregates["currency"],
        "totals": aggregates["totals"],
        "metrics": score_payload["metrics"],
        "recommendations": [],
        "dataQuality": aggregates["dataQuality"],
    }


def build_financial_health_score(aggregates: Mapping[str, Any]) -> dict[str, Any]:
    aggregate_metrics = aggregates.get("metrics") or {}
    metric_scores = []
    weighted_sum = DECIMAL_ZERO
    total_weight = 0

    for definition in METRIC_DEFINITIONS:
        aggregate = _as_mapping(aggregate_metrics.get(definition.id))
        score = score_financial_health_metric(definition.id, aggregate)
        weighted_sum += Decimal(score) * Decimal(definition.weight)
        total_weight += definition.weight
        metric_scores.append(
            {
                "id": definition.id,
                "label": definition.label,
                "description": definition.description,
                "category": definition.category,
                "weight": definition.weight,
                "unit": definition.unit,
                "higherIsBetter": definition.higherIsBetter,
                "value": aggregate.get("value"),
                "score": score,
                "level": get_financial_health_level(score),
                "details": _build_metric_details(aggregate),
            }
        )

    overall_score = _clamp_score(
        (weighted_sum / Decimal(total_weight)).quantize(
            SCORE_QUANT,
            rounding=ROUND_HALF_UP,
        )
        if total_weight
        else DECIMAL_ZERO
    )
    return {
        "score": overall_score,
        "level": get_financial_health_level(overall_score),
        "metrics": metric_scores,
    }


def score_financial_health_metric(metric_id: str, aggregate: Mapping[str, Any]) -> int:
    if metric_id == METRIC_INCOME_EXPENSE_RATIO:
        return _score_income_expense_ratio(aggregate)
    if metric_id == METRIC_SAVINGS_RATE:
        return _score_savings_rate(aggregate)
    if metric_id == METRIC_BUDGET_USAGE:
        return _score_budget_usage(aggregate)
    if metric_id == METRIC_EMERGENCY_FUND_PROGRESS:
        return _score_emergency_fund_progress(aggregate)
    if metric_id == METRIC_CASH_GAP_RISK:
        return _score_cash_gap_risk(aggregate)
    if metric_id == METRIC_PLANNED_PAYMENTS_LOAD:
        return _score_planned_payments_load(aggregate)
    if metric_id == METRIC_EXPENSE_STABILITY:
        return _score_expense_stability(aggregate)
    return FINANCIAL_HEALTH_SCORE_MIN


def _score_income_expense_ratio(aggregate: Mapping[str, Any]) -> int:
    ratio = _to_decimal_or_none(aggregate.get("value"))
    income = _money_amount(aggregate.get("income"))
    expenses = _money_amount(aggregate.get("expenses"))

    if ratio is None:
        if income > DECIMAL_ZERO and expenses == DECIMAL_ZERO:
            return 100
        return 0

    if ratio >= Decimal("2.00"):
        return 100
    if ratio >= Decimal("1.50"):
        return 90
    if ratio >= Decimal("1.00"):
        return 75
    if ratio >= Decimal("0.80"):
        return 55
    if ratio >= Decimal("0.50"):
        return 35
    return 15


def _score_savings_rate(aggregate: Mapping[str, Any]) -> int:
    savings_rate = _to_decimal_or_none(aggregate.get("value"))
    income = _money_amount(aggregate.get("income"))

    if savings_rate is None:
        return 0 if income <= DECIMAL_ZERO else 20
    if savings_rate >= Decimal("30.00"):
        return 100
    if savings_rate >= Decimal("20.00"):
        return 90
    if savings_rate >= Decimal("10.00"):
        return 75
    if savings_rate > DECIMAL_ZERO:
        return 60
    return 35


def _score_budget_usage(aggregate: Mapping[str, Any]) -> int:
    usage = _to_decimal_or_none(aggregate.get("value"))
    budget_count = int(aggregate.get("budgetCount") or 0)

    if budget_count == 0 or usage is None:
        return 50
    if usage <= Decimal("70.00"):
        return 100
    if usage <= Decimal("90.00"):
        return 85
    if usage <= Decimal("100.00"):
        return 70
    if usage <= Decimal("120.00"):
        return 45
    return 20


def _score_emergency_fund_progress(aggregate: Mapping[str, Any]) -> int:
    progress = _to_decimal_or_none(aggregate.get("value"))
    goal_count = int(aggregate.get("goalCount") or 0)

    if goal_count == 0 or progress is None:
        return 40
    if progress >= Decimal("100.00"):
        return 100
    if progress >= Decimal("75.00"):
        return 90
    if progress >= Decimal("50.00"):
        return 75
    if progress >= Decimal("25.00"):
        return 55
    if progress > DECIMAL_ZERO:
        return 35
    return 20


def _score_cash_gap_risk(aggregate: Mapping[str, Any]) -> int:
    if not aggregate.get("hasCashGapRisk"):
        return 100

    available_balance = _money_amount(aggregate.get("availableBalance"))
    gap_amount = _money_amount(aggregate.get("gapAmount"))
    risk_base = max(abs(available_balance) + gap_amount, DECIMAL_ONE)
    gap_ratio = gap_amount / risk_base

    if gap_ratio >= Decimal("0.75"):
        return 10
    if gap_ratio >= Decimal("0.50"):
        return 20
    if gap_ratio >= Decimal("0.25"):
        return 35
    return 50


def _score_planned_payments_load(aggregate: Mapping[str, Any]) -> int:
    load = _to_decimal_or_none(aggregate.get("value"))
    planned_expenses = _money_amount(aggregate.get("plannedExpenses"))

    if planned_expenses <= DECIMAL_ZERO:
        return 100
    if load is None:
        return 30
    if load <= Decimal("10.00"):
        return 100
    if load <= Decimal("25.00"):
        return 85
    if load <= Decimal("40.00"):
        return 65
    if load <= Decimal("60.00"):
        return 45
    return 20


def _score_expense_stability(aggregate: Mapping[str, Any]) -> int:
    expense_days = int(aggregate.get("daysWithExpenses") or 0)
    concentration_ratio = _to_decimal_or_none(aggregate.get("concentrationRatio"))

    if expense_days == 0:
        return 50
    if concentration_ratio is None:
        return 70
    if concentration_ratio <= Decimal("2.00"):
        return 100
    if concentration_ratio <= Decimal("3.00"):
        return 85
    if concentration_ratio <= Decimal("5.00"):
        return 65
    if concentration_ratio <= Decimal("8.00"):
        return 45
    return 25


def _build_metric_details(aggregate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in aggregate.items()
        if key != "value"
    }


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _money_amount(value: Any) -> Decimal:
    if not isinstance(value, Mapping):
        return DECIMAL_ZERO
    return _to_decimal_or_none(value.get("amount")) or DECIMAL_ZERO


def _to_decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _clamp_score(value: Decimal | int | float) -> int:
    decimal_value = _to_decimal_or_none(value) or DECIMAL_ZERO
    normalized = max(
        Decimal(FINANCIAL_HEALTH_SCORE_MIN),
        min(Decimal(FINANCIAL_HEALTH_SCORE_MAX), decimal_value),
    )
    return int(normalized)
