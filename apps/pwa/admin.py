from django.contrib import admin

from apps.pwa.models import PwaNotificationSettings, PwaPushSubscription


@admin.register(PwaPushSubscription)
class PwaPushSubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "device_id",
        "provider",
        "endpoint_host",
        "is_active",
        "last_used_at",
        "created_at",
        "updated_at",
    )
    list_filter = ("provider", "is_active", "browser", "platform")
    search_fields = ("device_id", "endpoint", "browser", "platform", "user__email", "user__username")
    readonly_fields = ("created_at", "updated_at", "last_used_at", "revoked_at")


@admin.register(PwaNotificationSettings)
class PwaNotificationSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "push_enabled",
        "sync_conflict",
        "sync_failed",
        "quiet_hours_enabled",
        "updated_at",
    )
    list_filter = ("push_enabled", "sync_conflict", "sync_failed", "quiet_hours_enabled")
    search_fields = ("user__email", "user__username")
    readonly_fields = ("created_at", "updated_at")
