from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from apps.users.models import User, UserProfileAuditLog


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
    list_display = ("id", "username", "email", "first_name", "last_name", "phone", "city", "avatar", "is_staff")
    search_fields = ("username", "email", "first_name", "last_name", "middle_name", "phone", "city")
    ordering = ("id",)
    inlines = [UserProfileAuditLogInline]
    fieldsets = UserAdmin.fieldsets + (
        (
            "Профиль",
            {
                "fields": (
                    "middle_name",
                    "phone",
                    "city",
                    "bio",
                    "avatar",
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
