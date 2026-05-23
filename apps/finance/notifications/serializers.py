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
    NotificationSettings,
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
    {
        "title": "Маркетинг и акции",
        "value": NotificationType.MARKETING,
        "icon": "tag",
        "iconTone": NotificationIconTone.INFO,
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


MAX_BULK_NOTIFICATION_IDS = 100


class NotificationBulkIdsSerializer(serializers.Serializer):
    ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
        max_length=MAX_BULK_NOTIFICATION_IDS,
    )

    def validate_ids(self, value):
        unique_ids = []

        for notification_id in value:
            if notification_id not in unique_ids:
                unique_ids.append(notification_id)

        return unique_ids


class NotificationBulkResultSerializer(serializers.Serializer):
    updated_count = serializers.IntegerField()
    updatedCount = serializers.IntegerField()

NOTIFICATION_QUIET_HOURS_DAY_OPTIONS = [
    {
        "title": "ПН",
        "value": "mon",
    },
    {
        "title": "ВТ",
        "value": "tue",
    },
    {
        "title": "СР",
        "value": "wed",
    },
    {
        "title": "ЧТ",
        "value": "thu",
    },
    {
        "title": "ПТ",
        "value": "fri",
    },
    {
        "title": "СБ",
        "value": "sat",
    },
    {
        "title": "ВС",
        "value": "sun",
    },
]

NOTIFICATION_SETTING_BOOLEAN_ALIASES = {
    "inAppEnabled": "in_app_enabled",
    "emailEnabled": "email_enabled",
    "pushEnabled": "push_enabled",
    "smsEnabled": "sms_enabled",
    "operationEnabled": "operation_enabled",
    "goalEnabled": "goal_enabled",
    "budgetEnabled": "budget_enabled",
    "systemEnabled": "system_enabled",
    "securityEnabled": "security_enabled",
    "marketingEnabled": "marketing_enabled",
    "quietHoursEnabled": "quiet_hours_enabled",
    "quietHoursStart": "quiet_hours_start",
    "quietHoursEnd": "quiet_hours_end",
    "quietHoursDays": "quiet_hours_days",
}

NOTIFICATION_QUIET_HOURS_DAYS = {
    option["value"]
    for option in NOTIFICATION_QUIET_HOURS_DAY_OPTIONS
}


class NotificationSettingsChannelSerializer(serializers.Serializer):
    channel = serializers.CharField()
    label = serializers.CharField()
    icon = serializers.CharField()
    enabled = serializers.BooleanField()
    hint = serializers.CharField()


class NotificationSettingsTypeSerializer(serializers.Serializer):
    type = serializers.CharField()
    label = serializers.CharField()
    icon = serializers.CharField()
    iconTone = serializers.CharField()
    enabled = serializers.BooleanField()


class NotificationQuietHoursDayOptionSerializer(serializers.Serializer):
    title = serializers.CharField()
    value = serializers.CharField()


class NotificationSettingsSerializer(serializers.ModelSerializer):
    inAppEnabled = serializers.SerializerMethodField(read_only=True)
    emailEnabled = serializers.SerializerMethodField(read_only=True)
    pushEnabled = serializers.SerializerMethodField(read_only=True)
    smsEnabled = serializers.SerializerMethodField(read_only=True)

    operationEnabled = serializers.SerializerMethodField(read_only=True)
    goalEnabled = serializers.SerializerMethodField(read_only=True)
    budgetEnabled = serializers.SerializerMethodField(read_only=True)
    systemEnabled = serializers.SerializerMethodField(read_only=True)
    securityEnabled = serializers.SerializerMethodField(read_only=True)
    marketingEnabled = serializers.SerializerMethodField(read_only=True)

    quietHoursEnabled = serializers.SerializerMethodField(read_only=True)
    quietHoursStart = serializers.SerializerMethodField(read_only=True)
    quietHoursEnd = serializers.SerializerMethodField(read_only=True)
    quietHoursDays = serializers.SerializerMethodField(read_only=True)

    channels = serializers.SerializerMethodField(read_only=True)
    types = serializers.SerializerMethodField(read_only=True)
    quietHoursDayOptions = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = NotificationSettings
        fields = [
            "id",
            "in_app_enabled",
            "inAppEnabled",
            "email_enabled",
            "emailEnabled",
            "push_enabled",
            "pushEnabled",
            "sms_enabled",
            "smsEnabled",
            "operation_enabled",
            "operationEnabled",
            "goal_enabled",
            "goalEnabled",
            "budget_enabled",
            "budgetEnabled",
            "system_enabled",
            "systemEnabled",
            "security_enabled",
            "securityEnabled",
            "marketing_enabled",
            "marketingEnabled",
            "quiet_hours_enabled",
            "quietHoursEnabled",
            "quiet_hours_start",
            "quietHoursStart",
            "quiet_hours_end",
            "quietHoursEnd",
            "quiet_hours_days",
            "quietHoursDays",
            "channels",
            "types",
            "quietHoursDayOptions",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "inAppEnabled",
            "emailEnabled",
            "pushEnabled",
            "smsEnabled",
            "operationEnabled",
            "goalEnabled",
            "budgetEnabled",
            "systemEnabled",
            "securityEnabled",
            "marketingEnabled",
            "quietHoursEnabled",
            "quietHoursStart",
            "quietHoursEnd",
            "quietHoursDays",
            "channels",
            "types",
            "quietHoursDayOptions",
            "created_at",
            "updated_at",
        ]

    def to_internal_value(self, data):
        mutable_data = data.copy()

        for alias, field_name in NOTIFICATION_SETTING_BOOLEAN_ALIASES.items():
            if alias in mutable_data and field_name not in mutable_data:
                mutable_data[field_name] = mutable_data[alias]

        return super().to_internal_value(mutable_data)

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_inAppEnabled(self, obj) -> bool:
        return obj.in_app_enabled

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_emailEnabled(self, obj) -> bool:
        return obj.email_enabled

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_pushEnabled(self, obj) -> bool:
        return obj.push_enabled

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_smsEnabled(self, obj) -> bool:
        return obj.sms_enabled

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_operationEnabled(self, obj) -> bool:
        return obj.operation_enabled

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_goalEnabled(self, obj) -> bool:
        return obj.goal_enabled

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_budgetEnabled(self, obj) -> bool:
        return obj.budget_enabled

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_systemEnabled(self, obj) -> bool:
        return obj.system_enabled

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_securityEnabled(self, obj) -> bool:
        return obj.security_enabled

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_marketingEnabled(self, obj) -> bool:
        return obj.marketing_enabled

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_quietHoursEnabled(self, obj) -> bool:
        return obj.quiet_hours_enabled

    @extend_schema_field(OpenApiTypes.STR)
    def get_quietHoursStart(self, obj) -> str:
        return obj.quiet_hours_start.strftime("%H:%M")

    @extend_schema_field(OpenApiTypes.STR)
    def get_quietHoursEnd(self, obj) -> str:
        return obj.quiet_hours_end.strftime("%H:%M")

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_quietHoursDays(self, obj) -> list[str]:
        return obj.quiet_hours_days

    @extend_schema_field(NotificationSettingsChannelSerializer(many=True))
    def get_channels(self, obj) -> list[dict]:
        return [
            {
                "channel": option["value"],
                "label": option["title"],
                "icon": option["icon"],
                "enabled": obj.is_channel_enabled(option["value"]),
                "hint": option["hint"],
            }
            for option in NOTIFICATION_CHANNEL_OPTIONS
        ]

    @extend_schema_field(NotificationSettingsTypeSerializer(many=True))
    def get_types(self, obj) -> list[dict]:
        return [
            {
                "type": option["value"],
                "label": option["title"],
                "icon": option["icon"],
                "iconTone": option["iconTone"],
                "enabled": obj.is_type_enabled(option["value"]),
            }
            for option in NOTIFICATION_TYPE_OPTIONS
        ]

    @extend_schema_field(NotificationQuietHoursDayOptionSerializer(many=True))
    def get_quietHoursDayOptions(self, obj) -> list[dict]:
        return NOTIFICATION_QUIET_HOURS_DAY_OPTIONS

    def validate_quiet_hours_days(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError(
                "Дни тихих часов должны быть списком."
            )

        result = []
        invalid_days = []

        for day in value:
            if not isinstance(day, str):
                invalid_days.append(str(day))
                continue

            normalized_day = day.strip().lower()

            if normalized_day not in NOTIFICATION_QUIET_HOURS_DAYS:
                invalid_days.append(day)
                continue

            if normalized_day not in result:
                result.append(normalized_day)

        if invalid_days:
            raise serializers.ValidationError(
                (
                    "Недопустимые дни тихих часов: "
                    f"{', '.join(invalid_days)}."
                )
            )

        return result

    def validate(self, attrs):
        quiet_hours_enabled = attrs.get(
            "quiet_hours_enabled",
            getattr(self.instance, "quiet_hours_enabled", False),
        )

        quiet_hours_days = attrs.get(
            "quiet_hours_days",
            getattr(self.instance, "quiet_hours_days", []),
        )

        quiet_hours_start = attrs.get(
            "quiet_hours_start",
            getattr(self.instance, "quiet_hours_start", None),
        )
        quiet_hours_end = attrs.get(
            "quiet_hours_end",
            getattr(self.instance, "quiet_hours_end", None),
        )

        if quiet_hours_enabled:
            errors = {}

            if quiet_hours_start is None:
                errors["quiet_hours_start"] = [
                    "Укажите начало тихих часов."
                ]

            if quiet_hours_end is None:
                errors["quiet_hours_end"] = [
                    "Укажите окончание тихих часов."
                ]

            if not quiet_hours_days:
                errors["quiet_hours_days"] = [
                    "Выберите хотя бы один день для тихих часов."
                ]

            if errors:
                raise serializers.ValidationError(errors)

        return attrs

