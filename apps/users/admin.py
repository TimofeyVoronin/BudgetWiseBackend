from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from apps.users.models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("id", "username", "email", "first_name", "last_name", "phone", "city", "avatar", "is_staff")
    search_fields = ("username", "email", "first_name", "last_name", "middle_name", "phone", "city")
    ordering = ("id",)
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