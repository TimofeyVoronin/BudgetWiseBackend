from rest_framework import serializers

from apps.pwa.models import PwaNotificationSettings


class PwaNotificationSettingsSerializer(serializers.ModelSerializer):
    pushEnabled = serializers.BooleanField(source="push_enabled")
    syncConflict = serializers.BooleanField(source="sync_conflict")
    syncFailed = serializers.BooleanField(source="sync_failed")
    budgetLimitWarning = serializers.BooleanField(source="budget_limit_warning")
    plannedTransactionDue = serializers.BooleanField(source="planned_transaction_due")
    receiptImported = serializers.BooleanField(source="receipt_imported")
    quietHoursEnabled = serializers.BooleanField(source="quiet_hours_enabled")
    quietHoursFrom = serializers.TimeField(source="quiet_hours_from", format="%H:%M")
    quietHoursTo = serializers.TimeField(source="quiet_hours_to", format="%H:%M")
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)

    class Meta:
        model = PwaNotificationSettings
        fields = [
            "pushEnabled",
            "syncConflict",
            "syncFailed",
            "budgetLimitWarning",
            "plannedTransactionDue",
            "receiptImported",
            "quietHoursEnabled",
            "quietHoursFrom",
            "quietHoursTo",
            "createdAt",
            "updatedAt",
        ]

    def validate(self, attrs):
        quiet_hours_enabled = attrs.get("quiet_hours_enabled")
        quiet_hours_from = attrs.get("quiet_hours_from")
        quiet_hours_to = attrs.get("quiet_hours_to")

        if quiet_hours_enabled and quiet_hours_from == quiet_hours_to:
            raise serializers.ValidationError(
                {
                    "quietHoursTo": [
                        "Окончание тихих часов должно отличаться от начала."
                    ]
                }
            )

        return attrs
