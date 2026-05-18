from decimal import Decimal

from drf_spectacular.utils import OpenApiTypes, extend_schema_field
from rest_framework import serializers

from apps.finance.models import (
    Account,
    Category,
    Transaction,
    TransactionType,
)


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
        ]

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
        account = attrs.get("account", getattr(self.instance, "account", None))
        category = attrs.get("category", getattr(self.instance, "category", None))
        transaction_type = attrs.get("type", getattr(self.instance, "type", None))

        should_validate_account_status = (
            not self.instance or "account" in attrs
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
        validated_data["user"] = request.user
        return super().create(validated_data)
