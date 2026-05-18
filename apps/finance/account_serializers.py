from decimal import Decimal

from drf_spectacular.utils import OpenApiTypes, extend_schema_field
from rest_framework import serializers

from apps.finance.models import Account, AccountType


ACCOUNT_TYPE_OPTIONS = [
    {
        "title": "Банковская карта",
        "value": AccountType.CARD,
        "icon": "card",
    },
    {
        "title": "Дебетовая карта",
        "value": AccountType.DEBIT,
        "icon": "card",
    },
    {
        "title": "Накопительный",
        "value": AccountType.SAVINGS,
        "icon": "bank",
    },
    {
        "title": "Наличные",
        "value": AccountType.CASH,
        "icon": "cash",
    },
    {
        "title": "Кредитный",
        "value": AccountType.CREDIT,
        "icon": "credit-card",
    },
    {
        "title": "Другое",
        "value": AccountType.OTHER,
        "icon": "wallet",
    },
]

ACCOUNT_BANK_OPTIONS = [
    {
        "title": "Сбербанк",
        "value": "Сбербанк",
    },
    {
        "title": "Тинькофф",
        "value": "Тинькофф",
    },
    {
        "title": "ВТБ",
        "value": "ВТБ",
    },
    {
        "title": "Альфа-Банк",
        "value": "Альфа-Банк",
    },
    {
        "title": "Газпромбанк",
        "value": "Газпромбанк",
    },
    {
        "title": "Другой банк",
        "value": "other",
    },
]

ACCOUNT_CURRENCY_OPTIONS = [
    {
        "title": "RUB ₽",
        "value": "RUB",
    },
    {
        "title": "USD $",
        "value": "USD",
    },
    {
        "title": "EUR €",
        "value": "EUR",
    },
]


class AccountSerializer(serializers.ModelSerializer):
    type_label = serializers.CharField(
        source="get_type_display",
        read_only=True,
    )
    status = serializers.SerializerMethodField(read_only=True)
    available_balance = serializers.SerializerMethodField(read_only=True)
    operations_count = serializers.SerializerMethodField(read_only=True)

    typeLabel = serializers.SerializerMethodField(read_only=True)
    bankName = serializers.SerializerMethodField(read_only=True)
    balanceRub = serializers.SerializerMethodField(read_only=True)
    initialBalanceRub = serializers.SerializerMethodField(read_only=True)
    isDefault = serializers.SerializerMethodField(read_only=True)
    operationsCount = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Account
        fields = [
            "id",
            "name",
            "type",
            "type_label",
            "typeLabel",
            "bank_name",
            "bankName",
            "currency",
            "initial_balance",
            "initialBalanceRub",
            "balance",
            "balanceRub",
            "blocked_amount",
            "credit_limit",
            "available_balance",
            "icon",
            "color",
            "status",
            "is_default",
            "isDefault",
            "is_active",
            "is_archived",
            "operations_count",
            "operationsCount",
            "comment",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "type_label",
            "typeLabel",
            "bankName",
            "balance",
            "balanceRub",
            "initialBalanceRub",
            "available_balance",
            "status",
            "isDefault",
            "operations_count",
            "operationsCount",
            "created_at",
            "updated_at",
        ]

    def to_internal_value(self, data):
        mutable_data = data.copy()

        aliases = {
            "bankName": "bank_name",
            "initialBalanceRub": "initial_balance",
            "isDefault": "is_default",
        }

        for alias, field_name in aliases.items():
            if alias in mutable_data and field_name not in mutable_data:
                mutable_data[field_name] = mutable_data[alias]

        return super().to_internal_value(mutable_data)

    @extend_schema_field(OpenApiTypes.STR)
    def get_status(self, obj) -> str:
        return obj.status

    @extend_schema_field(OpenApiTypes.STR)
    def get_available_balance(self, obj) -> str:
        return self._format_money(obj.available_balance)

    @extend_schema_field(OpenApiTypes.INT)
    def get_operations_count(self, obj) -> int:
        return getattr(obj, "operations_count", obj.transactions.count())

    @extend_schema_field(OpenApiTypes.STR)
    def get_typeLabel(self, obj) -> str:
        return obj.get_type_display()

    @extend_schema_field(OpenApiTypes.STR)
    def get_bankName(self, obj) -> str:
        return obj.bank_name

    @extend_schema_field(OpenApiTypes.STR)
    def get_balanceRub(self, obj) -> str:
        return self._format_money(obj.balance)

    @extend_schema_field(OpenApiTypes.STR)
    def get_initialBalanceRub(self, obj) -> str:
        return self._format_money(obj.initial_balance)

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_isDefault(self, obj) -> bool:
        return obj.is_default

    @extend_schema_field(OpenApiTypes.INT)
    def get_operationsCount(self, obj) -> int:
        return self.get_operations_count(obj)

    def validate_currency(self, value: str) -> str:
        return value.upper()

    def validate(self, attrs):
        account_type = attrs.get("type", getattr(self.instance, "type", None))
        bank_name = attrs.get("bank_name", getattr(self.instance, "bank_name", ""))

        if account_type in {AccountType.CARD, AccountType.DEBIT, AccountType.CREDIT}:
            if bank_name is None:
                attrs["bank_name"] = ""

        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        validated_data["user"] = request.user

        initial_balance = validated_data.get("initial_balance", Decimal("0.00"))
        validated_data["balance"] = initial_balance

        is_default = validated_data.get("is_default", False)

        if not Account.objects.filter(user=request.user).exists():
            validated_data["is_default"] = True
            is_default = True

        if is_default:
            Account.objects.filter(user=request.user, is_default=True).update(
                is_default=False,
            )

        return super().create(validated_data)

    def update(self, instance, validated_data):
        request = self.context["request"]

        if validated_data.get("is_default") is True:
            Account.objects.filter(
                user=request.user,
                is_default=True,
            ).exclude(pk=instance.pk).update(is_default=False)

        if validated_data.get("is_archived") is True:
            validated_data["is_active"] = False
            validated_data["is_default"] = False

        if validated_data.get("is_archived") is False and "is_active" not in validated_data:
            validated_data["is_active"] = True

        return super().update(instance, validated_data)

    def _format_money(self, value: Decimal) -> str:
        return str(value.quantize(Decimal("0.01")))


class AccountArchiveSerializer(serializers.Serializer):
    archived = serializers.BooleanField(
        required=False,
        default=True,
        help_text="true - отправить счёт в архив, false - восстановить из архива.",
    )


class AccountSummarySerializer(serializers.Serializer):
    total_balance = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
    )
    active_count = serializers.IntegerField()
    archived_count = serializers.IntegerField()
    currency = serializers.CharField()

    totalBalanceRub = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
    )


class AccountHistoryRowSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    date = serializers.DateField()
    description = serializers.CharField()
    category_name = serializers.CharField()
    amount = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
    )
    signed_amount = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
    )
    type = serializers.CharField()


class AccountTypeOptionSerializer(serializers.Serializer):
    title = serializers.CharField()
    value = serializers.CharField()
    icon = serializers.CharField()


class AccountBankOptionSerializer(serializers.Serializer):
    title = serializers.CharField()
    value = serializers.CharField()


class AccountCurrencyOptionSerializer(serializers.Serializer):
    title = serializers.CharField()
    value = serializers.CharField()


class AccountMetaSerializer(serializers.Serializer):
    types = AccountTypeOptionSerializer(many=True)
    banks = AccountBankOptionSerializer(many=True)
    currencies = AccountCurrencyOptionSerializer(many=True)
