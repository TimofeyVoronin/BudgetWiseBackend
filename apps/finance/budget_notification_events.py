from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from django.db import transaction as db_transaction
from django.utils import timezone

from apps.finance.budgets import get_budget_usage, get_period_label
from apps.finance.budget_notifications import get_or_create_budget_notification_settings
from apps.finance.models import (
    Budget,
    BudgetKind,
    BudgetNotificationEvent,
    BudgetNotificationEventStatus,
    BudgetNotificationEventType,
    BudgetNotificationSettings,
    Goal,
    GoalStatus,
    NotificationEntityKind,
    NotificationIconTone,
)

MONEY_QUANT = Decimal("0.01")
PERCENT_QUANT = Decimal("0.01")


@dataclass(frozen=True)
class BudgetNotificationCandidate:
    event_type: str
    related_object_type: str
    related_object_id: int
    threshold_id: str
    title: str
    message: str
    icon: str
    icon_tone: str
    payload: dict[str, Any]

    @property
    def deduplication_key(self) -> str:
        return ":".join(
            [
                self.event_type,
                self.related_object_type,
                str(self.related_object_id),
                self.threshold_id or "default",
            ]
        )


def generate_budget_notification_events(
    *,
    user,
    target_date: date | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Generate budget/goal notification events for a user.

    The service creates BudgetNotificationEvent rows only when ``dry_run`` is False.
    It does not send email, push, or in-app messages. Delivery through the
    Notification Center is handled by the next integration step.
    """
    target_date = target_date or timezone.localdate()
    settings = get_or_create_budget_notification_settings(user=user)

    processed_budgets = 0
    processed_goals = 0
    candidates: list[BudgetNotificationCandidate] = []

    if settings.enabled:
        budget_candidates, processed_budgets = _build_budget_event_candidates(
            user=user,
            settings=settings,
            target_date=target_date,
        )
        goal_candidates, processed_goals = _build_goal_event_candidates(
            user=user,
            settings=settings,
            target_date=target_date,
        )
        candidates.extend(budget_candidates)
        candidates.extend(goal_candidates)

    min_repeat_hours = int(settings.anti_spam.get("minRepeatHours", 24))
    repeat_since = timezone.now() - timedelta(hours=min_repeat_hours)

    items = []
    created_events = 0
    skipped_duplicates = 0

    with db_transaction.atomic():
        for candidate in candidates:
            is_duplicate = BudgetNotificationEvent.objects.filter(
                user=user,
                deduplication_key=candidate.deduplication_key,
                created_at__gte=repeat_since,
            ).exists()

            if is_duplicate:
                skipped_duplicates += 1
                continue

            event_id = None
            if not dry_run:
                event = BudgetNotificationEvent.objects.create(
                    user=user,
                    event_type=candidate.event_type,
                    related_object_type=candidate.related_object_type,
                    related_object_id=candidate.related_object_id,
                    threshold_id=candidate.threshold_id,
                    title=candidate.title,
                    message=candidate.message,
                    icon=candidate.icon,
                    icon_tone=candidate.icon_tone,
                    status=BudgetNotificationEventStatus.GENERATED,
                    deduplication_key=candidate.deduplication_key,
                    payload=candidate.payload,
                )
                event_id = event.id
                created_events += 1

            items.append(
                {
                    "id": event_id,
                    "eventType": candidate.event_type,
                    "relatedObjectType": candidate.related_object_type,
                    "relatedObjectId": candidate.related_object_id,
                    "thresholdId": candidate.threshold_id,
                    "title": candidate.title,
                    "message": candidate.message,
                    "icon": candidate.icon,
                    "iconTone": candidate.icon_tone,
                    "deduplicationKey": candidate.deduplication_key,
                    "payload": candidate.payload,
                }
            )

    return {
        "date": target_date.isoformat(),
        "dryRun": dry_run,
        "processedBudgets": processed_budgets,
        "processedGoals": processed_goals,
        "createdEvents": created_events,
        "wouldCreateEvents": len(items) if dry_run else 0,
        "skippedDuplicates": skipped_duplicates,
        "items": items,
    }


def _build_budget_event_candidates(*, user, settings: BudgetNotificationSettings, target_date: date) -> tuple[list[BudgetNotificationCandidate], int]:
    budgets = (
        Budget.objects
        .filter(
            user=user,
            kind=BudgetKind.EXPENSE,
            is_active=True,
            paused=False,
            period_start__lte=target_date,
            period_end__gte=target_date,
        )
        .select_related("category")
        .order_by("id")
    )

    enabled_events = _enabled_event_ids(settings)
    active_thresholds = _active_budget_thresholds(settings)
    candidates: list[BudgetNotificationCandidate] = []
    processed_count = 0

    for budget in budgets:
        processed_count += 1
        usage = get_budget_usage(budget)
        usage_percent = Decimal(str(usage.usage_percent))

        if (
            usage_percent > Decimal("100.00")
            and BudgetNotificationEventType.BUDGET_EXCEEDED.value in enabled_events
        ):
            candidates.append(_build_budget_exceeded_candidate(budget=budget, usage_percent=usage_percent))
            continue

        if not settings.thresholds_enabled:
            continue

        crossed_threshold = _highest_crossed_threshold(
            thresholds=active_thresholds,
            usage_percent=usage_percent,
        )
        if (
            crossed_threshold
            and BudgetNotificationEventType.BUDGET_NEAR_LIMIT.value in enabled_events
        ):
            candidates.append(
                _build_budget_near_limit_candidate(
                    budget=budget,
                    usage_percent=usage_percent,
                    threshold=crossed_threshold,
                )
            )
            continue

        if (
            BudgetNotificationEventType.BUDGET_BACK_TO_NORMAL.value in enabled_events
            and _has_recent_budget_risk_event(user=user, budget_id=budget.id)
            and not crossed_threshold
        ):
            candidates.append(_build_budget_back_to_normal_candidate(budget=budget, usage_percent=usage_percent))

    return candidates, processed_count


def _build_goal_event_candidates(*, user, settings: BudgetNotificationSettings, target_date: date) -> tuple[list[BudgetNotificationCandidate], int]:
    enabled_events = _enabled_event_ids(settings)
    goals_settings = settings.goals or {}
    selected_goal_ids = goals_settings.get("selectedGoalIds") or []

    goals = Goal.objects.filter(
        user=user,
        status__in=[GoalStatus.ACTIVE, GoalStatus.COMPLETED],
    ).order_by("id")

    if selected_goal_ids:
        goals = goals.filter(id__in=selected_goal_ids)

    milestone_percents = [
        int(value)
        for value in goals_settings.get("milestonePercents", [25, 50, 75, 100])
    ]
    milestone_enabled = goals_settings.get("milestoneEnabled", {})
    notify_on_lag = bool(goals_settings.get("notifyOnLag", False))
    lag_days = int(goals_settings.get("lagDays", 7))

    candidates: list[BudgetNotificationCandidate] = []
    processed_count = 0

    for goal in goals:
        processed_count += 1
        progress_percent = _goal_progress_percent(goal)

        if (
            progress_percent >= Decimal("100.00")
            or goal.status == GoalStatus.COMPLETED
        ) and BudgetNotificationEventType.GOAL_REACHED.value in enabled_events:
            candidates.append(_build_goal_reached_candidate(goal=goal, progress_percent=progress_percent))
            continue

        if BudgetNotificationEventType.GOAL_MILESTONE.value in enabled_events:
            crossed_milestone = _highest_crossed_goal_milestone(
                progress_percent=progress_percent,
                milestone_percents=milestone_percents,
                milestone_enabled=milestone_enabled,
            )
            if crossed_milestone:
                candidates.append(
                    _build_goal_milestone_candidate(
                        goal=goal,
                        progress_percent=progress_percent,
                        milestone_percent=crossed_milestone,
                    )
                )

        if (
            notify_on_lag
            and BudgetNotificationEventType.GOAL_LAGGING.value in enabled_events
            and _goal_is_lagging(goal=goal, target_date=target_date, lag_days=lag_days, progress_percent=progress_percent)
        ):
            candidates.append(_build_goal_lagging_candidate(goal=goal, progress_percent=progress_percent, lag_days=lag_days))

    return candidates, processed_count


def _enabled_event_ids(settings: BudgetNotificationSettings) -> set[str]:
    return {
        item.get("id")
        for item in settings.events
        if item.get("enabled")
    }


def _active_budget_thresholds(settings: BudgetNotificationSettings) -> list[dict[str, Any]]:
    return sorted(
        [
            item
            for item in settings.thresholds
            if item.get("active") and Decimal(str(item.get("percent", 0))) < Decimal("100")
        ],
        key=lambda item: Decimal(str(item.get("percent", 0))),
    )


def _highest_crossed_threshold(*, thresholds: list[dict[str, Any]], usage_percent: Decimal) -> dict[str, Any] | None:
    crossed = [
        threshold
        for threshold in thresholds
        if usage_percent >= Decimal(str(threshold.get("percent", 0)))
    ]
    if not crossed:
        return None
    return crossed[-1]


def _highest_crossed_goal_milestone(*, progress_percent: Decimal, milestone_percents: list[int], milestone_enabled: dict[str, bool]) -> int | None:
    crossed = []
    for percent in sorted(set(milestone_percents)):
        if percent >= 100:
            continue
        if not milestone_enabled.get(str(percent), True):
            continue
        if progress_percent >= Decimal(str(percent)):
            crossed.append(percent)

    return crossed[-1] if crossed else None


def _goal_progress_percent(goal: Goal) -> Decimal:
    if goal.target_amount <= 0:
        return Decimal("0.00")

    return min(
        goal.current_amount / goal.target_amount * Decimal("100"),
        Decimal("100.00"),
    ).quantize(PERCENT_QUANT, rounding=ROUND_HALF_UP)


def _goal_is_lagging(*, goal: Goal, target_date: date, lag_days: int, progress_percent: Decimal) -> bool:
    if goal.status != GoalStatus.ACTIVE or not goal.deadline:
        return False

    if progress_percent >= Decimal("100.00"):
        return False

    return target_date >= goal.deadline - timedelta(days=lag_days)


def _has_recent_budget_risk_event(*, user, budget_id: int) -> bool:
    return BudgetNotificationEvent.objects.filter(
        user=user,
        related_object_type=NotificationEntityKind.BUDGET,
        related_object_id=budget_id,
        event_type__in=[
            BudgetNotificationEventType.BUDGET_NEAR_LIMIT,
            BudgetNotificationEventType.BUDGET_EXCEEDED,
        ],
    ).exists()


def _build_budget_near_limit_candidate(*, budget: Budget, usage_percent: Decimal, threshold: dict[str, Any]) -> BudgetNotificationCandidate:
    percent = _percent_to_number(usage_percent)
    threshold_percent = int(threshold.get("percent", 0))
    category_name = budget.category.name
    period_label = get_period_label(budget)

    return BudgetNotificationCandidate(
        event_type=BudgetNotificationEventType.BUDGET_NEAR_LIMIT,
        related_object_type=NotificationEntityKind.BUDGET,
        related_object_id=budget.id,
        threshold_id=str(threshold.get("id") or f"threshold_{threshold_percent}"),
        title="Бюджет близок к лимиту",
        message=f"Бюджет «{category_name}» за период «{period_label}» использован на {percent}%.",
        icon="trending-up",
        icon_tone=NotificationIconTone.WARNING,
        payload={
            "budgetId": budget.id,
            "categoryName": category_name,
            "periodLabel": period_label,
            "usagePercent": percent,
            "thresholdPercent": threshold_percent,
            "limitAmount": str(budget.amount_limit.quantize(MONEY_QUANT)),
        },
    )


def _build_budget_exceeded_candidate(*, budget: Budget, usage_percent: Decimal) -> BudgetNotificationCandidate:
    percent = _percent_to_number(usage_percent)
    category_name = budget.category.name
    period_label = get_period_label(budget)

    return BudgetNotificationCandidate(
        event_type=BudgetNotificationEventType.BUDGET_EXCEEDED,
        related_object_type=NotificationEntityKind.BUDGET,
        related_object_id=budget.id,
        threshold_id="exceeded",
        title="Бюджет превышен",
        message=f"Бюджет «{category_name}» за период «{period_label}» превышен: {percent}% от лимита.",
        icon="alert-circle",
        icon_tone=NotificationIconTone.ERROR,
        payload={
            "budgetId": budget.id,
            "categoryName": category_name,
            "periodLabel": period_label,
            "usagePercent": percent,
            "limitAmount": str(budget.amount_limit.quantize(MONEY_QUANT)),
        },
    )


def _build_budget_back_to_normal_candidate(*, budget: Budget, usage_percent: Decimal) -> BudgetNotificationCandidate:
    percent = _percent_to_number(usage_percent)
    return BudgetNotificationCandidate(
        event_type=BudgetNotificationEventType.BUDGET_BACK_TO_NORMAL,
        related_object_type=NotificationEntityKind.BUDGET,
        related_object_id=budget.id,
        threshold_id="back_to_normal",
        title="Бюджет вернулся в норму",
        message=f"Бюджет «{budget.category.name}» снова в норме: {percent}% от лимита.",
        icon="check-circle",
        icon_tone=NotificationIconTone.SUCCESS,
        payload={
            "budgetId": budget.id,
            "categoryName": budget.category.name,
            "usagePercent": percent,
        },
    )


def _build_goal_milestone_candidate(*, goal: Goal, progress_percent: Decimal, milestone_percent: int) -> BudgetNotificationCandidate:
    return BudgetNotificationCandidate(
        event_type=BudgetNotificationEventType.GOAL_MILESTONE,
        related_object_type=NotificationEntityKind.GOAL,
        related_object_id=goal.id,
        threshold_id=f"milestone_{milestone_percent}",
        title="Цель достигла промежуточного рубежа",
        message=f"Цель «{goal.name}» достигла {milestone_percent}% выполнения.",
        icon="flag",
        icon_tone=NotificationIconTone.PRIMARY,
        payload={
            "goalId": goal.id,
            "goalName": goal.name,
            "progressPercent": _percent_to_number(progress_percent),
            "milestonePercent": milestone_percent,
            "currentAmount": str(goal.current_amount.quantize(MONEY_QUANT)),
            "targetAmount": str(goal.target_amount.quantize(MONEY_QUANT)),
        },
    )


def _build_goal_reached_candidate(*, goal: Goal, progress_percent: Decimal) -> BudgetNotificationCandidate:
    return BudgetNotificationCandidate(
        event_type=BudgetNotificationEventType.GOAL_REACHED,
        related_object_type=NotificationEntityKind.GOAL,
        related_object_id=goal.id,
        threshold_id="reached",
        title="Цель накопления достигнута",
        message=f"Цель «{goal.name}» выполнена.",
        icon="trophy",
        icon_tone=NotificationIconTone.SUCCESS,
        payload={
            "goalId": goal.id,
            "goalName": goal.name,
            "progressPercent": _percent_to_number(progress_percent),
            "currentAmount": str(goal.current_amount.quantize(MONEY_QUANT)),
            "targetAmount": str(goal.target_amount.quantize(MONEY_QUANT)),
        },
    )


def _build_goal_lagging_candidate(*, goal: Goal, progress_percent: Decimal, lag_days: int) -> BudgetNotificationCandidate:
    return BudgetNotificationCandidate(
        event_type=BudgetNotificationEventType.GOAL_LAGGING,
        related_object_type=NotificationEntityKind.GOAL,
        related_object_id=goal.id,
        threshold_id=f"lag_{lag_days}_days",
        title="Цель отстаёт от плана",
        message=f"Цель «{goal.name}» может не успеть к сроку. Текущий прогресс: {_percent_to_number(progress_percent)}%.",
        icon="trending-down",
        icon_tone=NotificationIconTone.ERROR,
        payload={
            "goalId": goal.id,
            "goalName": goal.name,
            "progressPercent": _percent_to_number(progress_percent),
            "lagDays": lag_days,
            "deadline": goal.deadline.isoformat() if goal.deadline else None,
        },
    )


def _percent_to_number(value: Decimal) -> float:
    return float(value.quantize(PERCENT_QUANT, rounding=ROUND_HALF_UP))
