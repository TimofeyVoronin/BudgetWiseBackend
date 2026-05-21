from __future__ import annotations

from decimal import Decimal

from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.exceptions import ErrorDetail

from apps.finance.models import (
    Account,
    Category,
    Tag,
    TransactionTemplate,
    TransactionTemplateIconTone,
    TransactionTemplateStatus,
    TransactionType,
)
from apps.finance.tags import get_accessible_tags
from apps.finance.transaction_serializers import TransactionSerializer, TransactionTagSerializer
from apps.finance.transaction_templates import (
    MAX_TEMPLATE_PAGE_SIZE,
    DEFAULT_TEMPLATE_PAGE_SIZE,
    get_transaction_templates_meta_payload,
    transaction_template_duplicate_exists,
)


class TransactionTemplateSerializer(serializers.ModelSerializer):
    amountRub = serializers.DecimalField(
        source="amount",
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
        coerce_to_string=False,
    )
    accountId = serializers.PrimaryKeyRelatedField(
        source="account",
        queryset=Account.objects.none(),
    )
    accountName = serializers.CharField(source="account.name", read_only=True)
    categoryId = serializers.PrimaryKeyRelatedField(
        source="category",
        queryset=Category.objects.none(),
    )
    categoryName = serializers.CharField(source="category.name", read_only=True)
    categoryIcon = serializers.CharField(source="category.icon", read_only=True)
    categoryColor = serializers.CharField(source="category.color", read_only=True)
    tagIds = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        write_only=True,
    )
    tags = TransactionTagSerializer(many=True, read_only=True)
    note = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    status = serializers.ChoiceField(
        choices=TransactionTemplateStatus.choices,
        default=TransactionTemplateStatus.ACTIVE,
        required=False,
    )
    isDefault = serializers.BooleanField(source="is_default", required=False, default=False)
    useCount = serializers.IntegerField(source="use_count", read_only=True)
    lastUsedAt = serializers.DateTimeField(source="last_used_at", read_only=True, allow_null=True)
    icon = serializers.CharField(read_only=True)
    iconTone = serializers.SerializerMethodField(read_only=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)

    class Meta:
        model = TransactionTemplate
        fields = [
            "id",
            "name",
            "kind",
            "amountRub",
            "currency",
            "accountId",
            "accountName",
            "categoryId",
            "categoryName",
            "categoryIcon",
            "categoryColor",
            "tagIds",
            "tags",
            "note",
            "status",
            "isDefault",
            "useCount",
            "lastUsedAt",
            "icon",
            "iconTone",
            "createdAt",
            "updatedAt",
        ]
        read_only_fields = [
            "id",
            "accountName",
            "categoryName",
            "categoryIcon",
            "categoryColor",
            "tags",
            "useCount",
            "lastUsedAt",
            "icon",
            "iconTone",
            "createdAt",
            "updatedAt",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        request = self.context.get("request")

        if request and request.user and request.user.is_authenticated:
            self.fields["accountId"].queryset = Account.objects.filter(
                user=request.user,
                is_active=True,
                is_archived=False,
            )
            self.fields["categoryId"].queryset = Category.objects.filter(
                user=request.user,
                is_active=True,
                is_archived=False,
            )

    def to_internal_value(self, data):
        mutable_data = data.copy()

        alias_map = {
            "amount": "amountRub",
            "amount_rub": "amountRub",
            "account": "accountId",
            "account_id": "accountId",
            "category": "categoryId",
            "category_id": "categoryId",
            "type": "kind",
            "tag_ids": "tagIds",
            "tags": "tagIds",
            "is_default": "isDefault",
            "description": "note",
            "comment": "note",
        }

        for alias, field_name in alias_map.items():
            if alias in mutable_data and field_name not in mutable_data:
                mutable_data[field_name] = mutable_data[alias]

        tag_ids = mutable_data.get("tagIds")

        if isinstance(tag_ids, str):
            mutable_data["tagIds"] = [
                item.strip()
                for item in tag_ids.split(",")
                if item.strip()
            ]

        return super().to_internal_value(mutable_data)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["id"] = instance.pk
        data["accountId"] = instance.account_id
        data["categoryId"] = instance.category_id
        data["amountRub"] = float(instance.amount)
        data["isDefault"] = instance.is_default
        data["useCount"] = instance.use_count
        data["icon"] = instance.icon
        data["iconTone"] = instance.icon_tone
        return data

    @extend_schema_field(OpenApiTypes.STR)
    def get_iconTone(self, obj: TransactionTemplate) -> str:
        return obj.icon_tone

    def validate_name(self, value: str) -> str:
        normalized_value = " ".join(str(value or "").split())

        if not normalized_value:
            raise serializers.ValidationError(
                "Название шаблона не может быть пустым.",
                code="template_name_blank",
            )

        if len(normalized_value) > 120:
            raise serializers.ValidationError(
                "Название шаблона не может быть длиннее 120 символов.",
                code="template_name_too_long",
            )

        return normalized_value

    def validate_currency(self, value: str) -> str:
        normalized_value = str(value or "RUB").strip().upper()

        if normalized_value != "RUB":
            raise serializers.ValidationError(
                "Сейчас поддерживается только валюта RUB.",
                code="template_currency_invalid",
            )

        return normalized_value

    def validate_note(self, value: str | None) -> str:
        normalized_value = str(value or "").strip()

        if len(normalized_value) > 1000:
            raise serializers.ValidationError(
                "Примечание шаблона не может быть длиннее 1000 символов.",
                code="template_note_too_long",
            )

        return normalized_value

    def _validate_tag_ids(self, tag_ids: list[int]) -> list[Tag]:
        request = self.context.get("request")
        unique_tag_ids = list(dict.fromkeys(tag_ids or []))

        if not unique_tag_ids:
            return []

        tags_queryset = (
            get_accessible_tags(request.user)
            .filter(pk__in=unique_tag_ids, is_visible=True)
            .order_by("name", "id")
        )
        tags_by_id = {tag.pk: tag for tag in tags_queryset}
        missing_tag_ids = [tag_id for tag_id in unique_tag_ids if tag_id not in tags_by_id]

        if missing_tag_ids:
            raise serializers.ValidationError(
                {
                    "tagIds": [
                        "Недоступные, скрытые или несуществующие теги: "
                        + ", ".join(str(tag_id) for tag_id in missing_tag_ids)
                        + "."
                    ]
                }
            )

        return [tags_by_id[tag_id] for tag_id in unique_tag_ids]

    def validate(self, attrs):
        request = self.context.get("request")
        instance = self.instance
        tag_ids = attrs.pop("tagIds", None)
        self._validated_tags = None

        if tag_ids is not None:
            self._validated_tags = self._validate_tag_ids(tag_ids)

        account = attrs.get("account", getattr(instance, "account", None))
        category = attrs.get("category", getattr(instance, "category", None))
        kind = attrs.get("kind", getattr(instance, "kind", None))
        name = attrs.get("name", getattr(instance, "name", ""))
        status = attrs.get("status", getattr(instance, "status", TransactionTemplateStatus.ACTIVE))

        if account and request and account.user_id != request.user.id:
            raise serializers.ValidationError(
                {"accountId": ["Счёт должен принадлежать текущему пользователю."]}
            )

        if category and request and category.user_id != request.user.id:
            raise serializers.ValidationError(
                {"categoryId": ["Категория должна принадлежать текущему пользователю."]}
            )

        if category and kind and category.type != kind:
            raise serializers.ValidationError(
                {"categoryId": ["Тип категории должен совпадать с типом шаблона."]}
            )

        if account and (account.is_archived or not account.is_active):
            raise serializers.ValidationError(
                {"accountId": ["Для шаблона можно выбрать только активный счёт."]}
            )

        if category and (category.is_archived or not category.is_active):
            raise serializers.ValidationError(
                {"categoryId": ["Для шаблона можно выбрать только активную категорию."]}
            )

        if request and status == TransactionTemplateStatus.ACTIVE and name:
            exclude_id = instance.pk if instance else None

            if transaction_template_duplicate_exists(
                user=request.user,
                name=name,
                exclude_id=exclude_id,
            ):
                raise serializers.ValidationError(
                    {
                        "name": [
                            ErrorDetail(
                                "Активный шаблон с таким названием уже существует.",
                                code="duplicate_template_name",
                            )
                        ]
                    }
                )

        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        tags = getattr(self, "_validated_tags", None)
        validated_data["user"] = request.user
        template = super().create(validated_data)

        if tags is not None:
            template.tags.set(tags)

        return template

    def update(self, instance, validated_data):
        tags = getattr(self, "_validated_tags", None)
        template = super().update(instance, validated_data)

        if tags is not None:
            template.tags.set(tags)

        return template


class TransactionTemplateSummarySerializer(serializers.Serializer):
    totalCount = serializers.IntegerField()
    frequentCount = serializers.IntegerField()
    lastUsedLabel = serializers.CharField()


class TransactionTemplatePaginationSerializer(serializers.Serializer):
    page = serializers.IntegerField()
    perPage = serializers.IntegerField()
    totalItems = serializers.IntegerField()
    totalPages = serializers.IntegerField()


class TransactionTemplateListResponseSerializer(serializers.Serializer):
    items = TransactionTemplateSerializer(many=True)
    summary = TransactionTemplateSummarySerializer()
    pagination = TransactionTemplatePaginationSerializer()


class TransactionTemplateDeleteResponseSerializer(serializers.Serializer):
    deleted = serializers.BooleanField()
    id = serializers.IntegerField()


class TransactionTemplateActionResponseSerializer(serializers.Serializer):
    template = TransactionTemplateSerializer()


class TransactionTemplateApplyDraftSerializer(serializers.Serializer):
    templateId = serializers.IntegerField()
    templateName = serializers.CharField()
    kind = serializers.ChoiceField(choices=TransactionType.choices)
    amountRub = serializers.FloatField()
    currency = serializers.CharField()
    categoryId = serializers.IntegerField()
    categoryName = serializers.CharField()
    categoryIcon = serializers.CharField()
    categoryColor = serializers.CharField()
    accountId = serializers.IntegerField()
    accountName = serializers.CharField()
    tagIds = serializers.ListField(child=serializers.IntegerField())
    tags = TransactionTagSerializer(many=True)
    note = serializers.CharField(allow_blank=True)
    description = serializers.CharField(allow_blank=True)
    operationDate = serializers.DateField()


class TransactionTemplateApplySerializer(serializers.Serializer):
    operationDate = serializers.DateField(required=False)
    amountRub = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
        required=False,
    )
    accountId = serializers.PrimaryKeyRelatedField(
        queryset=Account.objects.none(),
        required=False,
    )
    categoryId = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.none(),
        required=False,
    )
    tagIds = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
    )
    note = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")

        if request and request.user and request.user.is_authenticated:
            self.fields["accountId"].queryset = Account.objects.filter(
                user=request.user,
                is_active=True,
                is_archived=False,
            )
            self.fields["categoryId"].queryset = Category.objects.filter(
                user=request.user,
                is_active=True,
                is_archived=False,
            )

    def to_internal_value(self, data):
        mutable_data = data.copy()
        alias_map = {
            "operation_date": "operationDate",
            "amount": "amountRub",
            "amount_rub": "amountRub",
            "account": "accountId",
            "account_id": "accountId",
            "category": "categoryId",
            "category_id": "categoryId",
            "tags": "tagIds",
            "tag_ids": "tagIds",
            "comment": "note",
        }

        for alias, field_name in alias_map.items():
            if alias in mutable_data and field_name not in mutable_data:
                mutable_data[field_name] = mutable_data[alias]

        tag_ids = mutable_data.get("tagIds")
        if isinstance(tag_ids, str):
            mutable_data["tagIds"] = [item.strip() for item in tag_ids.split(",") if item.strip()]

        return super().to_internal_value(mutable_data)

    def validate(self, attrs):
        template: TransactionTemplate = self.context["template"]
        request = self.context["request"]
        account = attrs.get("accountId", template.account)
        category = attrs.get("categoryId", template.category)
        tag_ids = attrs.get("tagIds", None)

        if template.status == TransactionTemplateStatus.ARCHIVED:
            raise serializers.ValidationError(
                {"template": ["Архивный шаблон нельзя применить."]},
                code="template_archived",
            )

        if account.user_id != request.user.id or account.is_archived or not account.is_active:
            raise serializers.ValidationError(
                {"accountId": ["Для операции можно выбрать только активный счёт текущего пользователя."]}
            )

        if category.user_id != request.user.id or category.is_archived or not category.is_active:
            raise serializers.ValidationError(
                {"categoryId": ["Для операции можно выбрать только активную категорию текущего пользователя."]}
            )

        if category.type != template.kind:
            raise serializers.ValidationError(
                {"categoryId": ["Тип категории должен совпадать с типом шаблона."]}
            )

        if tag_ids is not None:
            unique_tag_ids = list(dict.fromkeys(tag_ids))
            tags_queryset = get_accessible_tags(request.user).filter(
                pk__in=unique_tag_ids,
                is_visible=True,
            )
            tags_by_id = {tag.pk: tag for tag in tags_queryset}
            missing_ids = [tag_id for tag_id in unique_tag_ids if tag_id not in tags_by_id]

            if missing_ids:
                raise serializers.ValidationError(
                    {"tagIds": ["Некоторые теги не найдены, скрыты или недоступны."]}
                )

            attrs["_tags"] = [tags_by_id[tag_id] for tag_id in unique_tag_ids]

        return attrs


class TransactionTemplateApplyResponseSerializer(serializers.Serializer):
    template = TransactionTemplateSerializer()
    transaction = TransactionSerializer()


class TransactionTemplateCheckNameResponseSerializer(serializers.Serializer):
    available = serializers.BooleanField()
    message = serializers.CharField(required=False)


class TransactionTemplateValidateSerializer(serializers.Serializer):
    name = serializers.CharField(required=True, allow_blank=True)
    kind = serializers.ChoiceField(choices=TransactionType.choices, required=False)
    amountRub = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    accountId = serializers.IntegerField(required=False)
    categoryId = serializers.IntegerField(required=False)
    tagIds = serializers.ListField(child=serializers.IntegerField(min_value=1), required=False)
    note = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    excludeId = serializers.IntegerField(required=False, allow_null=True)


class TransactionTemplateValidateResponseSerializer(serializers.Serializer):
    ok = serializers.BooleanField()
    fieldErrors = serializers.DictField(child=serializers.CharField())


class TransactionTemplateOptionSerializer(serializers.Serializer):
    title = serializers.CharField()
    value = serializers.IntegerField()
    icon = serializers.CharField(required=False)
    color = serializers.CharField(required=False)
    currency = serializers.CharField(required=False)
    kind = serializers.CharField(required=False)


class TransactionTemplateKindOptionSerializer(serializers.Serializer):
    title = serializers.CharField()
    value = serializers.CharField()


class TransactionTemplateMetaResponseSerializer(serializers.Serializer):
    kinds = TransactionTemplateKindOptionSerializer(many=True)
    statuses = TransactionTemplateKindOptionSerializer(many=True)
    defaultCurrency = serializers.CharField()
    categories = TransactionTemplateOptionSerializer(many=True)
    accounts = TransactionTemplateOptionSerializer(many=True)
    sortOptions = TransactionTemplateKindOptionSerializer(many=True)


def build_apply_draft_payload(template: TransactionTemplate) -> dict:
    return {
        "templateId": template.pk,
        "templateName": template.name,
        "kind": template.kind,
        "amountRub": float(template.amount),
        "currency": template.currency,
        "categoryId": template.category_id,
        "categoryName": template.category.name,
        "categoryIcon": template.category.icon,
        "categoryColor": template.category.color,
        "accountId": template.account_id,
        "accountName": template.account.name,
        "tagIds": list(template.tags.values_list("id", flat=True)),
        "tags": TransactionTagSerializer(template.tags.all(), many=True).data,
        "note": template.note or "",
        "description": template.note or template.name,
        "operationDate": timezone.localdate(),
    }


def serializer_errors_to_field_errors(errors) -> dict[str, str]:
    field_errors = {}

    for field_name, field_errors_value in errors.items():
        field_errors[field_name] = _first_error_message(field_errors_value)

    return field_errors


def _first_error_message(error_value) -> str:
    if isinstance(error_value, dict):
        if not error_value:
            return "Некорректное значение."
        return _first_error_message(error_value[next(iter(error_value))])

    if isinstance(error_value, list):
        if not error_value:
            return "Некорректное значение."
        return _first_error_message(error_value[0])

    return str(error_value)


def validate_transaction_template_form(*, user, data: dict) -> dict[str, str]:
    errors = {}
    serializer_context = {"request": _RequestProxy(user)}
    serializer = TransactionTemplateSerializer(
        data=data,
        context=serializer_context,
    )

    if not serializer.is_valid():
        errors.update(serializer_errors_to_field_errors(serializer.errors))

    exclude_id = data.get("excludeId") or data.get("exclude_id")
    name = data.get("name")

    if name and transaction_template_duplicate_exists(
        user=user,
        name=name,
        exclude_id=exclude_id,
    ):
        errors["name"] = "Активный шаблон с таким названием уже существует."

    return errors


class _RequestProxy:
    def __init__(self, user):
        self.user = user
