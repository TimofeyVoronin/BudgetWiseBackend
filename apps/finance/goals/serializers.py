from decimal import Decimal

from django.utils import timezone
from drf_spectacular.utils import OpenApiTypes, extend_schema_field
from rest_framework import serializers

from apps.finance.currencies.services import (
    get_user_visible_currency_codes,
    validate_user_currency_available,
)
from apps.finance.models import (
    Account,
    Goal,
    GoalCategory,
    GoalContribution,
    GoalPriority,
    GoalStatus,
)


GOAL_CATEGORY_OPTIONS = [
    {
        "title": "Накопления",
        "value": GoalCategory.SAVINGS,
        "icon": "piggy-bank",
    },
    {
        "title": "Жильё",
        "value": GoalCategory.HOUSING,
        "icon": "home",
    },
    {
        "title": "Транспорт",
        "value": GoalCategory.TRANSPORT,
        "icon": "car",
    },
    {
        "title": "Путешествия",
        "value": GoalCategory.TRAVEL,
        "icon": "airplane",
    },
    {
        "title": "Другое",
        "value": GoalCategory.OTHER,
        "icon": "target",
    },
]

GOAL_PRIORITY_OPTIONS = [
    {
        "title": "Высокий",
        "value": GoalPriority.HIGH,
    },
    {
        "title": "Средний",
        "value": GoalPriority.MEDIUM,
    },
    {
        "title": "Низкий",
        "value": GoalPriority.LOW,
    },
]

GOAL_STATUS_OPTIONS = [
    {
        "title": "Активна",
        "value": GoalStatus.ACTIVE,
    },
    {
        "title": "Завершена",
        "value": GoalStatus.COMPLETED,
    },
    {
        "title": "В архиве",
        "value": GoalStatus.ARCHIVED,
    },
    {
        "title": "Отменена",
        "value": GoalStatus.CANCELLED,
    },
]


class GoalSerializer(serializers.ModelSerializer):
    category_label = serializers.CharField(
        source="get_category_display",
        read_only=True,
    )
    priority_label = serializers.CharField(
        source="get_priority_display",
        read_only=True,
    )
    status_label = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )
    account_name = serializers.CharField(
        source="account.name",
        read_only=True,
    )
    percent = serializers.SerializerMethodField(read_only=True)
    topups_count = serializers.SerializerMethodField(read_only=True)

    categoryKey = serializers.SerializerMethodField(read_only=True)
    categoryLabel = serializers.SerializerMethodField(read_only=True)
    priorityLabel = serializers.SerializerMethodField(read_only=True)
    statusLabel = serializers.SerializerMethodField(read_only=True)
    targetRub = serializers.SerializerMethodField(read_only=True)
    currentRub = serializers.SerializerMethodField(read_only=True)
    accountId = serializers.SerializerMethodField(read_only=True)
    accountName = serializers.SerializerMethodField(read_only=True)
    topupsCount = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Goal
        fields = [
            "id",
            "name",
            "account",
            "account_name",
            "accountId",
            "accountName",
            "category",
            "category_label",
            "categoryKey",
            "categoryLabel",
            "priority",
            "priority_label",
            "priorityLabel",
            "status",
            "status_label",
            "statusLabel",
            "target_amount",
            "targetRub",
            "current_amount",
            "currentRub",
            "percent",
            "deadline",
            "icon",
            "color",
            "topups_count",
            "topupsCount",
            "comment",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "account_name",
            "accountId",
            "accountName",
            "category_label",
            "categoryKey",
            "categoryLabel",
            "priority_label",
            "priorityLabel",
            "status_label",
            "statusLabel",
            "current_amount",
            "currentRub",
            "percent",
            "topups_count",
            "topupsCount",
            "created_at",
            "updated_at",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        request = self.context.get("request")

        if request and request.user.is_authenticated:
            self.fields["account"].queryset = Account.objects.filter(
                user=request.user,
                is_active=True,
                is_archived=False,
                currency__in=get_user_visible_currency_codes(request.user),
            )
        else:
            self.fields["account"].queryset = Account.objects.none()

    def to_internal_value(self, data):
        mutable_data = data.copy()

        aliases = {
            "accountId": "account",
            "categoryKey": "category",
            "targetRub": "target_amount",
        }

        for alias, field_name in aliases.items():
            if alias in mutable_data and field_name not in mutable_data:
                mutable_data[field_name] = mutable_data[alias]

        for field_name in ["name", "comment", "icon", "color"]:
            value = mutable_data.get(field_name)

            if isinstance(value, str):
                mutable_data[field_name] = value.strip()

        return super().to_internal_value(mutable_data)

    @extend_schema_field(OpenApiTypes.NUMBER)
    def get_percent(self, obj) -> str:
        return self._format_decimal(obj.progress_percent)

    @extend_schema_field(OpenApiTypes.INT)
    def get_topups_count(self, obj) -> int:
        return getattr(obj, "topups_count", obj.contributions.count())

    @extend_schema_field(OpenApiTypes.STR)
    def get_categoryKey(self, obj) -> str:
        return obj.category

    @extend_schema_field(OpenApiTypes.STR)
    def get_categoryLabel(self, obj) -> str:
        return obj.get_category_display()

    @extend_schema_field(OpenApiTypes.STR)
    def get_priorityLabel(self, obj) -> str:
        return obj.get_priority_display()

    @extend_schema_field(OpenApiTypes.STR)
    def get_statusLabel(self, obj) -> str:
        return obj.get_status_display()

    @extend_schema_field(OpenApiTypes.STR)
    def get_targetRub(self, obj) -> str:
        return self._format_decimal(obj.target_amount)

    @extend_schema_field(OpenApiTypes.STR)
    def get_currentRub(self, obj) -> str:
        return self._format_decimal(obj.current_amount)

    @extend_schema_field(OpenApiTypes.INT)
    def get_accountId(self, obj) -> int | None:
        return obj.account_id

    @extend_schema_field(OpenApiTypes.STR)
    def get_accountName(self, obj) -> str:
        if obj.account_id and obj.account:
            return obj.account.name

        return ""

    @extend_schema_field(OpenApiTypes.INT)
    def get_topupsCount(self, obj) -> int:
        return self.get_topups_count(obj)

    def validate_name(self, value: str) -> str:
        name = value.strip()

        if not name:
            raise serializers.ValidationError(
                "Название цели не может быть пустым."
            )

        return name

    def validate_account(self, account: Account | None) -> Account | None:
        request = self.context.get("request")

        if account is None:
            return account

        if request and account.user_id != request.user.id:
            raise serializers.ValidationError(
                "Счёт должен принадлежать текущему пользователю."
            )

        validate_user_currency_available(
            request.user,
            account.currency,
            field_name="account",
            require_visible=True,
        )

        if not account.is_active:
            raise serializers.ValidationError(
                "Нельзя привязать цель к неактивному счёту."
            )

        if account.is_archived:
            raise serializers.ValidationError(
                "Нельзя привязать цель к архивному счёту."
            )

        return account

    def validate(self, attrs):
        request = self.context.get("request")
        name = attrs.get("name", getattr(self.instance, "name", None))

        if self._has_direct_current_amount_input():
            raise serializers.ValidationError(
                {
                    "current_amount": (
                        "Накопленную сумму нельзя изменять напрямую. "
                        "Используйте endpoint пополнения цели."
                    )
                }
            )

        if request and name:
            duplicate_queryset = Goal.objects.filter(
                user=request.user,
                name__iexact=name,
            )

            if self.instance is not None:
                duplicate_queryset = duplicate_queryset.exclude(pk=self.instance.pk)

            if duplicate_queryset.exists():
                raise serializers.ValidationError(
                    {
                        "name": "Цель с таким названием уже существует."
                    }
                )

        target_amount = attrs.get(
            "target_amount",
            getattr(self.instance, "target_amount", None),
        )
        current_amount = getattr(
            self.instance,
            "current_amount",
            Decimal("0.00"),
        )

        if target_amount is not None and target_amount < current_amount:
            raise serializers.ValidationError(
                {
                    "target_amount": (
                        "Целевая сумма не может быть меньше уже накопленной суммы."
                    )
                }
            )

        status_value = attrs.get(
            "status",
            getattr(self.instance, "status", GoalStatus.ACTIVE),
        )
        deadline = attrs.get(
            "deadline",
            getattr(self.instance, "deadline", None),
        )

        if (
            status_value == GoalStatus.ACTIVE
            and deadline is not None
            and deadline < timezone.localdate()
        ):
            raise serializers.ValidationError(
                {
                    "deadline": (
                        "Срок активной цели не может быть раньше текущей даты."
                    )
                }
            )

        return attrs

    def _has_direct_current_amount_input(self) -> bool:
        initial_data = getattr(self, "initial_data", {}) or {}

        return any(
            field_name in initial_data
            for field_name in (
                "current_amount",
                "currentRub",
                "current_rub",
            )
        )

    def create(self, validated_data):
        request = self.context["request"]
        validated_data["user"] = request.user

        return super().create(validated_data)

    def _format_decimal(self, value: Decimal) -> str:
        return str(value.quantize(Decimal("0.01")))


class GoalSummarySerializer(serializers.Serializer):
    total_current = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
    )
    total_target = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
    )
    active_count = serializers.IntegerField()
    completed_count = serializers.IntegerField()

    totalCurrentRub = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
    )
    totalTargetRub = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
    )


class GoalCategoryOptionSerializer(serializers.Serializer):
    title = serializers.CharField()
    value = serializers.CharField()
    icon = serializers.CharField()


class GoalPriorityOptionSerializer(serializers.Serializer):
    title = serializers.CharField()
    value = serializers.CharField()


class GoalStatusOptionSerializer(serializers.Serializer):
    title = serializers.CharField()
    value = serializers.CharField()


class GoalMetaSerializer(serializers.Serializer):
    categories = GoalCategoryOptionSerializer(many=True)
    priorities = GoalPriorityOptionSerializer(many=True)
    statuses = GoalStatusOptionSerializer(many=True)


class GoalContributionSerializer(serializers.ModelSerializer):
    date = serializers.DateField(
        source="contribution_date",
        read_only=True,
    )
    amountRub = serializers.SerializerMethodField(read_only=True)
    accountName = serializers.SerializerMethodField(read_only=True)
    operationId = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = GoalContribution
        fields = [
            "id",
            "date",
            "amount",
            "amountRub",
            "account",
            "account_name",
            "accountName",
            "transaction",
            "operationId",
            "comment",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    @extend_schema_field(OpenApiTypes.STR)
    def get_amountRub(self, obj) -> str:
        return str(obj.amount.quantize(Decimal("0.01")))

    @extend_schema_field(OpenApiTypes.STR)
    def get_accountName(self, obj) -> str:
        if obj.account_id and obj.account:
            return obj.account.name

        return obj.account_name

    @extend_schema_field(OpenApiTypes.INT)
    def get_operationId(self, obj) -> int | None:
        return obj.transaction_id


class GoalDetailSerializer(serializers.Serializer):
    goal = GoalSerializer()
    history = GoalContributionSerializer(many=True)


class GoalTopupCreateSerializer(serializers.Serializer):
    amountRub = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )
    date = serializers.DateField()
    accountId = serializers.PrimaryKeyRelatedField(
        queryset=Account.objects.none(),
    )
    comment = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=True,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        request = self.context.get("request")

        if request and request.user.is_authenticated:
            self.fields["accountId"].queryset = Account.objects.filter(
                user=request.user,
                is_active=True,
                is_archived=False,
                currency__in=get_user_visible_currency_codes(request.user),
            )

    def to_internal_value(self, data):
        mutable_data = data.copy()

        aliases = {
            "amount": "amountRub",
            "amount_rub": "amountRub",
            "contribution_date": "date",
            "account": "accountId",
            "account_id": "accountId",
        }

        for alias, field_name in aliases.items():
            if alias in mutable_data and field_name not in mutable_data:
                mutable_data[field_name] = mutable_data[alias]

        return super().to_internal_value(mutable_data)

    def validate_date(self, value):
        if value > timezone.localdate():
            raise serializers.ValidationError(
                "Дата пополнения не может быть позже текущей даты."
            )

        return value

    def validate(self, attrs):
        goal = self.context.get("goal")
        amount = attrs.get("amountRub")
        account = attrs.get("accountId")

        if (
            goal is not None
            and goal.status == GoalStatus.ACTIVE
            and amount is not None
        ):
            remaining_amount = goal.target_amount - goal.current_amount

            if remaining_amount <= Decimal("0.00"):
                raise serializers.ValidationError(
                    {
                        "amountRub": "Цель уже достигнута."
                    }
                )

            if amount > remaining_amount:
                raise serializers.ValidationError(
                    {
                        "amountRub": (
                            "Сумма пополнения не может быть больше "
                            "оставшейся суммы по цели."
                        )
                    }
                )

        if account is not None and amount is not None:
            validate_user_currency_available(
                self.context["request"].user,
                account.currency,
                field_name="accountId",
                require_visible=True,
            )

            if account.available_balance < amount:
                raise serializers.ValidationError(
                    {
                        "accountId": (
                            "На счёте недостаточно доступного баланса "
                            "для пополнения цели."
                        )
                    }
                )

        return attrs
