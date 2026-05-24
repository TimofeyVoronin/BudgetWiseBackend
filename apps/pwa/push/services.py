from __future__ import annotations

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.pwa.models import PwaPushProvider, PwaPushSubscription


DEFAULT_MAX_SUBSCRIPTIONS_PER_USER = 10


def get_max_subscriptions_per_user() -> int:
    return int(
        getattr(
            settings,
            "PWA_MAX_PUSH_SUBSCRIPTIONS_PER_USER",
            DEFAULT_MAX_SUBSCRIPTIONS_PER_USER,
        )
    )


def register_push_subscription(*, user, data: dict) -> PwaPushSubscription:
    endpoint = data["endpoint"].strip()
    device_id = data["deviceId"].strip()
    is_active = bool(data.get("isActive", True))

    with transaction.atomic():
        existing = (
            PwaPushSubscription.objects.select_for_update()
            .filter(user=user, endpoint=endpoint)
            .first()
        )

        if existing is None:
            active_count = PwaPushSubscription.objects.filter(
                user=user,
                is_active=True,
            ).count()
            max_count = get_max_subscriptions_per_user()

            if is_active and active_count >= max_count:
                raise ValidationError(
                    {
                        "general": [
                            (
                                "Достигнут лимит активных push-подписок "
                                f"для пользователя: {max_count}."
                            )
                        ]
                    }
                )

            subscription = PwaPushSubscription(user=user, endpoint=endpoint)
        else:
            subscription = existing

        subscription.device_id = device_id
        subscription.provider = PwaPushProvider.WEB_PUSH
        subscription.p256dh = data["p256dh"].strip()
        subscription.auth = data["auth"].strip()
        subscription.browser = data.get("browser", "").strip()
        subscription.platform = data.get("platform", "").strip()
        subscription.user_agent = data.get("userAgent", "").strip()
        subscription.is_active = is_active
        subscription.last_used_at = timezone.now()
        subscription.save()

    return subscription


def list_push_subscriptions(*, user):
    return PwaPushSubscription.objects.filter(user=user).order_by(
        "-is_active",
        "-updated_at",
        "-id",
    )


def get_user_push_subscription(*, user, subscription_id: int) -> PwaPushSubscription:
    try:
        return PwaPushSubscription.objects.get(user=user, pk=subscription_id)
    except PwaPushSubscription.DoesNotExist as exc:
        raise ValidationError(
            {
                "id": ["Push-подписка не найдена."]
            }
        ) from exc


def revoke_push_subscription(*, user, subscription_id: int) -> PwaPushSubscription:
    subscription = get_user_push_subscription(
        user=user,
        subscription_id=subscription_id,
    )

    subscription.is_active = False
    subscription.revoked_at = timezone.now()
    subscription.save(update_fields=["is_active", "revoked_at", "updated_at"])
    return subscription


def build_push_test_result(*, subscription: PwaPushSubscription) -> dict:
    send_enabled = bool(getattr(settings, "PWA_PUSH_SEND_ENABLED", False))

    if not send_enabled:
        return {
            "sent": False,
            "provider": subscription.provider,
            "code": "push_provider_disabled",
            "message": "Push-провайдер пока не подключён. Подписка сохранена, но отправка будет добавлена в следующей подзадаче.",
        }

    return {
        "sent": False,
        "provider": subscription.provider,
        "code": "push_provider_not_implemented",
        "message": "Отправка push-уведомлений будет реализована через Web Push provider.",
    }


def build_pwa_meta() -> dict:
    return {
        "pushSubscriptionsEnabled": bool(getattr(settings, "PWA_PUSH_SUBSCRIPTIONS_ENABLED", True)),
        "pushDeliveryEnabled": bool(getattr(settings, "PWA_PUSH_SEND_ENABLED", False)),
        "backgroundSyncEnabled": bool(getattr(settings, "PWA_BACKGROUND_SYNC_ENABLED", True)),
        "supportedPushProvider": getattr(settings, "PWA_PUSH_PROVIDER", PwaPushProvider.WEB_PUSH),
        "vapidPublicKey": getattr(settings, "PWA_VAPID_PUBLIC_KEY", ""),
        "maxSubscriptionsPerUser": get_max_subscriptions_per_user(),
        "supportedEvents": [
            "budget_limit_warning",
            "planned_transaction_due",
            "receipt_imported",
            "sync_conflict",
            "sync_failed",
        ],
        "endpoints": {
            "pushSubscriptions": "/api/v1/pwa/push-subscriptions/",
            "notificationSettings": "/api/v1/pwa/notification-settings/",
            "backgroundSyncMeta": "/api/v1/pwa/background-sync/meta/",
        },
    }
