from __future__ import annotations

import json
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.pwa.models import PwaPushProvider, PwaPushSubscription

try:  # pragma: no cover - covered through mocked provider in tests.
    from pywebpush import webpush
except ImportError:  # pragma: no cover - dependency may be absent in local dev before pip install.
    webpush = None


DEFAULT_MAX_SUBSCRIPTIONS_PER_USER = 10
DEFAULT_PUSH_TTL_SECONDS = 60


def get_max_subscriptions_per_user() -> int:
    return int(
        getattr(
            settings,
            "PWA_MAX_PUSH_SUBSCRIPTIONS_PER_USER",
            DEFAULT_MAX_SUBSCRIPTIONS_PER_USER,
        )
    )


def get_push_ttl_seconds() -> int:
    return int(getattr(settings, "PWA_PUSH_TTL_SECONDS", DEFAULT_PUSH_TTL_SECONDS))


def register_push_subscription(*, user, data: dict) -> PwaPushSubscription:
    if not bool(getattr(settings, "PWA_PUSH_SUBSCRIPTIONS_ENABLED", True)):
        raise ValidationError({"general": ["Регистрация push-подписок отключена."]})

    endpoint = data["endpoint"].strip()
    device_id = data["deviceId"].strip()
    is_active = bool(data.get("isActive", True))
    provider = data.get("provider") or PwaPushProvider.WEB_PUSH

    with transaction.atomic():
        existing = (
            PwaPushSubscription.objects.select_for_update()
            .filter(user=user, endpoint=endpoint)
            .first()
        )

        if existing is None:
            _validate_active_subscription_limit(user=user, is_active=is_active)
            subscription = PwaPushSubscription(user=user, endpoint=endpoint)
        else:
            if is_active and not existing.is_active:
                _validate_active_subscription_limit(user=user, is_active=True)
            subscription = existing

        subscription.device_id = device_id
        subscription.provider = provider
        subscription.p256dh = data["p256dh"].strip()
        subscription.auth = data["auth"].strip()
        subscription.browser = data.get("browser", "").strip()
        subscription.platform = data.get("platform", "").strip()
        subscription.user_agent = data.get("userAgent", "").strip()
        subscription.is_active = is_active
        subscription.last_used_at = timezone.now()
        subscription.save()

    return subscription


def _validate_active_subscription_limit(*, user, is_active: bool) -> None:
    if not is_active:
        return

    active_count = PwaPushSubscription.objects.filter(
        user=user,
        is_active=True,
    ).count()
    max_count = get_max_subscriptions_per_user()

    if active_count >= max_count:
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
        raise NotFound("Push-подписка не найдена.") from exc


def revoke_push_subscription(*, user, subscription_id: int) -> PwaPushSubscription:
    subscription = get_user_push_subscription(
        user=user,
        subscription_id=subscription_id,
    )

    deactivate_push_subscription(subscription=subscription)
    return subscription


def deactivate_push_subscription(*, subscription: PwaPushSubscription) -> None:
    subscription.is_active = False
    subscription.revoked_at = timezone.now()
    subscription.save(update_fields=["is_active", "revoked_at", "updated_at"])


def build_push_test_result(*, subscription: PwaPushSubscription) -> dict:
    payload = build_test_push_payload(subscription=subscription)
    return send_push_notification(subscription=subscription, payload=payload)


def build_test_push_payload(*, subscription: PwaPushSubscription) -> dict:
    return {
        "type": "test",
        "title": "BudgetWise",
        "body": "Тестовое push-уведомление отправлено успешно.",
        "data": {
            "subscriptionId": str(subscription.pk),
            "deviceId": subscription.device_id,
        },
    }


def send_push_notification(*, subscription: PwaPushSubscription, payload: dict[str, Any]) -> dict:
    if not subscription.is_active:
        return {
            "sent": False,
            "provider": subscription.provider,
            "code": "push_subscription_inactive",
            "message": "Push-подписка отключена.",
        }

    send_enabled = bool(getattr(settings, "PWA_PUSH_SEND_ENABLED", False))

    if not send_enabled:
        return {
            "sent": False,
            "provider": subscription.provider,
            "code": "push_provider_disabled",
            "message": "Push-провайдер отключён. Подписка сохранена, но отправка не выполняется.",
        }

    if subscription.provider != PwaPushProvider.WEB_PUSH:
        return {
            "sent": False,
            "provider": subscription.provider,
            "code": "push_provider_unsupported",
            "message": "Для подписки указан неподдерживаемый push-провайдер.",
        }

    return send_web_push_notification(subscription=subscription, payload=payload)


def send_web_push_notification(*, subscription: PwaPushSubscription, payload: dict[str, Any]) -> dict:
    vapid_private_key = str(getattr(settings, "PWA_VAPID_PRIVATE_KEY", "") or "").strip()
    vapid_subject = str(getattr(settings, "PWA_VAPID_SUBJECT", "") or "").strip()

    if not vapid_private_key or not vapid_subject:
        return {
            "sent": False,
            "provider": subscription.provider,
            "code": "push_provider_not_configured",
            "message": "Web Push provider не настроен: отсутствует VAPID private key или subject.",
        }

    if webpush is None:
        return {
            "sent": False,
            "provider": subscription.provider,
            "code": "push_provider_dependency_missing",
            "message": "Зависимость pywebpush не установлена в backend-окружении.",
        }

    subscription_info = build_web_push_subscription_info(subscription=subscription)
    serialized_payload = json.dumps(payload, ensure_ascii=False)

    try:
        webpush(
            subscription_info=subscription_info,
            data=serialized_payload,
            vapid_private_key=vapid_private_key,
            vapid_claims={"sub": vapid_subject},
            ttl=get_push_ttl_seconds(),
        )
    except Exception as exc:  # noqa: BLE001 - provider errors should be converted to API-safe response.
        return build_web_push_error_result(subscription=subscription, exc=exc)

    subscription.last_used_at = timezone.now()
    subscription.save(update_fields=["last_used_at", "updated_at"])

    return {
        "sent": True,
        "provider": subscription.provider,
        "code": "push_sent",
        "message": "Тестовое push-уведомление отправлено.",
    }


def build_web_push_subscription_info(*, subscription: PwaPushSubscription) -> dict:
    return {
        "endpoint": subscription.endpoint,
        "keys": {
            "p256dh": subscription.p256dh,
            "auth": subscription.auth,
        },
    }


def build_web_push_error_result(*, subscription: PwaPushSubscription, exc: Exception) -> dict:
    status_code = extract_push_response_status_code(exc)

    if status_code in {404, 410}:
        deactivate_push_subscription(subscription=subscription)
        return {
            "sent": False,
            "provider": subscription.provider,
            "code": "push_subscription_gone",
            "message": "Push-подписка больше недействительна и была отключена.",
            "statusCode": status_code,
        }

    if status_code in {401, 403}:
        return {
            "sent": False,
            "provider": subscription.provider,
            "code": "push_provider_auth_failed",
            "message": "Push-сервис отклонил запрос авторизации. Проверьте VAPID-ключи.",
            "statusCode": status_code,
        }

    return {
        "sent": False,
        "provider": subscription.provider,
        "code": "push_provider_error",
        "message": "Не удалось отправить push-уведомление через Web Push provider.",
        "statusCode": status_code,
    }


def extract_push_response_status_code(exc: Exception) -> int | None:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)

    if status_code is None:
        return None

    try:
        return int(status_code)
    except (TypeError, ValueError):
        return None


def build_pwa_meta() -> dict:
    return {
        "pushSubscriptionsEnabled": bool(getattr(settings, "PWA_PUSH_SUBSCRIPTIONS_ENABLED", True)),
        "pushDeliveryEnabled": bool(getattr(settings, "PWA_PUSH_SEND_ENABLED", False)),
        "pushProviderConfigured": is_push_provider_configured(),
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


def is_push_provider_configured() -> bool:
    return bool(
        getattr(settings, "PWA_VAPID_PUBLIC_KEY", "")
        and getattr(settings, "PWA_VAPID_PRIVATE_KEY", "")
        and getattr(settings, "PWA_VAPID_SUBJECT", "")
    )
