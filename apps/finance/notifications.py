from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.utils import timezone

from apps.finance.models import (
    Notification,
    NotificationChannel,
    NotificationDeliveryStatus,
    NotificationIconTone,
    NotificationSettings,
    NotificationType,
)


def get_or_create_notification_settings(*, user) -> NotificationSettings:
    settings, _ = NotificationSettings.objects.get_or_create(user=user)
    return settings


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
    normalized_delivery_steps = delivery_steps or [
        {
            "label": "Создано",
            "at": now.isoformat(),
        }
    ]

    return Notification.objects.create(
        user=user,
        title=title.strip(),
        body=body.strip(),
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
