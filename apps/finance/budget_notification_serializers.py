from __future__ import annotations

from rest_framework import serializers

from apps.finance.budget_notifications import (
    build_budget_notification_preview,
    build_budget_notification_test_result,
    get_budget_notifications_meta_payload,
    get_or_create_budget_notification_settings,
    update_budget_notification_settings,
    validate_budget_notification_thresholds,
)
from apps.finance.models import (
    BudgetNotificationChannel,
    BudgetNotificationDeliveryStatus,
    BudgetNotificationEventGroup,
    BudgetNotificationEventType,
    BudgetNotificationSettings,
)


class BudgetNotificationThresholdSerializer(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()
    hint = serializers.CharField(allow_blank=True)
    percent = serializers.IntegerField(min_value=1, max_value=100)
    active = serializers.BooleanField()
    locked = serializers.BooleanField()


class BudgetNotificationEventSettingSerializer(serializers.Serializer):
    id = serializers.ChoiceField(choices=BudgetNotificationEventType.choices)
    group = serializers.ChoiceField(choices=BudgetNotificationEventGroup.choices)
    label = serializers.CharField()
    icon = serializers.CharField()
    iconTone = serializers.CharField()
    enabled = serializers.BooleanField()


class BudgetNotificationChannelSettingSerializer(serializers.Serializer):
    id = serializers.ChoiceField(choices=BudgetNotificationChannel.choices)
    label = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    icon = serializers.CharField()
    enabled = serializers.BooleanField()
    deliveryHint = serializers.CharField(allow_blank=True)
    deliveryOk = serializers.BooleanField()
    deliveryStatus = serializers.ChoiceField(
        choices=BudgetNotificationDeliveryStatus.choices,
        required=False,
    )


class BudgetNotificationAntiSpamSettingsSerializer(serializers.Serializer):
    minRepeatHours = serializers.IntegerField(min_value=1, max_value=168)
    groupNotifications = serializers.BooleanField()
    cooldownMinutes = serializers.IntegerField(min_value=0, max_value=1440)


class BudgetNotificationGoalsSettingsSerializer(serializers.Serializer):
    milestonePercents = serializers.ListField(
        child=serializers.IntegerField(min_value=1, max_value=100),
    )
    milestoneEnabled = serializers.DictField(
        child=serializers.BooleanField(),
    )
    notifyOnLag = serializers.BooleanField()
    lagDays = serializers.IntegerField(min_value=1, max_value=365)
    selectedGoalIds = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
    )


class BudgetNotificationsSettingsSerializer(serializers.ModelSerializer):
    thresholdsEnabled = serializers.BooleanField(source="thresholds_enabled")
    antiSpam = BudgetNotificationAntiSpamSettingsSerializer(source="anti_spam")
    previewUsagePercent = serializers.IntegerField(source="preview_usage_percent")

    class Meta:
        model = BudgetNotificationSettings
        fields = [
            "enabled",
            "thresholdsEnabled",
            "thresholds",
            "events",
            "channels",
            "antiSpam",
            "goals",
            "previewUsagePercent",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]

    thresholds = BudgetNotificationThresholdSerializer(many=True)
    events = BudgetNotificationEventSettingSerializer(many=True)
    channels = BudgetNotificationChannelSettingSerializer(many=True)
    goals = BudgetNotificationGoalsSettingsSerializer()
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)

    class Meta:
        model = BudgetNotificationSettings
        fields = [
            "enabled",
            "thresholdsEnabled",
            "thresholds",
            "events",
            "channels",
            "antiSpam",
            "goals",
            "previewUsagePercent",
            "updatedAt",
        ]
        read_only_fields = ["updatedAt"]


class BudgetNotificationThresholdUpdateItemSerializer(serializers.Serializer):
    id = serializers.CharField()
    percent = serializers.IntegerField(min_value=1, max_value=100, required=False)
    active = serializers.BooleanField(required=False)


class BudgetNotificationEventUpdateItemSerializer(serializers.Serializer):
    id = serializers.ChoiceField(choices=BudgetNotificationEventType.choices)
    enabled = serializers.BooleanField()


class BudgetNotificationChannelUpdateItemSerializer(serializers.Serializer):
    id = serializers.ChoiceField(choices=BudgetNotificationChannel.choices)
    enabled = serializers.BooleanField()


class BudgetNotificationAntiSpamUpdateSerializer(serializers.Serializer):
    minRepeatHours = serializers.IntegerField(min_value=1, max_value=168, required=False)
    groupNotifications = serializers.BooleanField(required=False)
    cooldownMinutes = serializers.IntegerField(min_value=0, max_value=1440, required=False)


class BudgetNotificationGoalsUpdateSerializer(serializers.Serializer):
    milestonePercents = serializers.ListField(
        child=serializers.IntegerField(min_value=1, max_value=100),
        required=False,
    )
    milestoneEnabled = serializers.DictField(
        child=serializers.BooleanField(),
        required=False,
    )
    notifyOnLag = serializers.BooleanField(required=False)
    lagDays = serializers.IntegerField(min_value=1, max_value=365, required=False)
    selectedGoalIds = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
    )


class UpdateBudgetNotificationsSettingsSerializer(serializers.Serializer):
    enabled = serializers.BooleanField(required=False)
    thresholdsEnabled = serializers.BooleanField(required=False)
    thresholds = BudgetNotificationThresholdUpdateItemSerializer(many=True, required=False)
    events = BudgetNotificationEventUpdateItemSerializer(many=True, required=False)
    channels = BudgetNotificationChannelUpdateItemSerializer(many=True, required=False)
    antiSpam = BudgetNotificationAntiSpamUpdateSerializer(required=False)
    goals = BudgetNotificationGoalsUpdateSerializer(required=False)
    previewUsagePercent = serializers.IntegerField(min_value=0, max_value=100, required=False)

    def update_settings(self, *, settings: BudgetNotificationSettings) -> BudgetNotificationSettings:
        return update_budget_notification_settings(
            settings=settings,
            payload=self.validated_data,
        )


class ValidateBudgetNotificationThresholdsSerializer(serializers.Serializer):
    thresholds = BudgetNotificationThresholdUpdateItemSerializer(many=True)

    def validate_thresholds_for_user(self, *, user) -> dict:
        return validate_budget_notification_thresholds(
            user=user,
            thresholds=self.validated_data["thresholds"],
        )


class ValidateBudgetNotificationThresholdsResponseSerializer(serializers.Serializer):
    ok = serializers.BooleanField()
    fieldErrors = serializers.DictField(child=serializers.CharField(), required=False)
    generalMessage = serializers.CharField(required=False, allow_null=True, allow_blank=True)


class SendBudgetNotificationTestSerializer(serializers.Serializer):
    channelIds = serializers.ListField(
        child=serializers.ChoiceField(choices=BudgetNotificationChannel.choices),
        required=False,
    )
    eventId = serializers.ChoiceField(choices=BudgetNotificationEventType.choices, required=False)

    def build_result(self, *, settings: BudgetNotificationSettings) -> dict:
        return build_budget_notification_test_result(
            settings=settings,
            channel_ids=self.validated_data.get("channelIds"),
            event_id=self.validated_data.get("eventId"),
        )


class BudgetNotificationTestChannelResultSerializer(serializers.Serializer):
    id = serializers.ChoiceField(choices=BudgetNotificationChannel.choices)
    status = serializers.ChoiceField(choices=["delivered", "failed", "skipped"])
    error = serializers.CharField(required=False, allow_blank=True)


class SendBudgetNotificationTestResponseSerializer(serializers.Serializer):
    sent = serializers.BooleanField()
    channels = BudgetNotificationTestChannelResultSerializer(many=True)


class BudgetNotificationPreviewChannelSampleSerializer(serializers.Serializer):
    channel = serializers.ChoiceField(choices=BudgetNotificationChannel.choices)
    title = serializers.CharField()
    body = serializers.CharField()


class BudgetNotificationPreviewSerializer(serializers.Serializer):
    eventTitle = serializers.CharField()
    eventSubtitle = serializers.CharField()
    channels = BudgetNotificationPreviewChannelSampleSerializer(many=True)
    activeChannelIds = serializers.ListField(child=serializers.ChoiceField(choices=BudgetNotificationChannel.choices))

    @staticmethod
    def build_payload(*, settings: BudgetNotificationSettings) -> dict:
        return build_budget_notification_preview(settings=settings)


class BudgetNotificationSelectOptionSerializer(serializers.Serializer):
    title = serializers.CharField()
    value = serializers.IntegerField()


class BudgetNotificationGoalOptionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    label = serializers.CharField()


class BudgetNotificationsMetaSerializer(serializers.Serializer):
    goals = BudgetNotificationGoalOptionSerializer(many=True)
    repeatHourOptions = BudgetNotificationSelectOptionSerializer(many=True)
    cooldownOptions = BudgetNotificationSelectOptionSerializer(many=True)
    lagDayOptions = BudgetNotificationSelectOptionSerializer(many=True)
    milestonePercents = serializers.ListField(child=serializers.IntegerField())

    @staticmethod
    def build_payload(*, user) -> dict:
        return get_budget_notifications_meta_payload(user=user)


class BudgetNotificationsSettingsResponseSerializer(BudgetNotificationsSettingsSerializer):
    pass


def get_current_budget_notifications_payload(*, user) -> BudgetNotificationSettings:
    return get_or_create_budget_notification_settings(user=user)
