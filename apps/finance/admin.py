from django.contrib import admin

from apps.finance.models import (
    BudgetNotificationEvent,
    BudgetNotificationSettings,
    Currency,
    Receipt,
    Tag,
    TagGroup,
    TransactionTemplate,
    UserCurrency,
)


@admin.register(TagGroup)
class TagGroupAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "user", "is_system", "created_at")
    list_filter = ("is_system",)
    search_fields = ("name", "user__email")
    readonly_fields = ("normalized_name", "created_at", "updated_at")


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "user", "group", "color", "icon", "is_visible", "is_system")
    list_filter = ("is_visible", "is_system", "group")
    search_fields = ("name", "description", "group__name", "user__email")
    readonly_fields = ("normalized_name", "created_at", "updated_at")


@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "fiscal_drive_number",
        "fiscal_document_number",
        "fiscal_sign",
        "total_amount",
        "status",
        "store_name",
        "created_at",
    )
    list_filter = ("status", "provider_name", "operation_type")
    search_fields = (
        "user__email",
        "user__username",
        "fiscal_drive_number",
        "fiscal_document_number",
        "fiscal_sign",
        "deduplication_key",
        "store_name",
        "seller_inn",
    )
    readonly_fields = (
        "raw_hash",
        "deduplication_key",
        "fiscal_key",
        "created_at",
        "updated_at",
    )


@admin.register(TransactionTemplate)
class TransactionTemplateAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "user",
        "kind",
        "amount",
        "currency",
        "account",
        "category",
        "status",
        "is_default",
        "use_count",
        "last_used_at",
        "created_at",
    )
    list_filter = ("kind", "status", "is_default", "currency")
    search_fields = (
        "name",
        "note",
        "account__name",
        "category__name",
        "tags__name",
        "user__email",
    )
    readonly_fields = ("normalized_name", "use_count", "last_used_at", "created_at", "updated_at")
    filter_horizontal = ("tags",)


@admin.register(BudgetNotificationSettings)
class BudgetNotificationSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "enabled",
        "thresholds_enabled",
        "preview_usage_percent",
        "created_at",
        "updated_at",
    )
    list_filter = ("enabled", "thresholds_enabled")
    search_fields = ("user__email", "user__username")
    readonly_fields = ("created_at", "updated_at")

@admin.register(BudgetNotificationEvent)
class BudgetNotificationEventAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "event_type",
        "related_object_type",
        "related_object_id",
        "threshold_id",
        "status",
        "created_at",
    )
    list_filter = ("event_type", "related_object_type", "status", "icon_tone")
    search_fields = ("title", "message", "deduplication_key", "user__email", "user__username")
    readonly_fields = ("deduplication_key", "created_at", "updated_at")



@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = ("id", "code", "name", "symbol", "is_system", "is_popular", "created_at")
    list_filter = ("is_system", "is_popular")
    search_fields = ("code", "name", "symbol")
    readonly_fields = ("created_at", "updated_at")


@admin.register(UserCurrency)
class UserCurrencyAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "currency",
        "is_primary",
        "is_visible",
        "is_custom",
        "rate_to_primary",
        "created_at",
    )
    list_filter = ("is_primary", "is_visible", "is_custom")
    search_fields = (
        "user__email",
        "user__username",
        "currency__code",
        "currency__name",
        "custom_name",
    )
    readonly_fields = ("created_at", "updated_at")
