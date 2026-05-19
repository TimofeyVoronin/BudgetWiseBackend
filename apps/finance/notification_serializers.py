from decimal import Decimal

from django.utils import timezone
from drf_spectacular.utils import OpenApiTypes, extend_schema_field
from rest_framework import serializers

from apps.finance.models import (
    Notification,
    NotificationChannel,
    NotificationDeliveryStatus,
    NotificationEntityKind,
    NotificationIconTone,
    NotificationType,
)


NOTIFICATION_CHANNEL_OPTIONS = [
    {
        "title": "In-app",
        "value": NotificationChannel.IN_APP,
        "icon": "bell",
        "active": True,
        "hint": "Уведомления внутри приложения.",
    },
    {
        "title": "Email",
        "value": NotificationChannel.EMAIL,
        "icon": "email",
        "active": True,
        "hint": "Уведомления по электронной почте.",
    },
    {
        "title": "Push",
        "value": NotificationChannel.PUSH,
        "icon": "cellphone",
        "active": True,
        "hint": "Push-уведомления на устройстве.",
    },
    {
        "title": "SMS",
        "value": NotificationChannel.SMS,
        "icon": "message-text",
        "active": True,
        "hint": "SMS-уведомления.",
    },
]

NOTIFICATION_TYPE_OPTIONS = [
    {
        "title": "Операции",
        "value": NotificationType.OPERATION,
        "icon": "credit-card",
        "iconTone": NotificationIconTone.PRIMARY,
    },
    {
        "title": "Цели",
        "value": NotificationType.GOAL,
        "icon": "target",
        "iconTone": NotificationIconTone.SUCCESS,
    },
    {
        "title": "Бюджет",
        "value": NotificationType.BUDGET,
        "icon": "chart-pie",
        "iconTone": NotificationIconTone.WARNING,
    },
    {
        "title": "Система",
        "value": NotificationType.SYSTEM,
        "icon": "information",
        "iconTone": NotificationIconTone.INFO,
    },
    {
        "title": "Безопасность",
        "value": NotificationType.SECURITY,
        "icon": "shield-alert",
        "iconTone": NotificationIconTone.ERROR,
    },
]

NOTIFICATION_STATUS_OPTIONS = [
    {
        "title": "Все",
        "value": "all",
    },
    {
        "title": "Непрочитано",
        "value": "unread",
    },
    {
        "title": "Прочитано",
        "value": "read",
    },
    {
        "title": "Архив",
        "value": "archived",
    },
]

NOTIFICATION_DELIVERY_STATUS_OPTIONS = [
    {
        "title": "Доставлено",
        "value": NotificationDeliveryStatus.DELIVERED,
    },
    {
        "title": "Ошибка доставки",
        "value": NotificationDeliveryStatus.FAILED,
    },
    {
        "title": "Ожидает доставки",
        "value": NotificationDeliveryStatus.PENDING,
    },
    {
        "title": "Канал недоступен",
        "value": NotificationDeliveryStatus.UNAVAILABLE,
    },
]

NOTIFICATION_ENTITY_KIND_OPTIONS = [
    {
        "title": "Операция",
        "value": NotificationEntityKind.TRANSACTION,
    },
    {
        "title": "Цель",
        "value": NotificationEntityKind.GOAL,
    },
    {
        "title": "Бюджет",
        "value": NotificationEntityKind.BUDGET,
    },
]

NOTIFICATION_ICON_TONE_OPTIONS = [
    {
        "title": "Основной",
        "value": NotificationIconTone.PRIMARY,
    },
    {
        "title": "Успех",
        "value": NotificationIconTone.SUCCESS,
    },
    {
        "title": "Предупреждение",
        "value": NotificationIconTone.WARNING,
    },
    {
        "title": "Ошибка",
        "value": NotificationIconTone.ERROR,
    },
    {
        "title": "Информация",
        "value": NotificationIconTone.INFO,
    },
]


class NotificationEntityLinkSerializer(serializers.Serializer):
    kind = serializers.CharField()
    routeName = serializers.CharField()
    label = serializers.CharField()


class NotificationDeliveryStepSerializer(serializers.Serializer):
    label = serializers.CharField()
    at = serializers.DateTimeField()


class NotificationSerializer(serializers.ModelSerializer):
    type_label = serializers.CharField(source="get_type_display", read_only=True)
    channel_label = serializers.CharField(source="get_channel_display", read_only=True)
    delivery_status_label = serializers.CharField(
        source="get_delivery_status_display",
        read_only=True,
    )

    status = serializers.SerializerMethodField(read_only=True)
    isRead = serializers.SerializerMethodField(read_only=True)
    iconTone = serializers.SerializerMethodField(read_only=True)
    typeLabel = serializers.SerializerMethodField(read_only=True)
    channelLabel = serializers.SerializerMethodField(read_only=True)
    deliveryStatus = serializers.SerializerMethodField(read_only=True)
    deliveryError = serializers.SerializerMethodField(read_only=True)
    createdAt = serializers.SerializerMethodField(read_only=True)
    timeLabel = serializers.SerializerMethodField(read_only=True)
    entityTag = serializers.SerializerMethodField(read_only=True)
    entityLink = serializers.SerializerMethodField(read_only=True)
    amountRub = serializers.SerializerMethodField(read_only=True)
    accountName = serializers.SerializerMethodField(read_only=True)
    categoryName = serializers.SerializerMethodField(read_only=True)
    relatedGoalName = serializers.SerializerMethodField(read_only=True)
    relatedGoalPercent = serializers.SerializerMethodField(read_only=True)
    deliverySteps = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Notification
        fields = [
            "id",
            "title",
            "body",
            "icon",
            "icon_tone",
            "iconTone",
            "type",
            "type_label",
            "typeLabel",
            "channel",
            "channel_label",
            "channelLabel",
            "status",
            "is_read",
            "isRead",
            "delivery_status",
            "delivery_status_label",
            "deliveryStatus",
            "delivery_error",
            "deliveryError",
            "created_at",
            "createdAt",
            "timeLabel",
            "entity_kind",
            "entity_id",
            "entity_route_name",
            "entity_label",
            "entity_tag",
            "entityTag",
            "entityLink",
            "amount",
            "amountRub",
            "account_name",
            "accountName",
            "category_name",
            "categoryName",
            "related_goal_name",
            "relatedGoalName",
            "related_goal_percent",
            "relatedGoalPercent",
            "delivery_steps",
            "deliverySteps",
            "read_at",
            "is_archived",
            "archived_at",
            "updated_at",
        ]
        read_only_fields = fields

    @extend_schema_field(OpenApiTypes.STR)
    def get_status(self, obj) -> str:
        return obj.status

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_isRead(self, obj) -> bool:
        return obj.is_read

    @extend_schema_field(OpenApiTypes.STR)
    def get_iconTone(self, obj) -> str:
        return obj.icon_tone

    @extend_schema_field(OpenApiTypes.STR)
    def get_typeLabel(self, obj) -> str:
        return obj.get_type_display()

    @extend_schema_field(OpenApiTypes.STR)
    def get_channelLabel(self, obj) -> str:
        return obj.get_channel_display()

    @extend_schema_field(OpenApiTypes.STR)
    def get_deliveryStatus(self, obj) -> str:
        return obj.delivery_status

    @extend_schema_field(OpenApiTypes.STR)
    def get_deliveryError(self, obj) -> str:
        return obj.delivery_error

    @extend_schema_field(OpenApiTypes.DATETIME)
    def get_createdAt(self, obj):
        return obj.created_at

    @extend_schema_field(OpenApiTypes.STR)
    def get_timeLabel(self, obj) -> str:
        created_at = timezone.localtime(obj.created_at)
        return created_at.strftime("%d.%m.%Y %H:%M")

    @extend_schema_field(OpenApiTypes.STR)
    def get_entityTag(self, obj) -> str:
        return obj.entity_tag

    @extend_schema_field(NotificationEntityLinkSerializer)
    def get_entityLink(self, obj):
        if not obj.entity_kind:
            return None

        return {
            "kind": obj.entity_kind,
            "routeName": obj.entity_route_name,
            "label": obj.entity_label,
        }

    @extend_schema_field(OpenApiTypes.STR)
    def get_amountRub(self, obj) -> str | None:
        return self._format_decimal(obj.amount)

    @extend_schema_field(OpenApiTypes.STR)
    def get_accountName(self, obj) -> str:
        return obj.account_name

    @extend_schema_field(OpenApiTypes.STR)
    def get_categoryName(self, obj) -> str:
        return obj.category_name

    @extend_schema_field(OpenApiTypes.STR)
    def get_relatedGoalName(self, obj) -> str:
        return obj.related_goal_name

    @extend_schema_field(OpenApiTypes.STR)
    def get_relatedGoalPercent(self, obj) -> str | None:
        return self._format_decimal(obj.related_goal_percent)

    @extend_schema_field(NotificationDeliveryStepSerializer(many=True))
    def get_deliverySteps(self, obj) -> list:
        return obj.delivery_steps

    def _format_decimal(self, value: Decimal | None) -> str | None:
        if value is None:
            return None

        return str(value.quantize(Decimal("0.01")))


class NotificationSummarySerializer(serializers.Serializer):
    unread_count = serializers.IntegerField()
    today_count = serializers.IntegerField()
    delivery_errors_count = serializers.IntegerField()
    archived_count = serializers.IntegerField()
    total_count = serializers.IntegerField()

    unreadCount = serializers.IntegerField()
    todayCount = serializers.IntegerField()
    deliveryErrorsCount = serializers.IntegerField()
    archivedCount = serializers.IntegerField()
    totalCount = serializers.IntegerField()


class NotificationOptionSerializer(serializers.Serializer):
    title = serializers.CharField()
    value = serializers.CharField()
    icon = serializers.CharField(required=False)
    iconTone = serializers.CharField(required=False)
    active = serializers.BooleanField(required=False)
    hint = serializers.CharField(required=False)


class NotificationMetaSerializer(serializers.Serializer):
    channels = NotificationOptionSerializer(many=True)
    types = NotificationOptionSerializer(many=True)
    statuses = NotificationOptionSerializer(many=True)
    deliveryStatuses = NotificationOptionSerializer(many=True)
    entityKinds = NotificationOptionSerializer(many=True)
    iconTones = NotificationOptionSerializer(many=True)


class NotificationBulkIdsSerializer(serializers.Serializer):
    ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
    )


class NotificationBulkResultSerializer(serializers.Serializer):
    updated_count = serializers.IntegerField()
    updatedCount = serializers.IntegerField()
