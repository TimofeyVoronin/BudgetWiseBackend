from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from apps.finance.health_check.constants import (
    FINANCIAL_HEALTH_RECOMMENDATION_PRIORITY_HIGH,
    FINANCIAL_HEALTH_RECOMMENDATION_PRIORITY_LOW,
    FINANCIAL_HEALTH_RECOMMENDATION_PRIORITY_MEDIUM,
    MAX_FINANCIAL_HEALTH_RECOMMENDATIONS,
    METRIC_BUDGET_USAGE,
    METRIC_CASH_GAP_RISK,
    METRIC_EMERGENCY_FUND_PROGRESS,
    METRIC_EXPENSE_STABILITY,
    METRIC_INCOME_EXPENSE_RATIO,
    METRIC_PLANNED_PAYMENTS_LOAD,
    METRIC_SAVINGS_RATE,
    RECOMMENDATION_BUDGET_OVER_LIMIT,
    RECOMMENDATION_CASH_GAP_RISK,
    RECOMMENDATION_HIGH_PLANNED_PAYMENTS_LOAD,
    RECOMMENDATION_INSUFFICIENT_CASHFLOW_DATA,
    RECOMMENDATION_LOW_SAVINGS_RATE,
    RECOMMENDATION_NEGATIVE_NET_BALANCE,
    RECOMMENDATION_UNSTABLE_EXPENSES,
    RECOMMENDATION_WEAK_EMERGENCY_FUND,
)

DECIMAL_ZERO = Decimal("0")
PRIORITY_ORDER = {
    FINANCIAL_HEALTH_RECOMMENDATION_PRIORITY_HIGH: 0,
    FINANCIAL_HEALTH_RECOMMENDATION_PRIORITY_MEDIUM: 1,
    FINANCIAL_HEALTH_RECOMMENDATION_PRIORITY_LOW: 2,
}


@dataclass(frozen=True)
class FinancialHealthRecommendation:
    code: str
    priority: str
    metricId: str
    title: str
    text: str
    action: str
    reason: str
    score: int

    def as_payload(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "priority": self.priority,
            "metricId": self.metricId,
            "title": self.title,
            "text": self.text,
            "action": self.action,
            "reason": self.reason,
        }


def build_financial_health_recommendations(
    *,
    metrics: Sequence[Mapping[str, Any]],
    totals: Mapping[str, Any] | None = None,
    data_quality: Mapping[str, Any] | None = None,
    max_items: int = MAX_FINANCIAL_HEALTH_RECOMMENDATIONS,
) -> list[dict[str, Any]]:
    """Return explainable rule-based recommendations for financial health.

    The function is read-only and uses only already calculated score payloads.
    It does not create recommendation records and does not change user data.
    """

    metrics_by_id = {
        str(metric.get("id")): metric
        for metric in metrics
        if isinstance(metric, Mapping) and metric.get("id")
    }
    recommendations: list[FinancialHealthRecommendation] = []

    recommendations.extend(_build_cashflow_recommendations(metrics_by_id, totals or {}))
    recommendations.extend(_build_budget_recommendations(metrics_by_id))
    recommendations.extend(_build_emergency_fund_recommendations(metrics_by_id))
    recommendations.extend(_build_risk_recommendations(metrics_by_id))
    recommendations.extend(_build_stability_recommendations(metrics_by_id))

    if data_quality and not data_quality.get("hasEnoughData"):
        recommendations.append(
            FinancialHealthRecommendation(
                code=RECOMMENDATION_INSUFFICIENT_CASHFLOW_DATA,
                priority=FINANCIAL_HEALTH_RECOMMENDATION_PRIORITY_LOW,
                metricId=METRIC_INCOME_EXPENSE_RATIO,
                title="Недостаточно данных для точной оценки",
                text=(
                    "За выбранный период мало операций, поэтому часть выводов может быть "
                    "менее точной."
                ),
                action="Добавьте доходы и расходы за период, чтобы оценка стала точнее.",
                reason="dataQuality.hasEnoughData=false",
                score=100,
            )
        )

    unique_by_code = _deduplicate_by_code(recommendations)
    unique_by_code.sort(
        key=lambda item: (
            PRIORITY_ORDER.get(item.priority, 99),
            item.score,
            item.code,
        )
    )
    return [item.as_payload() for item in unique_by_code[:max_items]]


def _build_cashflow_recommendations(
    metrics_by_id: Mapping[str, Mapping[str, Any]],
    totals: Mapping[str, Any],
) -> list[FinancialHealthRecommendation]:
    recommendations = []
    income_expense_ratio = metrics_by_id.get(METRIC_INCOME_EXPENSE_RATIO)
    savings_rate = metrics_by_id.get(METRIC_SAVINGS_RATE)
    net_balance = _money_amount(totals.get("netBalance"))

    if net_balance < DECIMAL_ZERO:
        recommendations.append(
            FinancialHealthRecommendation(
                code=RECOMMENDATION_NEGATIVE_NET_BALANCE,
                priority=FINANCIAL_HEALTH_RECOMMENDATION_PRIORITY_HIGH,
                metricId=METRIC_INCOME_EXPENSE_RATIO,
                title="Расходы превышают доходы",
                text="За выбранный период расходы оказались выше доходов.",
                action=(
                    "Проверьте крупные траты и временно сократите необязательные "
                    "расходы."
                ),
                reason="totals.netBalance.amount<0",
                score=_metric_score(income_expense_ratio),
            )
        )

    if savings_rate and _metric_score(savings_rate) < 75:
        income = _money_amount(_metric_details(savings_rate).get("income"))
        if income <= DECIMAL_ZERO:
            return recommendations
        recommendations.append(
            FinancialHealthRecommendation(
                code=RECOMMENDATION_LOW_SAVINGS_RATE,
                priority=_priority_by_score(_metric_score(savings_rate)),
                metricId=METRIC_SAVINGS_RATE,
                title="Низкая доля сбережений",
                text="После расходов остаётся слишком малая часть дохода.",
                action="Попробуйте откладывать хотя бы 10% дохода сразу после поступления.",
                reason="savingsRate.score<75",
                score=_metric_score(savings_rate),
            )
        )

    return recommendations


def _build_budget_recommendations(
    metrics_by_id: Mapping[str, Mapping[str, Any]],
) -> list[FinancialHealthRecommendation]:
    budget_usage = metrics_by_id.get(METRIC_BUDGET_USAGE)
    if not budget_usage:
        return []

    details = _metric_details(budget_usage)
    budget_count = int(details.get("budgetCount") or 0)
    if budget_count == 0:
        return []

    usage = _to_decimal_or_none(budget_usage.get("value"))
    over_limit = bool(details.get("overLimit"))
    score = _metric_score(budget_usage)

    if not over_limit and score >= 70:
        return []

    priority = (
        FINANCIAL_HEALTH_RECOMMENDATION_PRIORITY_HIGH
        if over_limit or (usage is not None and usage > Decimal("100"))
        else FINANCIAL_HEALTH_RECOMMENDATION_PRIORITY_MEDIUM
    )
    return [
        FinancialHealthRecommendation(
            code=RECOMMENDATION_BUDGET_OVER_LIMIT,
            priority=priority,
            metricId=METRIC_BUDGET_USAGE,
            title="Бюджет требует внимания",
            text="Расходы приблизились к лимиту бюджета или превысили его.",
            action="Посмотрите категории с самым высоким расходом и скорректируйте лимиты.",
            reason="budgetUsage.overLimit=true or budgetUsage.score<70",
            score=score,
        )
    ]


def _build_emergency_fund_recommendations(
    metrics_by_id: Mapping[str, Mapping[str, Any]],
) -> list[FinancialHealthRecommendation]:
    emergency_fund = metrics_by_id.get(METRIC_EMERGENCY_FUND_PROGRESS)
    if not emergency_fund:
        return []

    score = _metric_score(emergency_fund)
    if score >= 75:
        return []

    details = _metric_details(emergency_fund)
    goal_count = int(details.get("goalCount") or 0)
    title = (
        "Создайте цель для финансовой подушки"
        if goal_count == 0
        else "Ускорьте накопление финансовой подушки"
    )

    return [
        FinancialHealthRecommendation(
            code=RECOMMENDATION_WEAK_EMERGENCY_FUND,
            priority=_priority_by_score(score),
            metricId=METRIC_EMERGENCY_FUND_PROGRESS,
            title=title,
            text="Резерв на непредвиденные расходы пока недостаточно сформирован.",
            action="Настройте цель накоплений и регулярно пополняйте её небольшими суммами.",
            reason="emergencyFundProgress.score<75",
            score=score,
        )
    ]


def _build_risk_recommendations(
    metrics_by_id: Mapping[str, Mapping[str, Any]],
) -> list[FinancialHealthRecommendation]:
    recommendations = []

    cash_gap = metrics_by_id.get(METRIC_CASH_GAP_RISK)
    if cash_gap and _metric_details(cash_gap).get("hasCashGapRisk"):
        recommendations.append(
            FinancialHealthRecommendation(
                code=RECOMMENDATION_CASH_GAP_RISK,
                priority=FINANCIAL_HEALTH_RECOMMENDATION_PRIORITY_HIGH,
                metricId=METRIC_CASH_GAP_RISK,
                title="Есть риск кассового разрыва",
                text="С учётом планируемых платежей доступный остаток может стать отрицательным.",
                action="Перенесите часть платежей, пополните счёт или уменьшите ближайшие расходы.",
                reason="cashGapRisk.hasCashGapRisk=true",
                score=_metric_score(cash_gap),
            )
        )

    planned_load = metrics_by_id.get(METRIC_PLANNED_PAYMENTS_LOAD)
    if planned_load and _metric_score(planned_load) < 65:
        recommendations.append(
            FinancialHealthRecommendation(
                code=RECOMMENDATION_HIGH_PLANNED_PAYMENTS_LOAD,
                priority=_priority_by_score(_metric_score(planned_load)),
                metricId=METRIC_PLANNED_PAYMENTS_LOAD,
                title="Высокая нагрузка будущих платежей",
                text="Планируемые расходы занимают слишком большую долю доходов.",
                action="Проверьте будущие платежи и перенесите необязательные списания.",
                reason="plannedPaymentsLoad.score<65",
                score=_metric_score(planned_load),
            )
        )

    return recommendations


def _build_stability_recommendations(
    metrics_by_id: Mapping[str, Mapping[str, Any]],
) -> list[FinancialHealthRecommendation]:
    expense_stability = metrics_by_id.get(METRIC_EXPENSE_STABILITY)
    if not expense_stability:
        return []

    details = _metric_details(expense_stability)
    days_with_expenses = int(details.get("daysWithExpenses") or 0)
    if days_with_expenses == 0:
        return []

    score = _metric_score(expense_stability)
    if score >= 65:
        return []

    return [
        FinancialHealthRecommendation(
            code=RECOMMENDATION_UNSTABLE_EXPENSES,
            priority=_priority_by_score(score),
            metricId=METRIC_EXPENSE_STABILITY,
            title="Расходы распределены неравномерно",
            text="В выбранном периоде есть дни с заметно повышенными расходами.",
            action="Проверьте крупные траты и настройте бюджетные лимиты по категориям.",
            reason="expenseStability.score<65",
            score=score,
        )
    ]


def _deduplicate_by_code(
    recommendations: Sequence[FinancialHealthRecommendation],
) -> list[FinancialHealthRecommendation]:
    unique: dict[str, FinancialHealthRecommendation] = {}
    for item in recommendations:
        existing = unique.get(item.code)
        if existing is None or _recommendation_rank(item) < _recommendation_rank(existing):
            unique[item.code] = item
    return list(unique.values())


def _recommendation_rank(item: FinancialHealthRecommendation) -> tuple[int, int, str]:
    return (
        PRIORITY_ORDER.get(item.priority, 99),
        item.score,
        item.code,
    )


def _priority_by_score(score: int) -> str:
    if score < 50:
        return FINANCIAL_HEALTH_RECOMMENDATION_PRIORITY_HIGH
    if score < 75:
        return FINANCIAL_HEALTH_RECOMMENDATION_PRIORITY_MEDIUM
    return FINANCIAL_HEALTH_RECOMMENDATION_PRIORITY_LOW


def _metric_score(metric: Mapping[str, Any] | None) -> int:
    if not metric:
        return 0
    try:
        return int(metric.get("score") or 0)
    except (TypeError, ValueError):
        return 0


def _metric_details(metric: Mapping[str, Any]) -> Mapping[str, Any]:
    details = metric.get("details")
    return details if isinstance(details, Mapping) else {}


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
