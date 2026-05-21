from django.contrib import admin

from apps.finance.models import Tag, TagGroup


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
