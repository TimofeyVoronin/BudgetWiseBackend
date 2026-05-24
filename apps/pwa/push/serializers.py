from __future__ import annotations

from urllib.parse import urlparse

from django.conf import settings
from drf_spectacular.utils import OpenApiExample, extend_schema_field
from rest_framework import serializers

from apps.pwa.models import PwaPushProvider, PwaPushSubscription


class PwaMetaSerializer(serializers.Serializer):
    pushSubscriptionsEnabled = serializers.BooleanField()
    pushDeliveryEnabled = serializers.BooleanField()
    backgroundSyncEnabled = serializers.BooleanField()
    supportedPushProvider = serializers.CharField()
    vapidPublicKey = serializers.CharField(allow_blank=True)
    maxSubscriptionsPerUser = serializers.IntegerField()
    supportedEvents = serializers.ListField(child=serializers.CharField())
    endpoints = serializers.DictField(child=serializers.CharField())


class PwaPushSubscriptionCreateSerializer(serializers.Serializer):
    deviceId = serializers.CharField(max_length=120)
    endpoint = serializers.URLField(max_length=2048)
    p256dh = serializers.CharField(allow_blank=False, trim_whitespace=True)
    auth = serializers.CharField(allow_blank=False, trim_whitespace=True)
    browser = serializers.CharField(max_length=80, required=False, allow_blank=True)
    platform = serializers.CharField(max_length=80, required=False, allow_blank=True)
    userAgent = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    isActive = serializers.BooleanField(required=False, default=True)

    def validate_endpoint(self, value: str) -> str:
        normalized_value = value.strip()
        parsed_endpoint = urlparse(normalized_value)

        if parsed_endpoint.scheme not in {"https", "http"} or not parsed_endpoint.netloc:
            raise serializers.ValidationError("Укажите корректный push endpoint.")

        return normalized_value

    def validate_deviceId(self, value: str) -> str:
        normalized_value = value.strip()

        if not normalized_value:
            raise serializers.ValidationError("Укажите ID устройства.")

        return normalized_value


class PwaPushSubscriptionSerializer(serializers.ModelSerializer):
    deviceId = serializers.CharField(source="device_id", read_only=True)
    endpointHost = serializers.CharField(source="endpoint_host", read_only=True)
    isActive = serializers.BooleanField(source="is_active", read_only=True)
    lastUsedAt = serializers.DateTimeField(source="last_used_at", read_only=True, allow_null=True)
    revokedAt = serializers.DateTimeField(source="revoked_at", read_only=True, allow_null=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)

    class Meta:
        model = PwaPushSubscription
        fields = [
            "id",
            "deviceId",
            "provider",
            "endpointHost",
            "browser",
            "platform",
            "user_agent",
            "isActive",
            "lastUsedAt",
            "revokedAt",
            "createdAt",
            "updatedAt",
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["userAgent"] = data.pop("user_agent")
        data["id"] = str(data["id"])
        return data


class PwaPushSubscriptionsListSerializer(serializers.Serializer):
    items = PwaPushSubscriptionSerializer(many=True)


class PwaPushSubscriptionDeleteSerializer(serializers.Serializer):
    deleted = serializers.BooleanField()
    id = serializers.CharField()


class PwaPushSubscriptionTestResponseSerializer(serializers.Serializer):
    sent = serializers.BooleanField()
    provider = serializers.CharField()
    code = serializers.CharField(required=False)
    message = serializers.CharField(required=False)


PWA_SUPPORTED_EVENTS = [
    "budget_limit_warning",
    "planned_transaction_due",
    "receipt_imported",
    "sync_conflict",
    "sync_failed",
]


PWA_META_EXAMPLE = OpenApiExample(
    "Успешный ответ",
    value={
        "pushSubscriptionsEnabled": True,
        "pushDeliveryEnabled": False,
        "backgroundSyncEnabled": True,
        "supportedPushProvider": "web_push",
        "vapidPublicKey": "",
        "maxSubscriptionsPerUser": 10,
        "supportedEvents": PWA_SUPPORTED_EVENTS,
        "endpoints": {
            "pushSubscriptions": "/api/v1/pwa/push-subscriptions/",
            "notificationSettings": "/api/v1/pwa/notification-settings/",
            "backgroundSyncMeta": "/api/v1/pwa/background-sync/meta/",
        },
    },
    response_only=True,
)
