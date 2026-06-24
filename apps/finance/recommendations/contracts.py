from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from apps.finance.recommendations.constants import (
    RECOMMENDATION_ACTION_ACCEPT,
    RECOMMENDATION_ACTION_HIDE,
    RECOMMENDATION_ACTION_REFRESH,
    RECOMMENDATION_ACTION_SNOOZE,
    RECOMMENDATION_ACTION_VIEW,
    RECOMMENDATION_CODE_CHECK_BUDGET_OVERRUN,
    RECOMMENDATION_CODE_COMPLETE_ONBOARDING,
    RECOMMENDATION_CODE_CREATE_BUDGET,
    RECOMMENDATION_CODE_CREATE_EMERGENCY_FUND_GOAL,
    RECOMMENDATION_CODE_FIX_CASH_GAP_RISK,
    RECOMMENDATION_CODE_INCREASE_SAVINGS_RATE,
    RECOMMENDATION_CODE_REDUCE_UNSTABLE_EXPENSES,
    RECOMMENDATION_CODE_REVIEW_PLANNED_PAYMENTS,
    RECOMMENDATION_DEFAULT_PRIORITY,
    RECOMMENDATION_DEFAULT_STATUS,
    RECOMMENDATION_DEFAULT_TTL_DAYS,
    RECOMMENDATION_EVENT_ACCEPTED,
    RECOMMENDATION_EVENT_CREATED,
    RECOMMENDATION_EVENT_EXPIRED,
    RECOMMENDATION_EVENT_HIDDEN,
    RECOMMENDATION_EVENT_REFRESHED,
    RECOMMENDATION_EVENT_SNOOZED,
    RECOMMENDATION_EVENT_VIEWED,
    RECOMMENDATION_GENERATION_MODE_RULE_BASED,
    RECOMMENDATION_MAX_ACTIVE_PER_USER,
    RECOMMENDATION_PRIORITIES,
    RECOMMENDATION_PRIORITY_HIGH,
    RECOMMENDATION_PRIORITY_LOW,
    RECOMMENDATION_PRIORITY_MEDIUM,
    RECOMMENDATION_SNOOZE_DEFAULT_DAYS,
    RECOMMENDATION_SOURCE_BUDGETS,
    RECOMMENDATION_SOURCE_FINANCIAL_HEALTH,
    RECOMMENDATION_SOURCE_GOALS,
    RECOMMENDATION_SOURCE_ONBOARDING,
    RECOMMENDATION_SOURCE_PLANNED_TRANSACTIONS,
    RECOMMENDATION_SOURCE_TRANSACTIONS,
    RECOMMENDATION_STATUS_ACCEPTED,
    RECOMMENDATION_STATUS_ACTIVE,
    RECOMMENDATION_STATUS_EXPIRED,
    RECOMMENDATION_STATUS_HIDDEN,
    RECOMMENDATION_STATUS_NEW,
    RECOMMENDATION_STATUS_SNOOZED,
    RECOMMENDATION_STATUSES,
    RECOMMENDATION_TYPE_BUDGET,
    RECOMMENDATION_TYPE_CASHFLOW,
    RECOMMENDATION_TYPE_EXPENSE_STABILITY,
    RECOMMENDATION_TYPE_FINANCIAL_HEALTH,
    RECOMMENDATION_TYPE_GOAL,
    RECOMMENDATION_TYPE_ONBOARDING,
    RECOMMENDATION_TYPE_PLANNED_PAYMENT,
    RECOMMENDATION_TYPE_SAVING,
    RECOMMENDATION_TYPES,
)


@dataclass(frozen=True)
class RecommendationTypeDefinition:
    value: str
    label: str
    description: str
    source: str


@dataclass(frozen=True)
class RecommendationStatusDefinition:
    value: str
    label: str
    description: str
    visibleInDefaultList: bool
    terminal: bool


@dataclass(frozen=True)
class RecommendationPriorityDefinition:
    value: str
    label: str
    description: str
    sortOrder: int


@dataclass(frozen=True)
class RecommendationActionDefinition:
    value: str
    label: str
    description: str
    targetStatus: str | None


@dataclass(frozen=True)
class RecommendationEventDefinition:
    value: str
    label: str
    description: str


@dataclass(frozen=True)
class RecommendationCodeDefinition:
    value: str
    type: str
    defaultPriority: str
    title: str
    description: str
    source: str


TYPE_DEFINITIONS = [
    RecommendationTypeDefinition(
        value=RECOMMENDATION_TYPE_BUDGET,
        label="Бюджет",
        description="Рекомендации по созданию, настройке и контролю бюджетов.",
        source=RECOMMENDATION_SOURCE_BUDGETS,
    ),
    RecommendationTypeDefinition(
        value=RECOMMENDATION_TYPE_SAVING,
        label="Сбережения",
        description="Рекомендации по увеличению доли сбережений и снижению лишних расходов.",
        source=RECOMMENDATION_SOURCE_TRANSACTIONS,
    ),
    RecommendationTypeDefinition(
        value=RECOMMENDATION_TYPE_GOAL,
        label="Цели",
        description="Рекомендации по созданию и ускорению финансовых целей.",
        source=RECOMMENDATION_SOURCE_GOALS,
    ),
    RecommendationTypeDefinition(
        value=RECOMMENDATION_TYPE_CASHFLOW,
        label="Денежный поток",
        description="Рекомендации по доходам, расходам и чистому остатку периода.",
        source=RECOMMENDATION_SOURCE_TRANSACTIONS,
    ),
    RecommendationTypeDefinition(
        value=RECOMMENDATION_TYPE_PLANNED_PAYMENT,
        label="Планируемые платежи",
        description="Рекомендации по будущим платежам и рискам кассового разрыва.",
        source=RECOMMENDATION_SOURCE_PLANNED_TRANSACTIONS,
    ),
    RecommendationTypeDefinition(
        value=RECOMMENDATION_TYPE_EXPENSE_STABILITY,
        label="Стабильность расходов",
        description="Рекомендации по неравномерным и крупным расходам.",
        source=RECOMMENDATION_SOURCE_TRANSACTIONS,
    ),
    RecommendationTypeDefinition(
        value=RECOMMENDATION_TYPE_ONBOARDING,
        label="Онбординг",
        description="Рекомендации по завершению первичной настройки приложения.",
        source=RECOMMENDATION_SOURCE_ONBOARDING,
    ),
    RecommendationTypeDefinition(
        value=RECOMMENDATION_TYPE_FINANCIAL_HEALTH,
        label="Финансовое здоровье",
        description="Рекомендации на основе Financial Health Check и его метрик.",
        source=RECOMMENDATION_SOURCE_FINANCIAL_HEALTH,
    ),
]

STATUS_DEFINITIONS = [
    RecommendationStatusDefinition(
        value=RECOMMENDATION_STATUS_NEW,
        label="Новая",
        description="Рекомендация создана, но ещё не была показана пользователю.",
        visibleInDefaultList=True,
        terminal=False,
    ),
    RecommendationStatusDefinition(
        value=RECOMMENDATION_STATUS_ACTIVE,
        label="Активная",
        description="Рекомендация доступна пользователю в основном списке.",
        visibleInDefaultList=True,
        terminal=False,
    ),
    RecommendationStatusDefinition(
        value=RECOMMENDATION_STATUS_ACCEPTED,
        label="Принята",
        description="Пользователь принял рекомендацию или подтвердил намерение выполнить действие.",
        visibleInDefaultList=False,
        terminal=True,
    ),
    RecommendationStatusDefinition(
        value=RECOMMENDATION_STATUS_HIDDEN,
        label="Скрыта",
        description="Пользователь скрыл рекомендацию из списка.",
        visibleInDefaultList=False,
        terminal=True,
    ),
    RecommendationStatusDefinition(
        value=RECOMMENDATION_STATUS_SNOOZED,
        label="Отложена",
        description="Пользователь временно отложил рекомендацию.",
        visibleInDefaultList=False,
        terminal=False,
    ),
    RecommendationStatusDefinition(
        value=RECOMMENDATION_STATUS_EXPIRED,
        label="Истекла",
        description="Рекомендация потеряла актуальность по сроку или по изменившимся данным.",
        visibleInDefaultList=False,
        terminal=True,
    ),
]

PRIORITY_DEFINITIONS = [
    RecommendationPriorityDefinition(
        value=RECOMMENDATION_PRIORITY_HIGH,
        label="Высокий приоритет",
        description="Рекомендация связана с высоким риском или сильным отклонением метрики.",
        sortOrder=1,
    ),
    RecommendationPriorityDefinition(
        value=RECOMMENDATION_PRIORITY_MEDIUM,
        label="Средний приоритет",
        description="Рекомендация помогает улучшить показатель, который требует внимания.",
        sortOrder=2,
    ),
    RecommendationPriorityDefinition(
        value=RECOMMENDATION_PRIORITY_LOW,
        label="Низкий приоритет",
        description="Рекомендация носит поддерживающий или профилактический характер.",
        sortOrder=3,
    ),
]

ACTION_DEFINITIONS = [
    RecommendationActionDefinition(
        value=RECOMMENDATION_ACTION_VIEW,
        label="Просмотреть",
        description="Зафиксировать просмотр рекомендации пользователем.",
        targetStatus=None,
    ),
    RecommendationActionDefinition(
        value=RECOMMENDATION_ACTION_ACCEPT,
        label="Принять",
        description="Отметить рекомендацию как принятую пользователем.",
        targetStatus=RECOMMENDATION_STATUS_ACCEPTED,
    ),
    RecommendationActionDefinition(
        value=RECOMMENDATION_ACTION_HIDE,
        label="Скрыть",
        description="Скрыть рекомендацию из основного списка.",
        targetStatus=RECOMMENDATION_STATUS_HIDDEN,
    ),
    RecommendationActionDefinition(
        value=RECOMMENDATION_ACTION_SNOOZE,
        label="Отложить",
        description="Временно отложить рекомендацию на выбранный срок.",
        targetStatus=RECOMMENDATION_STATUS_SNOOZED,
    ),
    RecommendationActionDefinition(
        value=RECOMMENDATION_ACTION_REFRESH,
        label="Обновить",
        description="Запустить повторную генерацию рекомендаций по текущим данным пользователя.",
        targetStatus=None,
    ),
]

EVENT_DEFINITIONS = [
    RecommendationEventDefinition(
        value=RECOMMENDATION_EVENT_CREATED,
        label="Создана",
        description="Рекомендация создана генератором.",
    ),
    RecommendationEventDefinition(
        value=RECOMMENDATION_EVENT_VIEWED,
        label="Просмотрена",
        description="Пользователь увидел рекомендацию.",
    ),
    RecommendationEventDefinition(
        value=RECOMMENDATION_EVENT_ACCEPTED,
        label="Принята",
        description="Пользователь принял рекомендацию.",
    ),
    RecommendationEventDefinition(
        value=RECOMMENDATION_EVENT_HIDDEN,
        label="Скрыта",
        description="Пользователь скрыл рекомендацию.",
    ),
    RecommendationEventDefinition(
        value=RECOMMENDATION_EVENT_SNOOZED,
        label="Отложена",
        description="Пользователь отложил рекомендацию.",
    ),
    RecommendationEventDefinition(
        value=RECOMMENDATION_EVENT_EXPIRED,
        label="Истекла",
        description="Рекомендация потеряла актуальность.",
    ),
    RecommendationEventDefinition(
        value=RECOMMENDATION_EVENT_REFRESHED,
        label="Обновлена",
        description="Рекомендации пользователя были обновлены по текущим данным.",
    ),
]

CODE_DEFINITIONS = [
    RecommendationCodeDefinition(
        value=RECOMMENDATION_CODE_CREATE_BUDGET,
        type=RECOMMENDATION_TYPE_BUDGET,
        defaultPriority=RECOMMENDATION_PRIORITY_MEDIUM,
        title="Создайте бюджет по основной категории расходов",
        description="Появляется, если у пользователя нет активных бюджетов или расходы требуют контроля.",
        source=RECOMMENDATION_SOURCE_BUDGETS,
    ),
    RecommendationCodeDefinition(
        value=RECOMMENDATION_CODE_REDUCE_UNSTABLE_EXPENSES,
        type=RECOMMENDATION_TYPE_EXPENSE_STABILITY,
        defaultPriority=RECOMMENDATION_PRIORITY_HIGH,
        title="Проверьте неравномерные расходы",
        description="Появляется при высокой концентрации расходов в отдельные дни.",
        source=RECOMMENDATION_SOURCE_FINANCIAL_HEALTH,
    ),
    RecommendationCodeDefinition(
        value=RECOMMENDATION_CODE_INCREASE_SAVINGS_RATE,
        type=RECOMMENDATION_TYPE_SAVING,
        defaultPriority=RECOMMENDATION_PRIORITY_MEDIUM,
        title="Увеличьте долю сбережений",
        description="Появляется при низкой доле сбережений относительно дохода.",
        source=RECOMMENDATION_SOURCE_FINANCIAL_HEALTH,
    ),
    RecommendationCodeDefinition(
        value=RECOMMENDATION_CODE_CREATE_EMERGENCY_FUND_GOAL,
        type=RECOMMENDATION_TYPE_GOAL,
        defaultPriority=RECOMMENDATION_PRIORITY_HIGH,
        title="Создайте цель для финансовой подушки",
        description="Появляется, если резервная цель отсутствует или прогресс по ней низкий.",
        source=RECOMMENDATION_SOURCE_GOALS,
    ),
    RecommendationCodeDefinition(
        value=RECOMMENDATION_CODE_REVIEW_PLANNED_PAYMENTS,
        type=RECOMMENDATION_TYPE_PLANNED_PAYMENT,
        defaultPriority=RECOMMENDATION_PRIORITY_MEDIUM,
        title="Проверьте будущие платежи",
        description="Появляется при высокой нагрузке планируемых платежей.",
        source=RECOMMENDATION_SOURCE_PLANNED_TRANSACTIONS,
    ),
    RecommendationCodeDefinition(
        value=RECOMMENDATION_CODE_FIX_CASH_GAP_RISK,
        type=RECOMMENDATION_TYPE_CASHFLOW,
        defaultPriority=RECOMMENDATION_PRIORITY_HIGH,
        title="Снизьте риск кассового разрыва",
        description="Появляется, если прогнозируемый остаток может стать отрицательным.",
        source=RECOMMENDATION_SOURCE_FINANCIAL_HEALTH,
    ),
    RecommendationCodeDefinition(
        value=RECOMMENDATION_CODE_COMPLETE_ONBOARDING,
        type=RECOMMENDATION_TYPE_ONBOARDING,
        defaultPriority=RECOMMENDATION_PRIORITY_LOW,
        title="Завершите первичную настройку",
        description="Появляется, если пользователь не завершил onboarding-анкету.",
        source=RECOMMENDATION_SOURCE_ONBOARDING,
    ),
    RecommendationCodeDefinition(
        value=RECOMMENDATION_CODE_CHECK_BUDGET_OVERRUN,
        type=RECOMMENDATION_TYPE_BUDGET,
        defaultPriority=RECOMMENDATION_PRIORITY_HIGH,
        title="Проверьте превышение бюджета",
        description="Появляется, если расходы приблизились к лимиту или превысили его.",
        source=RECOMMENDATION_SOURCE_FINANCIAL_HEALTH,
    ),
]


def _asdict(items: list[Any]) -> list[dict[str, Any]]:
    return [asdict(item) for item in items]


def get_recommendation_type_values() -> list[str]:
    return [item.value for item in TYPE_DEFINITIONS]


def get_recommendation_status_values() -> list[str]:
    return [item.value for item in STATUS_DEFINITIONS]


def get_recommendation_priority_values() -> list[str]:
    return [item.value for item in PRIORITY_DEFINITIONS]


def get_recommendation_action_values() -> list[str]:
    return [item.value for item in ACTION_DEFINITIONS]


def get_recommendation_code_values() -> list[str]:
    return [item.value for item in CODE_DEFINITIONS]


def validate_recommendation_contract() -> bool:
    return (
        get_recommendation_type_values() == RECOMMENDATION_TYPES
        and get_recommendation_status_values() == RECOMMENDATION_STATUSES
        and get_recommendation_priority_values() == RECOMMENDATION_PRIORITIES
        and len(set(get_recommendation_code_values())) == len(CODE_DEFINITIONS)
    )


def build_recommendations_meta() -> dict[str, Any]:
    return {
        "generation": {
            "mode": RECOMMENDATION_GENERATION_MODE_RULE_BASED,
            "mlEnabled": False,
            "usesFinancialHealthCheck": True,
            "defaultTtlDays": RECOMMENDATION_DEFAULT_TTL_DAYS,
            "defaultSnoozeDays": RECOMMENDATION_SNOOZE_DEFAULT_DAYS,
            "maxActivePerUser": RECOMMENDATION_MAX_ACTIVE_PER_USER,
        },
        "defaults": {
            "status": RECOMMENDATION_DEFAULT_STATUS,
            "priority": RECOMMENDATION_DEFAULT_PRIORITY,
        },
        "types": _asdict(TYPE_DEFINITIONS),
        "statuses": _asdict(STATUS_DEFINITIONS),
        "priorities": _asdict(PRIORITY_DEFINITIONS),
        "actions": _asdict(ACTION_DEFINITIONS),
        "events": _asdict(EVENT_DEFINITIONS),
        "codes": _asdict(CODE_DEFINITIONS),
        "endpoints": {
            "meta": "GET /api/v1/finance/recommendations/meta/",
            "list": "GET /api/v1/finance/recommendations/",
            "refresh": "POST /api/v1/finance/recommendations/refresh/",
            "accept": "POST /api/v1/finance/recommendations/{id}/accept/",
            "hide": "POST /api/v1/finance/recommendations/{id}/hide/",
            "snooze": "POST /api/v1/finance/recommendations/{id}/snooze/",
            "stats": "GET /api/v1/finance/recommendations/stats/",
        },
        "listQueryParameters": {
            "status": "new|active|accepted|hidden|snoozed|expired",
            "type": "budget|saving|goal|cashflow|planned_payment|expense_stability|onboarding|financial_health",
            "priority": "high|medium|low",
            "ordering": "priority|-priority|created_at|-created_at|expires_at|-expires_at",
        },
        "itemContract": {
            "id": "integer",
            "code": "string",
            "type": "budget|saving|goal|cashflow|planned_payment|expense_stability|onboarding|financial_health",
            "priority": "high|medium|low",
            "status": "new|active|accepted|hidden|snoozed|expired",
            "title": "string",
            "text": "string",
            "action": "string",
            "reason": "string",
            "source": "string",
            "context": "object",
            "expiresAt": "datetime|null",
            "snoozedUntil": "datetime|null",
            "createdAt": "datetime",
            "updatedAt": "datetime",
        },
        "statsContract": {
            "total": "integer",
            "active": "integer",
            "accepted": "integer",
            "hidden": "integer",
            "snoozed": "integer",
            "expired": "integer",
            "acceptanceRate": "number",
            "byType": "object",
            "byPriority": "object",
        },
    }
