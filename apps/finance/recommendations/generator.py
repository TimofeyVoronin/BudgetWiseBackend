from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Iterable, Mapping

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils import timezone

from apps.finance.health_check.constants import (
    RECOMMENDATION_BUDGET_OVER_LIMIT as HEALTH_RECOMMENDATION_BUDGET_OVER_LIMIT,
    RECOMMENDATION_CASH_GAP_RISK as HEALTH_RECOMMENDATION_CASH_GAP_RISK,
    RECOMMENDATION_HIGH_PLANNED_PAYMENTS_LOAD as HEALTH_RECOMMENDATION_HIGH_PLANNED_PAYMENTS_LOAD,
    RECOMMENDATION_LOW_SAVINGS_RATE as HEALTH_RECOMMENDATION_LOW_SAVINGS_RATE,
    RECOMMENDATION_NEGATIVE_NET_BALANCE as HEALTH_RECOMMENDATION_NEGATIVE_NET_BALANCE,
    RECOMMENDATION_UNSTABLE_EXPENSES as HEALTH_RECOMMENDATION_UNSTABLE_EXPENSES,
    RECOMMENDATION_WEAK_EMERGENCY_FUND as HEALTH_RECOMMENDATION_WEAK_EMERGENCY_FUND,
)
from apps.finance.health_check.scoring import build_financial_health_summary
from apps.finance.models import (
    FinancialRecommendation,
    FinancialRecommendationEvent,
    FinancialRecommendationEventType,
    FinancialRecommendationPriority,
    FinancialRecommendationSource,
    FinancialRecommendationStatus,
    FinancialRecommendationType,
)
from apps.finance.recommendations.constants import (
    RECOMMENDATION_CODE_CHECK_BUDGET_OVERRUN,
    RECOMMENDATION_CODE_COMPLETE_ONBOARDING,
    RECOMMENDATION_CODE_CREATE_BUDGET,
    RECOMMENDATION_CODE_CREATE_EMERGENCY_FUND_GOAL,
    RECOMMENDATION_CODE_FIX_CASH_GAP_RISK,
    RECOMMENDATION_CODE_INCREASE_SAVINGS_RATE,
    RECOMMENDATION_CODE_REDUCE_UNSTABLE_EXPENSES,
    RECOMMENDATION_CODE_REVIEW_PLANNED_PAYMENTS,
    RECOMMENDATION_DEFAULT_TTL_DAYS,
    RECOMMENDATION_MAX_ACTIVE_PER_USER,
    RECOMMENDATION_PRIORITY_HIGH,
    RECOMMENDATION_PRIORITY_LOW,
    RECOMMENDATION_PRIORITY_MEDIUM,
)
from apps.users.models import OnboardingSurveyStatus

VISIBLE_STATUSES = [
    FinancialRecommendationStatus.NEW,
    FinancialRecommendationStatus.ACTIVE,
    FinancialRecommendationStatus.SNOOZED,
]
TERMINAL_USER_STATUSES = [
    FinancialRecommendationStatus.ACCEPTED,
    FinancialRecommendationStatus.HIDDEN,
]

HEALTH_RECOMMENDATION_MAPPING = {
    HEALTH_RECOMMENDATION_LOW_SAVINGS_RATE: {
        "code": RECOMMENDATION_CODE_INCREASE_SAVINGS_RATE,
        "type": FinancialRecommendationType.SAVING,
        "source": FinancialRecommendationSource.FINANCIAL_HEALTH,
        "source_key": "financial-health:savings-rate",
    },
    HEALTH_RECOMMENDATION_NEGATIVE_NET_BALANCE: {
        "code": RECOMMENDATION_CODE_INCREASE_SAVINGS_RATE,
        "type": FinancialRecommendationType.CASHFLOW,
        "source": FinancialRecommendationSource.FINANCIAL_HEALTH,
        "source_key": "financial-health:negative-net-balance",
    },
    HEALTH_RECOMMENDATION_BUDGET_OVER_LIMIT: {
        "code": RECOMMENDATION_CODE_CHECK_BUDGET_OVERRUN,
        "type": FinancialRecommendationType.BUDGET,
        "source": FinancialRecommendationSource.FINANCIAL_HEALTH,
        "source_key": "financial-health:budget-usage",
    },
    HEALTH_RECOMMENDATION_WEAK_EMERGENCY_FUND: {
        "code": RECOMMENDATION_CODE_CREATE_EMERGENCY_FUND_GOAL,
        "type": FinancialRecommendationType.GOAL,
        "source": FinancialRecommendationSource.FINANCIAL_HEALTH,
        "source_key": "financial-health:emergency-fund",
    },
    HEALTH_RECOMMENDATION_CASH_GAP_RISK: {
        "code": RECOMMENDATION_CODE_FIX_CASH_GAP_RISK,
        "type": FinancialRecommendationType.CASHFLOW,
        "source": FinancialRecommendationSource.FINANCIAL_HEALTH,
        "source_key": "financial-health:cash-gap-risk",
    },
    HEALTH_RECOMMENDATION_HIGH_PLANNED_PAYMENTS_LOAD: {
        "code": RECOMMENDATION_CODE_REVIEW_PLANNED_PAYMENTS,
        "type": FinancialRecommendationType.PLANNED_PAYMENT,
        "source": FinancialRecommendationSource.FINANCIAL_HEALTH,
        "source_key": "financial-health:planned-payments-load",
    },
    HEALTH_RECOMMENDATION_UNSTABLE_EXPENSES: {
        "code": RECOMMENDATION_CODE_REDUCE_UNSTABLE_EXPENSES,
        "type": FinancialRecommendationType.EXPENSE_STABILITY,
        "source": FinancialRecommendationSource.FINANCIAL_HEALTH,
        "source_key": "financial-health:expense-stability",
    },
}


@dataclass(frozen=True)
class RecommendationDraft:
    code: str
    type: str
    priority: str
    title: str
    text: str
    action: str
    reason: str
    source: str
    source_key: str
    context: dict[str, Any]
    expires_at: Any = None


@dataclass(frozen=True)
class RecommendationGenerationResult:
    created: int
    updated: int
    skipped: int
    total: int
    recommendations: list[FinancialRecommendation]

    def as_payload(self) -> dict[str, Any]:
        return {
            "created": self.created,
            "updated": self.updated,
            "skipped": self.skipped,
            "total": self.total,
            "recommendationIds": [item.id for item in self.recommendations],
        }


def generate_financial_recommendations(
    *,
    user,
    period: str | None = None,
    date_from=None,
    date_to=None,
    currency: str | None = None,
    max_items: int = RECOMMENDATION_MAX_ACTIVE_PER_USER,
) -> RecommendationGenerationResult:
    """Create or update rule-based financial recommendations for a user.

    The generator reads existing user data and Financial Health Check metrics,
    but does not modify financial entities such as accounts, transactions,
    budgets, goals, or planned operations. Only recommendation records and
    recommendation events are created or updated.
    """

    summary = build_financial_health_summary(
        user=user,
        period=period,
        date_from=date_from,
        date_to=date_to,
        currency=currency,
    )
    drafts = build_recommendation_drafts_from_summary(user=user, summary=summary)
    if max_items > 0:
        drafts = drafts[:max_items]

    created = 0
    updated = 0
    skipped = 0
    saved_recommendations: list[FinancialRecommendation] = []

    with transaction.atomic():
        for draft in drafts:
            recommendation, action = upsert_recommendation_from_draft(user=user, draft=draft)
            if action == "created":
                created += 1
            elif action == "updated":
                updated += 1
            else:
                skipped += 1
            if recommendation is not None:
                saved_recommendations.append(recommendation)

    return RecommendationGenerationResult(
        created=created,
        updated=updated,
        skipped=skipped,
        total=len(saved_recommendations),
        recommendations=saved_recommendations,
    )


def build_recommendation_drafts_from_summary(*, user, summary: Mapping[str, Any]) -> list[RecommendationDraft]:
    drafts: list[RecommendationDraft] = []
    recommendations = summary.get("recommendations") or []

    for recommendation in recommendations:
        if isinstance(recommendation, Mapping):
            draft = _build_draft_from_health_recommendation(recommendation)
            if draft is not None:
                drafts.append(draft)

    drafts.extend(_build_data_quality_drafts(summary))
    onboarding_draft = _build_onboarding_draft(user=user)
    if onboarding_draft is not None:
        drafts.append(onboarding_draft)

    return _deduplicate_drafts(drafts)


def upsert_recommendation_from_draft(
    *,
    user,
    draft: RecommendationDraft,
) -> tuple[FinancialRecommendation | None, str]:
    active = (
        FinancialRecommendation.objects.select_for_update()
        .filter(
            user=user,
            code=draft.code,
            source=draft.source,
            source_key=draft.source_key,
            status__in=VISIBLE_STATUSES,
        )
        .order_by("id")
        .first()
    )
    if active is not None:
        _apply_draft(active, draft)
        if active.status in {FinancialRecommendationStatus.NEW, FinancialRecommendationStatus.ACTIVE}:
            active.status = FinancialRecommendationStatus.ACTIVE
        active.full_clean()
        active.save()
        _create_event(active, FinancialRecommendationEventType.REFRESHED, {"source": "generator"})
        return active, "updated"

    terminal_exists = FinancialRecommendation.objects.filter(
        user=user,
        code=draft.code,
        source=draft.source,
        source_key=draft.source_key,
        status__in=TERMINAL_USER_STATUSES,
    ).exists()
    if terminal_exists:
        return None, "skipped"

    recommendation = FinancialRecommendation(
        user=user,
        status=FinancialRecommendationStatus.ACTIVE,
    )
    _apply_draft(recommendation, draft)
    recommendation.full_clean()
    recommendation.save()
    _create_event(recommendation, FinancialRecommendationEventType.CREATED, {"source": "generator"})
    return recommendation, "created"


def _build_draft_from_health_recommendation(
    recommendation: Mapping[str, Any],
) -> RecommendationDraft | None:
    source_code = str(recommendation.get("code") or "")
    mapping = HEALTH_RECOMMENDATION_MAPPING.get(source_code)
    if mapping is None:
        return None

    metric_id = str(recommendation.get("metricId") or "")
    priority = _normalize_priority(str(recommendation.get("priority") or ""))
    return RecommendationDraft(
        code=mapping["code"],
        type=mapping["type"],
        priority=priority,
        title=str(recommendation.get("title") or mapping["code"]),
        text=str(recommendation.get("text") or ""),
        action=str(recommendation.get("action") or ""),
        reason=str(recommendation.get("reason") or ""),
        source=mapping["source"],
        source_key=mapping["source_key"],
        context={
            "sourceRecommendationCode": source_code,
            "metricId": metric_id,
            "source": "financial_health_check",
        },
        expires_at=timezone.now() + timedelta(days=RECOMMENDATION_DEFAULT_TTL_DAYS),
    )


def _build_data_quality_drafts(summary: Mapping[str, Any]) -> list[RecommendationDraft]:
    data_quality = summary.get("dataQuality")
    if not isinstance(data_quality, Mapping):
        return []

    drafts = []
    if int(data_quality.get("budgetCount") or 0) == 0:
        drafts.append(
            RecommendationDraft(
                code=RECOMMENDATION_CODE_CREATE_BUDGET,
                type=FinancialRecommendationType.BUDGET,
                priority=RECOMMENDATION_PRIORITY_MEDIUM,
                title="Создайте первый бюджет",
                text="У вас пока нет активных бюджетов для контроля расходов.",
                action="Создайте бюджет для основной категории расходов.",
                reason="dataQuality.budgetCount=0",
                source=FinancialRecommendationSource.BUDGETS,
                source_key="missing-active-budget",
                context={"source": "financial_health_data_quality"},
                expires_at=timezone.now() + timedelta(days=RECOMMENDATION_DEFAULT_TTL_DAYS),
            )
        )

    if int(data_quality.get("goalCount") or 0) == 0:
        drafts.append(
            RecommendationDraft(
                code=RECOMMENDATION_CODE_CREATE_EMERGENCY_FUND_GOAL,
                type=FinancialRecommendationType.GOAL,
                priority=RECOMMENDATION_PRIORITY_HIGH,
                title="Создайте цель для финансовой подушки",
                text="У вас пока нет активной цели накоплений для резервного фонда.",
                action="Создайте цель накоплений и регулярно пополняйте её.",
                reason="dataQuality.goalCount=0",
                source=FinancialRecommendationSource.GOALS,
                source_key="missing-emergency-fund-goal",
                context={"source": "financial_health_data_quality"},
                expires_at=timezone.now() + timedelta(days=RECOMMENDATION_DEFAULT_TTL_DAYS),
            )
        )

    return drafts


def _build_onboarding_draft(*, user) -> RecommendationDraft | None:
    try:
        survey = user.onboarding_survey
    except ObjectDoesNotExist:
        survey = None

    if survey is not None and survey.status == OnboardingSurveyStatus.COMPLETED:
        return None

    return RecommendationDraft(
        code=RECOMMENDATION_CODE_COMPLETE_ONBOARDING,
        type=FinancialRecommendationType.ONBOARDING,
        priority=RECOMMENDATION_PRIORITY_LOW,
        title="Завершите первичную настройку",
        text="Ответы onboarding помогут точнее подобрать категории, цели и рекомендации.",
        action="Пройдите короткую анкету первичной настройки.",
        reason="onboarding.status!=completed",
        source=FinancialRecommendationSource.ONBOARDING,
        source_key="onboarding-not-completed",
        context={"source": "onboarding"},
        expires_at=timezone.now() + timedelta(days=RECOMMENDATION_DEFAULT_TTL_DAYS),
    )


def _apply_draft(recommendation: FinancialRecommendation, draft: RecommendationDraft) -> None:
    recommendation.code = draft.code
    recommendation.type = draft.type
    recommendation.priority = draft.priority
    recommendation.title = draft.title
    recommendation.text = draft.text
    recommendation.action = draft.action
    recommendation.reason = draft.reason
    recommendation.source = draft.source
    recommendation.source_key = draft.source_key
    recommendation.context = draft.context
    recommendation.expires_at = draft.expires_at


def _create_event(
    recommendation: FinancialRecommendation,
    event_type: str,
    metadata: Mapping[str, Any] | None = None,
) -> FinancialRecommendationEvent:
    event = FinancialRecommendationEvent(
        recommendation=recommendation,
        user=recommendation.user,
        event_type=event_type,
        metadata=dict(metadata or {}),
    )
    event.full_clean()
    event.save()
    return event


def _deduplicate_drafts(drafts: Iterable[RecommendationDraft]) -> list[RecommendationDraft]:
    unique: dict[str, RecommendationDraft] = {}
    for draft in drafts:
        existing = unique.get(draft.code)
        if existing is None or _priority_rank(draft.priority) < _priority_rank(existing.priority):
            unique[draft.code] = draft
    return sorted(
        unique.values(),
        key=lambda item: (_priority_rank(item.priority), item.code, item.source_key),
    )


def _normalize_priority(priority: str) -> str:
    if priority in {
        RECOMMENDATION_PRIORITY_HIGH,
        RECOMMENDATION_PRIORITY_MEDIUM,
        RECOMMENDATION_PRIORITY_LOW,
    }:
        return priority
    return RECOMMENDATION_PRIORITY_MEDIUM


def _priority_rank(priority: str) -> int:
    if priority == RECOMMENDATION_PRIORITY_HIGH:
        return 0
    if priority == RECOMMENDATION_PRIORITY_MEDIUM:
        return 1
    return 2
