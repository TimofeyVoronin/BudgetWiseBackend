from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.finance.models import (
    Notification,
    NotificationChannel,
    NotificationDeliveryStatus,
    NotificationEntityKind,
    NotificationIconTone,
    NotificationSettings,
    NotificationType,
)


def get_or_create_notification_settings(*, user) -> NotificationSettings:
    settings, _ = NotificationSettings.objects.get_or_create(user=user)
    return settings


def _normalize_string(
    value: str | None,
    *,
    field_name: str,
    required: bool = False,
    max_length: int | None = None,
) -> str:
    if value is None:
        value = ""

    if not isinstance(value, str):
        raise ValidationError(
            {
                field_name: [
                    "Значение должно быть строкой."
                ]
            }
        )

    normalized_value = value.strip()

    if required and not normalized_value:
        raise ValidationError(
            {
                field_name: [
                    "Поле обязательно для заполнения."
                ]
            }
        )

    if max_length is not None and len(normalized_value) > max_length:
        raise ValidationError(
            {
                field_name: [
                    f"Поле не может быть длиннее {max_length} символов."
                ]
            }
        )

    return normalized_value


def _validate_choice(value: str, *, field_name: str, allowed_values: list[str]) -> str:
    if value not in allowed_values:
        raise ValidationError(
            {
                field_name: [
                    (
                        "Недопустимое значение. Допустимые значения: "
                        f"{', '.join(allowed_values)}."
                    )
                ]
            }
        )

    return value


def _validate_delivery_steps(value: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    if value is None:
        return None

    if not isinstance(value, list):
        raise ValidationError(
            {
                "delivery_steps": [
                    "Шаги доставки должны быть списком."
                ]
            }
        )

    normalized_steps = []

    for index, step in enumerate(value, start=1):
        if not isinstance(step, dict):
            raise ValidationError(
                {
                    "delivery_steps": [
                        f"Шаг доставки #{index} должен быть объектом."
                    ]
                }
            )

        label = _normalize_string(
            step.get("label"),
            field_name="delivery_steps.label",
            required=True,
            max_length=100,
        )
        at_value = step.get("at")

        if not at_value:
            raise ValidationError(
                {
                    "delivery_steps.at": [
                        f"Укажите дату и время для шага доставки #{index}."
                    ]
                }
            )

        normalized_steps.append(
            {
                "label": label,
                "at": str(at_value),
            }
        )

    return normalized_steps


def create_notification(
    *,
    user,
    title: str,
    body: str = "",
    type: str = NotificationType.SYSTEM,
    channel: str = NotificationChannel.IN_APP,
    icon: str = "bell",
    icon_tone: str = NotificationIconTone.PRIMARY,
    entity_kind: str = "",
    entity_id: int | None = None,
    entity_route_name: str = "",
    entity_label: str = "",
    entity_tag: str = "",
    amount: Decimal | None = None,
    account_name: str = "",
    category_name: str = "",
    related_goal_name: str = "",
    related_goal_percent: Decimal | None = None,
    delivery_steps: list[dict[str, Any]] | None = None,
) -> Notification:
    """Create a notification with user notification settings applied.

    The function does not send email, push or SMS messages. It creates an
    application-level notification record and sets delivery_status according
    to the user's enabled channels, enabled notification types and quiet hours.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        raise ValidationError(
            {
                "user": [
                    "Для создания уведомления нужен авторизованный пользователь."
                ]
            }
        )

    title = _normalize_string(
        title,
        field_name="title",
        required=True,
        max_length=200,
    )
    body = _normalize_string(
        body,
        field_name="body",
        max_length=2000,
    )
    type = _validate_choice(
        type,
        field_name="type",
        allowed_values=NotificationType.values,
    )
    channel = _validate_choice(
        channel,
        field_name="channel",
        allowed_values=NotificationChannel.values,
    )
    icon = _normalize_string(
        icon,
        field_name="icon",
        required=True,
        max_length=50,
    )
    icon_tone = _validate_choice(
        icon_tone,
        field_name="icon_tone",
        allowed_values=NotificationIconTone.values,
    )

    if entity_kind:
        entity_kind = _validate_choice(
            entity_kind,
            field_name="entity_kind",
            allowed_values=NotificationEntityKind.values,
        )

    if entity_id is not None and entity_id <= 0:
        raise ValidationError(
            {
                "entity_id": [
                    "ID связанной сущности должен быть положительным числом."
                ]
            }
        )

    if amount is not None and amount < Decimal("0.00"):
        raise ValidationError(
            {
                "amount": [
                    "Сумма уведомления не может быть отрицательной."
                ]
            }
        )

    if related_goal_percent is not None and (
        related_goal_percent < Decimal("0.00")
        or related_goal_percent > Decimal("100.00")
    ):
        raise ValidationError(
            {
                "related_goal_percent": [
                    "Процент цели должен быть в диапазоне от 0 до 100."
                ]
            }
        )

    entity_route_name = _normalize_string(
        entity_route_name,
        field_name="entity_route_name",
        max_length=100,
    )
    entity_label = _normalize_string(
        entity_label,
        field_name="entity_label",
        max_length=150,
    )
    entity_tag = _normalize_string(
        entity_tag,
        field_name="entity_tag",
        max_length=150,
    )
    account_name = _normalize_string(
        account_name,
        field_name="account_name",
        max_length=100,
    )
    category_name = _normalize_string(
        category_name,
        field_name="category_name",
        max_length=100,
    )
    related_goal_name = _normalize_string(
        related_goal_name,
        field_name="related_goal_name",
        max_length=150,
    )

    notification_settings = get_or_create_notification_settings(user=user)

    delivery_status = NotificationDeliveryStatus.DELIVERED
    delivery_error = ""

    if not notification_settings.is_channel_enabled(channel):
        delivery_status = NotificationDeliveryStatus.UNAVAILABLE
        delivery_error = "Канал уведомлений отключён в настройках пользователя."

    elif not notification_settings.is_type_enabled(type):
        delivery_status = NotificationDeliveryStatus.UNAVAILABLE
        delivery_error = "Тип уведомлений отключён в настройках пользователя."

    elif notification_settings.is_quiet_time():
        delivery_status = NotificationDeliveryStatus.PENDING
        delivery_error = "Доставка отложена из-за тихих часов."

    now = timezone.now()
    normalized_delivery_steps = _validate_delivery_steps(delivery_steps)

    if normalized_delivery_steps is None:
        normalized_delivery_steps = [
            {
                "label": "Создано",
                "at": now.isoformat(),
            }
        ]

    return Notification.objects.create(
        user=user,
        title=title,
        body=body,
        type=type,
        channel=channel,
        delivery_status=delivery_status,
        delivery_error=delivery_error,
        icon=icon,
        icon_tone=icon_tone,
        entity_kind=entity_kind,
        entity_id=entity_id,
        entity_route_name=entity_route_name,
        entity_label=entity_label,
        entity_tag=entity_tag,
        amount=amount,
        account_name=account_name,
        category_name=category_name,
        related_goal_name=related_goal_name,
        related_goal_percent=related_goal_percent,
        delivery_steps=normalized_delivery_steps,
    )
