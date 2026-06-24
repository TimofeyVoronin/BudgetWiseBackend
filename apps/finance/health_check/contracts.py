from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from apps.finance.health_check.constants import (
    FINANCIAL_HEALTH_DEFAULT_CURRENCY,
    FINANCIAL_HEALTH_DEFAULT_PERIOD,
    FINANCIAL_HEALTH_LEVEL_CRITICAL,
    FINANCIAL_HEALTH_LEVEL_EXCELLENT,
    FINANCIAL_HEALTH_LEVEL_GOOD,
    FINANCIAL_HEALTH_LEVEL_RISK,
    FINANCIAL_HEALTH_LEVEL_WARNING,
    FINANCIAL_HEALTH_METRIC_CATEGORIES,
    FINANCIAL_HEALTH_METRIC_WEIGHTS,
    FINANCIAL_HEALTH_PERIOD_CUSTOM,
    FINANCIAL_HEALTH_PERIOD_MONTH,
    FINANCIAL_HEALTH_PERIOD_QUARTER,
    FINANCIAL_HEALTH_PERIOD_YEAR,
    FINANCIAL_HEALTH_RECOMMENDATION_PRIORITY_HIGH,
    FINANCIAL_HEALTH_RECOMMENDATION_PRIORITY_LOW,
    FINANCIAL_HEALTH_RECOMMENDATION_PRIORITY_MEDIUM,
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


@dataclass(frozen=True)
class FinancialHealthMetricDefinition:
    id: str
    label: str
    description: str
    category: str
    weight: int
    unit: str
    higherIsBetter: bool
    source: str


@dataclass(frozen=True)
class FinancialHealthLevelDefinition:
    value: str
    label: str
    minScore: int
    maxScore: int
    description: str


@dataclass(frozen=True)
class FinancialHealthPeriodDefinition:
    value: str
    label: str
    requiresCustomDates: bool


@dataclass(frozen=True)
class FinancialHealthRecommendationPriorityDefinition:
    value: str
    label: str
    description: str


METRIC_DEFINITIONS = [
    FinancialHealthMetricDefinition(
        id=METRIC_INCOME_EXPENSE_RATIO,
        label="Соотношение доходов и расходов",
        description="Показывает, насколько доходы пользователя покрывают расходы за выбранный период.",
        category=FINANCIAL_HEALTH_METRIC_CATEGORIES[METRIC_INCOME_EXPENSE_RATIO],
        weight=FINANCIAL_HEALTH_METRIC_WEIGHTS[METRIC_INCOME_EXPENSE_RATIO],
        unit="ratio",
        higherIsBetter=True,
        source="transactions",
    ),
    FinancialHealthMetricDefinition(
        id=METRIC_SAVINGS_RATE,
        label="Доля сбережений",
        description="Показывает, какая часть доходов остаётся после расходов.",
        category=FINANCIAL_HEALTH_METRIC_CATEGORIES[METRIC_SAVINGS_RATE],
        weight=FINANCIAL_HEALTH_METRIC_WEIGHTS[METRIC_SAVINGS_RATE],
        unit="percent",
        higherIsBetter=True,
        source="transactions",
    ),
    FinancialHealthMetricDefinition(
        id=METRIC_BUDGET_USAGE,
        label="Использование бюджетов",
        description="Оценивает, насколько расходы укладываются в заданные бюджеты.",
        category=FINANCIAL_HEALTH_METRIC_CATEGORIES[METRIC_BUDGET_USAGE],
        weight=FINANCIAL_HEALTH_METRIC_WEIGHTS[METRIC_BUDGET_USAGE],
        unit="percent",
        higherIsBetter=False,
        source="budgets, transactions",
    ),
    FinancialHealthMetricDefinition(
        id=METRIC_EMERGENCY_FUND_PROGRESS,
        label="Прогресс финансовой подушки",
        description="Оценивает прогресс цели, связанной с накоплением резервного фонда.",
        category=FINANCIAL_HEALTH_METRIC_CATEGORIES[METRIC_EMERGENCY_FUND_PROGRESS],
        weight=FINANCIAL_HEALTH_METRIC_WEIGHTS[METRIC_EMERGENCY_FUND_PROGRESS],
        unit="percent",
        higherIsBetter=True,
        source="goals",
    ),
    FinancialHealthMetricDefinition(
        id=METRIC_CASH_GAP_RISK,
        label="Риск кассового разрыва",
        description="Оценивает вероятность ухода баланса ниже безопасного уровня с учётом будущих платежей.",
        category=FINANCIAL_HEALTH_METRIC_CATEGORIES[METRIC_CASH_GAP_RISK],
        weight=FINANCIAL_HEALTH_METRIC_WEIGHTS[METRIC_CASH_GAP_RISK],
        unit="risk",
        higherIsBetter=False,
        source="accounts, planned transactions",
    ),
    FinancialHealthMetricDefinition(
        id=METRIC_PLANNED_PAYMENTS_LOAD,
        label="Нагрузка планируемых платежей",
        description="Показывает, какую долю доходов могут занять будущие планируемые расходы.",
        category=FINANCIAL_HEALTH_METRIC_CATEGORIES[METRIC_PLANNED_PAYMENTS_LOAD],
        weight=FINANCIAL_HEALTH_METRIC_WEIGHTS[METRIC_PLANNED_PAYMENTS_LOAD],
        unit="percent",
        higherIsBetter=False,
        source="planned transactions, transactions",
    ),
    FinancialHealthMetricDefinition(
        id=METRIC_EXPENSE_STABILITY,
        label="Стабильность расходов",
        description="Оценивает, насколько равномерно распределены расходы по дням или месяцам периода.",
        category=FINANCIAL_HEALTH_METRIC_CATEGORIES[METRIC_EXPENSE_STABILITY],
        weight=FINANCIAL_HEALTH_METRIC_WEIGHTS[METRIC_EXPENSE_STABILITY],
        unit="score",
        higherIsBetter=True,
        source="transactions",
    ),
]

LEVEL_DEFINITIONS = [
    FinancialHealthLevelDefinition(
        value=FINANCIAL_HEALTH_LEVEL_CRITICAL,
        label="Критическое состояние",
        minScore=0,
        maxScore=39,
        description="Высокий финансовый риск, требуется срочное внимание к расходам и обязательствам.",
    ),
    FinancialHealthLevelDefinition(
        value=FINANCIAL_HEALTH_LEVEL_RISK,
        label="Зона риска",
        minScore=40,
        maxScore=59,
        description="Есть заметные проблемы с бюджетом, расходами или будущими платежами.",
    ),
    FinancialHealthLevelDefinition(
        value=FINANCIAL_HEALTH_LEVEL_WARNING,
        label="Требует внимания",
        minScore=60,
        maxScore=74,
        description="Финансовое состояние в целом управляемое, но есть слабые места.",
    ),
    FinancialHealthLevelDefinition(
        value=FINANCIAL_HEALTH_LEVEL_GOOD,
        label="Хорошее состояние",
        minScore=75,
        maxScore=89,
        description="Большинство финансовых показателей в норме.",
    ),
    FinancialHealthLevelDefinition(
        value=FINANCIAL_HEALTH_LEVEL_EXCELLENT,
        label="Отличное состояние",
        minScore=90,
        maxScore=100,
        description="Финансовые показатели устойчивые, серьёзных рисков не выявлено.",
    ),
]

PERIOD_DEFINITIONS = [
    FinancialHealthPeriodDefinition(
        value=FINANCIAL_HEALTH_PERIOD_MONTH,
        label="Месяц",
        requiresCustomDates=False,
    ),
    FinancialHealthPeriodDefinition(
        value=FINANCIAL_HEALTH_PERIOD_QUARTER,
        label="Квартал",
        requiresCustomDates=False,
    ),
    FinancialHealthPeriodDefinition(
        value=FINANCIAL_HEALTH_PERIOD_YEAR,
        label="Год",
        requiresCustomDates=False,
    ),
    FinancialHealthPeriodDefinition(
        value=FINANCIAL_HEALTH_PERIOD_CUSTOM,
        label="Произвольный период",
        requiresCustomDates=True,
    ),
]

RECOMMENDATION_PRIORITY_DEFINITIONS = [
    FinancialHealthRecommendationPriorityDefinition(
        value=FINANCIAL_HEALTH_RECOMMENDATION_PRIORITY_HIGH,
        label="Высокий приоритет",
        description="Рекомендация связана с высоким риском или сильным отклонением метрики.",
    ),
    FinancialHealthRecommendationPriorityDefinition(
        value=FINANCIAL_HEALTH_RECOMMENDATION_PRIORITY_MEDIUM,
        label="Средний приоритет",
        description="Рекомендация помогает улучшить показатель, который требует внимания.",
    ),
    FinancialHealthRecommendationPriorityDefinition(
        value=FINANCIAL_HEALTH_RECOMMENDATION_PRIORITY_LOW,
        label="Низкий приоритет",
        description="Рекомендация носит поддерживающий или профилактический характер.",
    ),
]


def build_financial_health_meta() -> dict[str, Any]:
    return {
        "scoreRange": {
            "min": FINANCIAL_HEALTH_SCORE_MIN,
            "max": FINANCIAL_HEALTH_SCORE_MAX,
        },
        "defaultPeriod": FINANCIAL_HEALTH_DEFAULT_PERIOD,
        "defaultCurrency": FINANCIAL_HEALTH_DEFAULT_CURRENCY,
        "periods": [asdict(period) for period in PERIOD_DEFINITIONS],
        "levels": [asdict(level) for level in LEVEL_DEFINITIONS],
        "metrics": [asdict(metric) for metric in METRIC_DEFINITIONS],
        "recommendationPriorities": [
            asdict(priority)
            for priority in RECOMMENDATION_PRIORITY_DEFINITIONS
        ],
        "summaryContract": build_financial_health_summary_contract(),
    }


def build_financial_health_summary_contract() -> dict[str, Any]:
    return {
        "score": "integer 0..100",
        "level": "excellent|good|warning|risk|critical",
        "period": {
            "type": "month|quarter|year|custom",
            "dateFrom": "YYYY-MM-DD",
            "dateTo": "YYYY-MM-DD",
            "label": "string",
        },
        "metrics": [
            {
                "id": "string",
                "label": "string",
                "value": "number|null",
                "score": "integer 0..100",
                "level": "excellent|good|warning|risk|critical",
                "weight": "integer",
                "unit": "percent|ratio|risk|score|money",
                "description": "string",
                "details": "object",
            }
        ],
        "recommendations": [
            {
                "code": "string",
                "priority": "high|medium|low",
                "metricId": "string",
                "title": "string",
                "text": "string",
            }
        ],
        "dataQuality": {
            "hasEnoughData": "boolean",
            "transactionCount": "integer",
            "periodDays": "integer",
            "warnings": ["string"],
        },
    }


def get_financial_health_metric_ids() -> list[str]:
    return [metric.id for metric in METRIC_DEFINITIONS]


def get_financial_health_level(score: int | float) -> str:
    normalized_score = max(FINANCIAL_HEALTH_SCORE_MIN, min(FINANCIAL_HEALTH_SCORE_MAX, int(score)))

    for level in LEVEL_DEFINITIONS:
        if level.minScore <= normalized_score <= level.maxScore:
            return level.value

    return FINANCIAL_HEALTH_LEVEL_CRITICAL


def validate_metric_weights() -> bool:
    return sum(metric.weight for metric in METRIC_DEFINITIONS) == 100
