from __future__ import annotations

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.exceptions import ErrorDetail

from apps.finance.models import Tag, TagGroup
from apps.finance.tags import (
    DEFAULT_TAG_COLOR,
    DEFAULT_TAG_ICON,
    MAX_TAG_DESCRIPTION_LENGTH,
    MAX_TAG_ICON_LENGTH,
    MAX_TAG_NAME_LENGTH,
    TAG_COLOR_OPTIONS,
    TAG_ICON_OPTIONS,
    is_valid_tag_color,
    is_valid_tag_icon,
    is_valid_tag_name,
    normalize_tag_color,
    normalize_tag_name,
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
        normalized_value = normalize_tag_name(value)

        if not normalized_value:
            raise serializers.ValidationError(
                "Название тега не может быть пустым.",
                code="tag_name_blank",
            )

        if len(normalized_value) > MAX_TAG_NAME_LENGTH:
            raise serializers.ValidationError(
                f"Название тега не может быть длиннее {MAX_TAG_NAME_LENGTH} символов.",
                code="tag_name_too_long",
            )

        if not is_valid_tag_name(normalized_value):
            raise serializers.ValidationError(
                (
                    "Название тега может содержать буквы, цифры, пробелы "
                    "и символы - _ . , & ( ) + №."
                ),
                code="tag_name_invalid_chars",
            )

        return normalized_value

    def validate_color(self, value: str) -> str:
        normalized_value = normalize_tag_color(value)

        if not is_valid_tag_color(normalized_value):
            raise serializers.ValidationError(
                "Цвет должен быть указан в HEX-формате, например #66BB6A.",
                code="tag_color_invalid",
            )

        return normalized_value

    def validate_icon(self, value: str) -> str:
        normalized_value = str(value or "").strip()

        if not normalized_value:
            raise serializers.ValidationError(
                "Иконка тега не может быть пустой.",
                code="tag_icon_blank",
            )

        if len(normalized_value) > MAX_TAG_ICON_LENGTH:
            raise serializers.ValidationError(
                f"Иконка тега не может быть длиннее {MAX_TAG_ICON_LENGTH} символов.",
                code="tag_icon_too_long",
            )

        if not is_valid_tag_icon(normalized_value):
            raise serializers.ValidationError(
                "Выберите иконку из справочника тегов.",
                code="tag_icon_invalid",
            )

        return normalized_value

    def validate_description(self, value: str) -> str:
        normalized_value = str(value or "").strip()

        if len(normalized_value) > MAX_TAG_DESCRIPTION_LENGTH:
            raise serializers.ValidationError(
                f"Описание тега не может быть длиннее {MAX_TAG_DESCRIPTION_LENGTH} символов.",
                code="tag_description_too_long",
            )

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
                            ErrorDetail(
                                "Тег с таким названием уже существует.",
                                code="duplicate_tag_name",
                            )
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
    name = serializers.CharField(max_length=MAX_TAG_NAME_LENGTH)

    def validate_name(self, value: str) -> str:
        normalized_value = normalize_tag_name(value)

        if not normalized_value:
            raise serializers.ValidationError(
                "Название тега не может быть пустым.",
                code="tag_name_blank",
            )

        if not is_valid_tag_name(normalized_value):
            raise serializers.ValidationError(
                (
                    "Название тега может содержать буквы, цифры, пробелы "
                    "и символы - _ . , & ( ) + №."
                ),
                code="tag_name_invalid_chars",
            )

        return normalized_value


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


class DeleteTagConflictResponseSerializer(serializers.Serializer):
    code = serializers.CharField()
    message = serializers.CharField()
    operationsCount = serializers.IntegerField()
    canHide = serializers.BooleanField()


class ValidateTagSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=MAX_TAG_NAME_LENGTH, allow_blank=True)
    groupId = serializers.IntegerField(required=False, allow_null=True)
    color = serializers.CharField(max_length=7, required=False, default=DEFAULT_TAG_COLOR)
    icon = serializers.CharField(max_length=MAX_TAG_ICON_LENGTH, required=False, default=DEFAULT_TAG_ICON)
    excludeId = serializers.IntegerField(required=False, allow_null=True)
    description = serializers.CharField(
        max_length=MAX_TAG_DESCRIPTION_LENGTH,
        required=False,
        allow_blank=True,
    )


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
    operationsCount = serializers.IntegerField(required=False)
    canHide = serializers.BooleanField(required=False)


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
        field_errors[field_name] = _first_error_message(field_errors_value)

    return field_errors


def _first_error_message(error_value) -> str:
    if isinstance(error_value, dict):
        if not error_value:
            return "Некорректное значение."

        first_key = next(iter(error_value))
        return _first_error_message(error_value[first_key])

    if isinstance(error_value, list):
        if not error_value:
            return "Некорректное значение."

        return _first_error_message(error_value[0])

    return str(error_value)


def validate_tag_form(*, user, data: dict) -> dict[str, str]:
    errors = {}
    name = normalize_tag_name(data.get("name", ""))
    group_id = data.get("groupId")
    color = normalize_tag_color(data.get("color", DEFAULT_TAG_COLOR))
    icon = str(data.get("icon", DEFAULT_TAG_ICON)).strip()
    description = str(data.get("description", "")).strip()
    exclude_id = data.get("excludeId")

    if not name:
        errors["name"] = "Введите название тега."
    elif len(name) > MAX_TAG_NAME_LENGTH:
        errors["name"] = f"Название тега не может быть длиннее {MAX_TAG_NAME_LENGTH} символов."
    elif not is_valid_tag_name(name):
        errors["name"] = (
            "Название тега может содержать буквы, цифры, пробелы "
            "и символы - _ . , & ( ) + №."
        )
    elif tag_duplicate_exists(user=user, name=name, exclude_id=exclude_id):
        errors["name"] = "Тег с таким названием уже существует."

    if group_id not in (None, ""):
        if not get_accessible_tag_groups(user).filter(pk=group_id).exists():
            errors["groupId"] = "Выберите существующую группу тегов."

    if not is_valid_tag_color(color):
        errors["color"] = "Цвет должен быть указан в HEX-формате, например #66BB6A."

    if not icon:
        errors["icon"] = "Выберите иконку тега."
    elif len(icon) > MAX_TAG_ICON_LENGTH:
        errors["icon"] = f"Иконка тега не может быть длиннее {MAX_TAG_ICON_LENGTH} символов."
    elif not is_valid_tag_icon(icon):
        errors["icon"] = "Выберите иконку из справочника тегов."

    if len(description) > MAX_TAG_DESCRIPTION_LENGTH:
        errors["description"] = f"Описание тега не может быть длиннее {MAX_TAG_DESCRIPTION_LENGTH} символов."

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
