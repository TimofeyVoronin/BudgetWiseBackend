from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from apps.users.models import (
    OnboardingSurvey,
    PhoneVerificationCode,
    User,
    UserAppSettings,
    UserProfileAuditLog,
)



class UserAppSettingsInline(admin.StackedInline):
    model = UserAppSettings
    extra = 0
    can_delete = False
    fields = (
        "timezone",
        "date_format",
        "number_format",
        "default_currency",
        "created_at",
        "updated_at",
    )
    readonly_fields = ("created_at", "updated_at")


class OnboardingSurveyInline(admin.StackedInline):
    model = OnboardingSurvey
    extra = 0
    can_delete = False
    fields = (
        "status",
        "answers",
        "result",
        "started_at",
        "completed_at",
        "created_at",
        "updated_at",
    )
    readonly_fields = ("created_at", "updated_at")


class UserProfileAuditLogInline(admin.TabularInline):
    model = UserProfileAuditLog
    extra = 0
    can_delete = False
    readonly_fields = (
        "action",
        "changed_fields",
        "old_values",
        "new_values",
        "metadata",
        "ip_address",
        "user_agent",
        "created_at",
    )
    fields = readonly_fields
    ordering = ("-created_at", "-id")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = (
        "id",
        "username",
        "email",
        "email_verified",
        "phone",
        "phone_verified",
        "first_name",
        "last_name",
        "city",
        "avatar",
        "avatar_url",
        "is_staff",
    )
    list_filter = ("email_verified", "phone_verified", "is_staff", "is_active")
    search_fields = ("username", "email", "first_name", "last_name", "middle_name", "phone", "city")
    ordering = ("id",)
    inlines = [UserAppSettingsInline, OnboardingSurveyInline, UserProfileAuditLogInline]
    fieldsets = UserAdmin.fieldsets + (
        (
            "Профиль",
            {
                "fields": (
                    "middle_name",
                    "phone",
                    "phone_verified",
                    "phone_verified_at",
                    "email_verified",
                    "email_verified_at",
                    "email_verification_sent_at",
                    "city",
                    "bio",
                    "avatar",
                    "avatar_url",
                    "avatar_public_id",
                ),
            },
        ),
    )


@admin.register(UserProfileAuditLog)
class UserProfileAuditLogAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "action", "changed_fields", "ip_address", "created_at")
    list_filter = ("action", "created_at")
    search_fields = ("user__email", "user__username", "ip_address", "user_agent")
    readonly_fields = (
        "user",
        "action",
        "changed_fields",
        "old_values",
        "new_values",
        "metadata",
        "ip_address",
        "user_agent",
        "created_at",
    )
    ordering = ("-created_at", "-id")

    def has_add_permission(self, request):
        return False


@admin.register(UserAppSettings)
class UserAppSettingsAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "timezone", "date_format", "number_format", "default_currency", "updated_at")
    list_filter = ("timezone", "date_format", "number_format", "default_currency")
    search_fields = ("user__email", "user__username", "default_currency")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("user_id",)


@admin.register(OnboardingSurvey)
class OnboardingSurveyAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "status", "started_at", "completed_at", "updated_at")
    list_filter = ("status", "created_at", "completed_at")
    search_fields = ("user__email", "user__username")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at", "-id")


@admin.register(PhoneVerificationCode)
class PhoneVerificationCodeAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "phone",
        "attempts_count",
        "sent_at",
        "expires_at",
        "confirmed_at",
    )
    list_filter = ("sent_at", "expires_at", "confirmed_at")
    search_fields = ("user__email", "user__username", "phone")
    readonly_fields = (
        "user",
        "phone",
        "code_hash",
        "attempts_count",
        "sent_at",
        "expires_at",
        "confirmed_at",
        "created_at",
    )
    ordering = ("-sent_at", "-id")

    def has_add_permission(self, request):
        return False

