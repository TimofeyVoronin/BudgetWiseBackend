from __future__ import annotations

from copy import deepcopy
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.finance.models import (
    BudgetNotificationChannel,
    BudgetNotificationDeliveryStatus,
    BudgetNotificationEventType,
    BudgetNotificationSettings,
    Goal,
    GoalStatus,
    default_budget_notification_anti_spam,
    default_budget_notification_channels,
    default_budget_notification_events,
    default_budget_notification_goals,
    default_budget_notification_thresholds,
)


BUDGET_NOTIFICATION_REPEAT_HOUR_OPTIONS = [1, 3, 6, 12, 24, 48, 72, 168]
BUDGET_NOTIFICATION_COOLDOWN_OPTIONS = [0, 5, 10, 15, 30, 60, 180, 360, 1440]
BUDGET_NOTIFICATION_LAG_DAY_OPTIONS = [1, 3, 7, 14, 30, 60, 90]


class BudgetNotificationCooldownError(ValidationError):
    status_code = 409
    default_code = "cooldown_active"
    default_detail = "После изменения настроек действует временная пауза."


def get_or_create_budget_notification_settings(*, user) -> BudgetNotificationSettings:
    settings, _ = BudgetNotificationSettings.objects.get_or_create(user=user)
    return settings


def get_budget_notifications_meta_payload(*, user) -> dict[str, Any]:
    goals = Goal.objects.filter(
        user=user,
        status__in=[GoalStatus.ACTIVE, GoalStatus.COMPLETED],
    ).order_by("status", "name", "id")

    return {
        "goals": [
            {
                "id": goal.id,
                "label": goal.name,
            }
            for goal in goals
        ],
        "repeatHourOptions": [
            {
                "title": _format_hours_option(value),
                "value": value,
            }
            for value in BUDGET_NOTIFICATION_REPEAT_HOUR_OPTIONS
        ],
        "cooldownOptions": [
            {
                "title": _format_minutes_option(value),
                "value": value,
            }
            for value in BUDGET_NOTIFICATION_COOLDOWN_OPTIONS
        ],
        "lagDayOptions": [
            {
                "title": _format_days_option(value),
                "value": value,
            }
            for value in BUDGET_NOTIFICATION_LAG_DAY_OPTIONS
        ],
        "milestonePercents": [25, 50, 75, 100],
    }


def build_budget_notification_preview(*, settings: BudgetNotificationSettings) -> dict[str, Any]:
    active_channels = [
        item["id"]
        for item in settings.channels
        if item.get("enabled")
    ]

    usage_percent = settings.preview_usage_percent
    event_title = "Бюджет близок к лимиту"
    event_subtitle = f"Текущее использование бюджета: {usage_percent}%"

    return {
        "eventTitle": event_title,
        "eventSubtitle": event_subtitle,
        "channels": [
            {
                "channel": channel_id,
                "title": event_title,
                "body": _build_preview_body(channel_id=channel_id, usage_percent=usage_percent),
            }
            for channel_id in active_channels
        ],
        "activeChannelIds": active_channels,
    }


def build_budget_notification_test_result(
    *,
    settings: BudgetNotificationSettings,
    channel_ids: list[str] | None,
    event_id: str | None,
) -> dict[str, Any]:
    if event_id and event_id not in BudgetNotificationEventType.values:
        raise ValidationError(
            {
                "eventId": [
                    "Недопустимый тип события уведомления."
                ]
            }
        )

    available_channels = {item["id"]: item for item in settings.channels}

    if channel_ids is None:
        channel_ids = [
            item["id"]
            for item in settings.channels
            if item.get("enabled")
        ]

    invalid_channel_ids = [
        channel_id
        for channel_id in channel_ids
        if channel_id not in BudgetNotificationChannel.values
    ]

    if invalid_channel_ids:
        raise ValidationError(
            {
                "channelIds": [
                    "Недопустимые каналы доставки: "
                    + ", ".join(invalid_channel_ids)
                    + "."
                ]
            }
        )

    channel_results = []
    delivered_count = 0

    for channel_id in channel_ids:
        channel = available_channels.get(channel_id)

        if not settings.enabled:
            channel_results.append(
                {
                    "id": channel_id,
                    "status": "skipped",
                    "error": "Уведомления отключены в настройках.",
                }
            )
            continue

        if channel and not channel.get("enabled"):
            channel_results.append(
                {
                    "id": channel_id,
                    "status": "skipped",
                    "error": "Канал отключён в настройках.",
                }
            )
            continue

        if channel_id == BudgetNotificationChannel.IN_APP.value:
            channel_results.append(
                {
                    "id": channel_id,
                    "status": "delivered",
                }
            )
            delivered_count += 1
            continue

        channel_results.append(
            {
                "id": channel_id,
                "status": "skipped",
                "error": "Канал доставки пока не настроен на backend.",
            }
        )

    return {
        "sent": delivered_count > 0,
        "channels": channel_results,
    }


def update_budget_notification_settings(
    *,
    settings: BudgetNotificationSettings,
    payload: dict[str, Any],
) -> BudgetNotificationSettings:
    if "enabled" in payload:
        settings.enabled = payload["enabled"]

    if "thresholdsEnabled" in payload:
        settings.thresholds_enabled = payload["thresholdsEnabled"]

    if "previewUsagePercent" in payload:
        settings.preview_usage_percent = payload["previewUsagePercent"]

    if "thresholds" in payload:
        settings.thresholds = merge_thresholds(
            current=settings.thresholds,
            updates=payload["thresholds"],
        )

    if "events" in payload:
        settings.events = merge_events(
            current=settings.events,
            updates=payload["events"],
        )

    if "channels" in payload:
        settings.channels = merge_channels(
            current=settings.channels,
            updates=payload["channels"],
        )

    if "antiSpam" in payload:
        settings.anti_spam = merge_anti_spam(
            current=settings.anti_spam,
            updates=payload["antiSpam"],
        )

    if "goals" in payload:
        settings.goals = merge_goals(
            current=settings.goals,
            updates=payload["goals"],
        )

    try:
        settings.full_clean()
        settings.save()
    except DjangoValidationError as exc:
        raise ValidationError(_django_validation_to_error_dict(exc)) from exc

    return settings


def validate_budget_notification_thresholds(
    *,
    user,
    thresholds: list[dict[str, Any]],
) -> dict[str, Any]:
    settings = get_or_create_budget_notification_settings(user=user)
    candidate = BudgetNotificationSettings(
        user=user,
        enabled=settings.enabled,
        thresholds_enabled=settings.thresholds_enabled,
        thresholds=merge_thresholds(current=settings.thresholds, updates=thresholds),
        events=settings.events,
        channels=settings.channels,
        anti_spam=settings.anti_spam,
        goals=settings.goals,
        preview_usage_percent=settings.preview_usage_percent,
    )

    try:
        candidate.full_clean()
    except DjangoValidationError as exc:
        return {
            "ok": False,
            "fieldErrors": _flatten_error_dict(_django_validation_to_error_dict(exc)),
            "generalMessage": "Проверьте пороги уведомлений.",
        }

    return {
        "ok": True,
        "fieldErrors": {},
        "generalMessage": None,
    }


def merge_thresholds(*, current: list[dict[str, Any]] | None, updates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    current_items = _items_by_id(current or default_budget_notification_thresholds())

    for update in updates:
        threshold_id = str(update.get("id", "")).strip()
        if not threshold_id:
            continue

        base = current_items.get(threshold_id, {"id": threshold_id})

        for field_name in ["percent", "active"]:
            if field_name in update:
                base[field_name] = update[field_name]

        current_items[threshold_id] = base

    return _ordered_items(current_items, default_budget_notification_thresholds())


def merge_events(*, current: list[dict[str, Any]] | None, updates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    current_items = _items_by_id(current or default_budget_notification_events())

    for update in updates:
        event_id = str(update.get("id", "")).strip()
        if not event_id:
            continue

        base = current_items.get(event_id, {"id": event_id})
        if "enabled" in update:
            base["enabled"] = update["enabled"]

        current_items[event_id] = base

    return _ordered_items(current_items, default_budget_notification_events())


def merge_channels(*, current: list[dict[str, Any]] | None, updates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    current_items = _items_by_id(current or default_budget_notification_channels())

    for update in updates:
        channel_id = str(update.get("id", "")).strip()
        if not channel_id:
            continue

        base = current_items.get(channel_id, {"id": channel_id})
        if "enabled" in update:
            base["enabled"] = update["enabled"]

        current_items[channel_id] = base

    return _ordered_items(current_items, default_budget_notification_channels())


def merge_anti_spam(*, current: dict[str, Any] | None, updates: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(current or default_budget_notification_anti_spam())
    merged.update(updates or {})
    return merged


def merge_goals(*, current: dict[str, Any] | None, updates: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(current or default_budget_notification_goals())
    merged.update(updates or {})
    return merged


def _items_by_id(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("id")): deepcopy(item)
        for item in items
        if item.get("id") is not None
    }


def _ordered_items(items_by_id: dict[str, dict[str, Any]], defaults: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = []
    used_ids = set()

    for default_item in defaults:
        item_id = str(default_item.get("id"))
        item = deepcopy(default_item)
        item.update(items_by_id.get(item_id, {}))
        ordered.append(item)
        used_ids.add(item_id)

    for item_id, item in items_by_id.items():
        if item_id not in used_ids:
            ordered.append(deepcopy(item))

    return ordered


def _django_validation_to_error_dict(exc: DjangoValidationError) -> dict[str, Any]:
    if hasattr(exc, "message_dict"):
        return {
            key: [str(message) for message in messages]
            if isinstance(messages, list)
            else [str(messages)]
            for key, messages in exc.message_dict.items()
        }

    return {
        "general": [str(message) for message in exc.messages]
    }




def _flatten_error_dict(errors: dict[str, Any]) -> dict[str, str]:
    result = {}

    for key, value in errors.items():
        if isinstance(value, list):
            result[key] = str(value[0]) if value else "Некорректное значение."
        else:
            result[key] = str(value)

    return result

def _format_hours_option(value: int) -> str:
    if value == 1:
        return "1 час"
    if value in {2, 3, 4}:
        return f"{value} часа"
    return f"{value} часов"


def _format_minutes_option(value: int) -> str:
    if value == 0:
        return "Без паузы"
    if value == 1:
        return "1 минута"
    if value in {2, 3, 4}:
        return f"{value} минуты"
    return f"{value} минут"


def _format_days_option(value: int) -> str:
    if value == 1:
        return "1 день"
    if value in {2, 3, 4}:
        return f"{value} дня"
    return f"{value} дней"


def _build_preview_body(*, channel_id: str, usage_percent: int) -> str:
    if channel_id == BudgetNotificationChannel.IN_APP.value:
        return f"Бюджет использован на {usage_percent}%. Проверьте расходы в приложении."

    if channel_id == BudgetNotificationChannel.EMAIL.value:
        return f"Ваш бюджет использован на {usage_percent}%. Email-доставка будет подключена позже."

    if channel_id == BudgetNotificationChannel.PUSH.value:
        return f"Бюджет использован на {usage_percent}%. Push-доставка будет подключена позже."

    return f"Бюджет использован на {usage_percent}%."
