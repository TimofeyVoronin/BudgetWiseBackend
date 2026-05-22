from decimal import Decimal

from drf_spectacular.utils import OpenApiTypes, extend_schema_field
from rest_framework import serializers

from apps.finance.currencies import validate_user_currency_available
from apps.finance.models import (
    Account,
    Category,
    Tag,
    Transaction,
    TransactionType,
)
from apps.finance.tags import get_accessible_tags


class TransactionTagSerializer(serializers.ModelSerializer):
    groupId = serializers.IntegerField(source="group_id", read_only=True, allow_null=True)
    groupName = serializers.SerializerMethodField(read_only=True)
    isVisible = serializers.BooleanField(source="is_visible", read_only=True)

    class Meta:
        model = Tag
        fields = [
            "id",
            "name",
            "groupId",
            "groupName",
            "color",
            "icon",
            "isVisible",
        ]

    @extend_schema_field(OpenApiTypes.STR)
    def get_groupName(self, obj: Tag) -> str:
        return obj.group.name if obj.group_id else "Без группы"


class TransactionSerializer(serializers.ModelSerializer):
    date = serializers.DateField(
        source="operation_date",
        read_only=True,
    )
    kind = serializers.CharField(
        source="type",
        read_only=True,
    )
    amount_abs = serializers.SerializerMethodField(read_only=True)
    signed_amount = serializers.SerializerMethodField(read_only=True)
    category_name = serializers.CharField(
        source="category.name",
        read_only=True,
    )
    category_icon = serializers.CharField(
        source="category.icon",
        read_only=True,
    )
    category_color = serializers.CharField(
        source="category.color",
        read_only=True,
    )
    account_name = serializers.CharField(
        source="account.name",
        read_only=True,
    )
    account_currency = serializers.CharField(
        source="account.currency",
        read_only=True,
    )
    tagIds = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        write_only=True,
    )
    tags = TransactionTagSerializer(many=True, read_only=True)

    class Meta:
        model = Transaction
        fields = [
            "id",
            "account",
            "account_name",
            "account_currency",
            "category",
            "category_name",
            "category_icon",
            "category_color",
            "type",
            "kind",
            "amount",
            "amount_abs",
            "signed_amount",
            "description",
            "operation_date",
            "date",
            "created_at",
            "updated_at",
            "tagIds",
            "tags",
        ]
        read_only_fields = [
            "id",
            "account_name",
            "account_currency",
            "category_name",
            "category_icon",
            "category_color",
            "kind",
            "amount_abs",
            "signed_amount",
            "date",
            "created_at",
            "updated_at",
            "tags",
        ]

    def to_internal_value(self, data):
        mutable_data = data.copy()

        alias_map = {
            "tag_ids": "tagIds",
            "tags": "tagIds",
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

    def _validate_tag_ids(self, tag_ids: list[int]) -> list[Tag]:
        request = self.context.get("request")

        if not request or not request.user or not request.user.is_authenticated:
            raise serializers.ValidationError(
                {
                    "tagIds": "Пользователь должен быть авторизован для выбора тегов."
                }
            )

        unique_tag_ids = list(dict.fromkeys(tag_ids))

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
                        (
                            "Недоступные, скрытые или несуществующие теги: "
                            + ", ".join(str(tag_id) for tag_id in missing_tag_ids)
                            + "."
                        )
                    ]
                }
            )

        return [tags_by_id[tag_id] for tag_id in unique_tag_ids]

    @extend_schema_field(OpenApiTypes.STR)
    def get_amount_abs(self, obj) -> str:
        return str(abs(obj.amount).quantize(Decimal("0.01")))

    @extend_schema_field(OpenApiTypes.STR)
    def get_signed_amount(self, obj) -> str:
        amount = abs(obj.amount)

        if obj.type == TransactionType.EXPENSE:
            amount = -amount

        return str(amount.quantize(Decimal("0.01")))

    def validate_account(self, account: Account) -> Account:
        request = self.context.get("request")

        if request and account.user_id != request.user.id:
            raise serializers.ValidationError(
                "Счёт должен принадлежать текущему пользователю."
            )

        return account

    def validate_category(self, category: Category) -> Category:
        request = self.context.get("request")

        if request and category.user_id != request.user.id:
            raise serializers.ValidationError(
                "Категория должна принадлежать текущему пользователю."
            )

        return category

    def validate(self, attrs):
        request = self.context.get("request")
        tag_ids = attrs.pop("tagIds", None)
        self._validated_tags = None

        if tag_ids is not None:
            self._validated_tags = self._validate_tag_ids(tag_ids)

        account = attrs.get("account", getattr(self.instance, "account", None))
        category = attrs.get("category", getattr(self.instance, "category", None))
        transaction_type = attrs.get("type", getattr(self.instance, "type", None))

        should_validate_account_status = (
            not self.instance or "account" in attrs
        )

        if request and should_validate_account_status and account:
            validate_user_currency_available(
                request.user,
                account.currency,
                field_name="account",
                require_visible=True,
            )

        if should_validate_account_status and account and not account.is_active:
            raise serializers.ValidationError(
                {
                    "account": "Нельзя использовать неактивный счёт."
                }
            )

        if should_validate_account_status and account and account.is_archived:
            raise serializers.ValidationError(
                {
                    "account": "Нельзя использовать архивный счёт."
                }
            )

        should_validate_category_status = (
            not self.instance or "category" in attrs
        )

        if should_validate_category_status and category and not category.is_active:
            raise serializers.ValidationError(
                {
                    "category": "Нельзя использовать неактивную категорию."
                }
            )

        if should_validate_category_status and category and category.is_archived:
            raise serializers.ValidationError(
                {
                    "category": "Нельзя использовать архивную категорию."
                }
            )

        if category and transaction_type and category.type != transaction_type:
            raise serializers.ValidationError(
                {
                    "category": "Тип категории должен совпадать с типом операции."
                }
            )

        if account and category and account.user_id != category.user_id:
            raise serializers.ValidationError(
                {
                    "category": "Счёт и категория должны принадлежать одному пользователю."
                }
            )

        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        tags = getattr(self, "_validated_tags", None)

        validated_data["user"] = request.user
        transaction = super().create(validated_data)

        if tags is not None:
            transaction.tags.set(tags)

        return transaction

    def update(self, instance, validated_data):
        tags = getattr(self, "_validated_tags", None)
        transaction = super().update(instance, validated_data)

        if tags is not None:
            transaction.tags.set(tags)

        return transaction
