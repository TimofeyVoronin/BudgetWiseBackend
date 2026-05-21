from __future__ import annotations

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.finance.models import Tag, TagGroup
from apps.finance.tags import (
    DEFAULT_TAG_COLOR,
    DEFAULT_TAG_ICON,
    TAG_COLOR_OPTIONS,
    TAG_ICON_OPTIONS,
    get_accessible_tag_groups,
    tag_duplicate_exists,
)


class TagGroupSerializer(serializers.Serializer):
    id = serializers.IntegerField(allow_null=True)
    name = serializers.CharField()


class TagSerializer(serializers.ModelSerializer):
    groupId = serializers.PrimaryKeyRelatedField(
        source="group",
        queryset=TagGroup.objects.none(),
        allow_null=True,
        required=False,
    )
    groupName = serializers.SerializerMethodField(read_only=True)
    operationsCount = serializers.SerializerMethodField(read_only=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)
    isVisible = serializers.BooleanField(source="is_visible", required=False, default=True)
    isSystem = serializers.BooleanField(source="is_system", read_only=True)

    class Meta:
        model = Tag
        fields = [
            "id",
            "name",
            "groupId",
            "groupName",
            "color",
            "icon",
            "operationsCount",
            "createdAt",
            "updatedAt",
            "isVisible",
            "isSystem",
            "description",
        ]
        read_only_fields = [
            "id",
            "groupName",
            "operationsCount",
            "createdAt",
            "updatedAt",
            "isSystem",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        request = self.context.get("request")
        queryset = TagGroup.objects.none()

        if request and request.user and request.user.is_authenticated:
            queryset = get_accessible_tag_groups(request.user)

        self.fields["groupId"].queryset = queryset

    def to_internal_value(self, data):
        mutable_data = data.copy()

        alias_map = {
            "group_id": "groupId",
            "group": "groupId",
            "is_visible": "isVisible",
        }

        for alias, field_name in alias_map.items():
            if alias in mutable_data and field_name not in mutable_data:
                mutable_data[field_name] = mutable_data[alias]

        return super().to_internal_value(mutable_data)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["id"] = instance.pk
        data["groupId"] = instance.group_id
        data["operationsCount"] = int(getattr(instance, "operations_count", 0) or 0)
        return data

    @extend_schema_field(OpenApiTypes.STR)
    def get_groupName(self, obj: Tag) -> str:
        return obj.group.name if obj.group_id else "Без группы"

    @extend_schema_field(OpenApiTypes.INT)
    def get_operationsCount(self, obj: Tag) -> int:
        return int(getattr(obj, "operations_count", 0) or 0)

    def validate_name(self, value: str) -> str:
        normalized_value = value.strip()

        if not normalized_value:
            raise serializers.ValidationError("Название тега не может быть пустым.")

        return normalized_value

    def validate_color(self, value: str) -> str:
        return value.upper()

    def validate_icon(self, value: str) -> str:
        normalized_value = value.strip()

        if not normalized_value:
            raise serializers.ValidationError("Иконка тега не может быть пустой.")

        return normalized_value

    def validate(self, attrs):
        request = self.context.get("request")
        instance = self.instance
        group = attrs.get("group") if "group" in attrs else getattr(instance, "group", None)
        name = attrs.get("name") or getattr(instance, "name", "")

        if group and request and not group.is_system and group.user_id != request.user.id:
            raise serializers.ValidationError(
                {
                    "groupId": [
                        "Группа тега должна принадлежать текущему пользователю."
                    ]
                }
            )

        if request and name:
            exclude_id = instance.pk if instance else None

            if tag_duplicate_exists(
                user=request.user,
                name=name,
                exclude_id=exclude_id,
            ):
                raise serializers.ValidationError(
                    {
                        "name": [
                            "Тег с таким названием уже существует."
                        ]
                    }
                )

        return attrs

    def create(self, validated_data):
        request = self.context.get("request")

        if request and request.user and request.user.is_authenticated:
            validated_data["user"] = request.user
            validated_data["is_system"] = False

        return super().create(validated_data)

    def update(self, instance, validated_data):
        if instance.is_system:
            raise serializers.ValidationError(
                {
                    "general": [
                        "Системный тег нельзя редактировать."
                    ]
                }
            )

        return super().update(instance, validated_data)


class TagsListSummarySerializer(serializers.Serializer):
    totalCount = serializers.IntegerField()
    withOperationsCount = serializers.IntegerField()
    withoutOperationsCount = serializers.IntegerField()


class TagsListResponseSerializer(serializers.Serializer):
    items = TagSerializer(many=True)
    summary = TagsListSummarySerializer()
    groups = TagGroupSerializer(many=True)


class TagSelectOptionSerializer(serializers.Serializer):
    title = serializers.CharField()
    value = serializers.IntegerField()
    color = serializers.CharField()
    icon = serializers.CharField()


class TagsSelectOptionsResponseSerializer(serializers.Serializer):
    options = TagSelectOptionSerializer(many=True)


class TagsGroupsResponseSerializer(serializers.Serializer):
    groups = TagGroupSerializer(many=True)


class RenameTagSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=80)


class RenameTagResponseSerializer(serializers.Serializer):
    tag = TagSerializer()
    operationsCount = serializers.IntegerField()


class MoveTagGroupSerializer(serializers.Serializer):
    groupId = serializers.IntegerField(allow_null=True)


class SetTagVisibilitySerializer(serializers.Serializer):
    isVisible = serializers.BooleanField()


class DeleteTagResponseSerializer(serializers.Serializer):
    deleted = serializers.BooleanField()
    id = serializers.IntegerField()


class ValidateTagSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=80, allow_blank=True)
    groupId = serializers.IntegerField(required=False, allow_null=True)
    color = serializers.CharField(max_length=7, required=False, default=DEFAULT_TAG_COLOR)
    icon = serializers.CharField(max_length=50, required=False, default=DEFAULT_TAG_ICON)
    excludeId = serializers.IntegerField(required=False, allow_null=True)


class ValidateTagResponseSerializer(serializers.Serializer):
    ok = serializers.BooleanField()
    fieldErrors = serializers.DictField(child=serializers.CharField())


class TagConflictResponseSerializer(serializers.Serializer):
    code = serializers.CharField()
    message = serializers.CharField()
    fieldErrors = serializers.DictField(
        child=serializers.CharField(),
        required=False,
    )


class TagOptionSerializer(serializers.Serializer):
    title = serializers.CharField()
    value = serializers.CharField()


class TagsMetaResponseSerializer(serializers.Serializer):
    groups = TagGroupSerializer(many=True)
    colors = TagOptionSerializer(many=True)
    icons = TagOptionSerializer(many=True)


def serializer_errors_to_field_errors(errors) -> dict[str, str]:
    field_errors = {}

    for field_name, field_errors_value in errors.items():
        if isinstance(field_errors_value, list):
            field_errors[field_name] = str(field_errors_value[0])
        else:
            field_errors[field_name] = str(field_errors_value)

    return field_errors


def validate_tag_form(*, user, data: dict) -> dict[str, str]:
    errors = {}
    name = str(data.get("name", "")).strip()
    group_id = data.get("groupId")
    color = str(data.get("color", DEFAULT_TAG_COLOR)).strip()
    icon = str(data.get("icon", DEFAULT_TAG_ICON)).strip()
    exclude_id = data.get("excludeId")

    if not name:
        errors["name"] = "Введите название тега."
    elif tag_duplicate_exists(user=user, name=name, exclude_id=exclude_id):
        errors["name"] = "Тег с таким названием уже существует."

    if group_id not in (None, ""):
        if not get_accessible_tag_groups(user).filter(pk=group_id).exists():
            errors["groupId"] = "Выберите существующую группу тегов."

    if not color.startswith("#") or len(color) != 7:
        errors["color"] = "Цвет должен быть указан в HEX-формате."

    if not icon:
        errors["icon"] = "Выберите иконку тега."

    return errors


def get_tags_meta_payload(user) -> dict:
    return {
        "groups": get_tag_group_payload(user, include_empty_group=True),
        "colors": TAG_COLOR_OPTIONS,
        "icons": TAG_ICON_OPTIONS,
    }


def get_tag_group_payload(user, *, include_empty_group: bool = False) -> list[dict]:
    groups = []

    if include_empty_group:
        groups.append({"id": None, "name": "Без группы"})

    groups.extend(
        {
            "id": group.pk,
            "name": group.name,
        }
        for group in get_accessible_tag_groups(user).order_by("is_system", "name", "id")
    )

    return groups
