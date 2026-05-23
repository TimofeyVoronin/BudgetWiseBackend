from __future__ import annotations

from decimal import Decimal

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.finance.budgets.services import (
    BUDGET_CATEGORY_GROUP_OPTIONS,
    BUDGET_KIND_OPTIONS,
    BUDGET_PERIOD_TYPE_OPTIONS,
    BUDGET_USAGE_STATUS_OPTIONS,
    budget_duplicate_exists,
    decimal_to_number,
    get_budget_usage,
    get_period_label,
    percent_to_number,
)
from apps.finance.currencies.services import (
    build_currency_select_options,
    get_user_default_currency_code,
    validate_user_currency_available,
)
from apps.finance.models import (
    Budget,
    BudgetCategoryGroup,
    BudgetKind,
    BudgetPeriodType,
    BudgetUsageStatus,
    Category,
)


MAX_BUDGET_SEARCH_LENGTH = 100


class BudgetSerializer(serializers.ModelSerializer):
    categoryId = serializers.PrimaryKeyRelatedField(
        source="category",
        queryset=Category.objects.none(),
    )
    categoryName = serializers.CharField(
        source="category.name",
        read_only=True,
    )
    categoryGroup = serializers.ChoiceField(
        source="category_group",
        choices=BudgetCategoryGroup.choices,
        default=BudgetCategoryGroup.MAIN,
        required=False,
    )
    categoryGroupLabel = serializers.CharField(
        source="get_category_group_display",
        read_only=True,
    )
    categoryIcon = serializers.CharField(
        source="category.icon",
        read_only=True,
    )
    categoryColor = serializers.CharField(
        source="category.color",
        read_only=True,
    )
    periodType = serializers.ChoiceField(
        source="period_type",
        choices=BudgetPeriodType.choices,
        default=BudgetPeriodType.MONTH,
        required=False,
    )
    periodTypeLabel = serializers.CharField(
        source="get_period_type_display",
        read_only=True,
    )
    periodLabel = serializers.SerializerMethodField(read_only=True)
    periodStart = serializers.DateField(source="period_start")
    periodEnd = serializers.DateField(source="period_end")
    limitRub = serializers.DecimalField(
        source="amount_limit",
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
        coerce_to_string=False,
    )
    spentRub = serializers.SerializerMethodField(read_only=True)
    currency = serializers.CharField(max_length=3, required=False)
    kind = serializers.ChoiceField(
        choices=BudgetKind.choices,
        default=BudgetKind.EXPENSE,
        required=False,
    )
    kindLabel = serializers.CharField(
        source="get_kind_display",
        read_only=True,
    )
    usageStatus = serializers.SerializerMethodField(read_only=True)
    usageStatusLabel = serializers.SerializerMethodField(read_only=True)
    usagePercent = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Budget
        fields = [
            "id",
            "categoryId",
            "categoryName",
            "categoryGroup",
            "categoryGroupLabel",
            "categoryIcon",
            "categoryColor",
            "periodType",
            "periodTypeLabel",
            "periodLabel",
            "periodStart",
            "periodEnd",
            "limitRub",
            "spentRub",
            "currency",
            "kind",
            "kindLabel",
            "rollover",
            "comment",
            "paused",
            "usageStatus",
            "usageStatusLabel",
            "usagePercent",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "categoryName",
            "categoryGroupLabel",
            "categoryIcon",
            "categoryColor",
            "periodTypeLabel",
            "periodLabel",
            "spentRub",
            "kindLabel",
            "usageStatus",
            "usageStatusLabel",
            "usagePercent",
            "created_at",
            "updated_at",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        request = self.context.get("request")
        category_queryset = Category.objects.none()

        if request and request.user and request.user.is_authenticated:
            category_queryset = Category.objects.filter(
                user=request.user,
                is_active=True,
                is_archived=False,
            )

        self.fields["categoryId"].queryset = category_queryset

    def to_internal_value(self, data):
        mutable_data = data.copy()

        alias_map = {
            "category_id": "categoryId",
            "category": "categoryId",
            "category_group": "categoryGroup",
            "period_type": "periodType",
            "period_start": "periodStart",
            "period_end": "periodEnd",
            "amount_limit": "limitRub",
            "limit_amount": "limitRub",
            "limit": "limitRub",
        }

        for alias, field_name in alias_map.items():
            if alias in mutable_data and field_name not in mutable_data:
                mutable_data[field_name] = mutable_data[alias]

        currency = mutable_data.get("currency")
        if isinstance(currency, str):
            mutable_data["currency"] = currency.strip().upper()

        return super().to_internal_value(mutable_data)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        usage = get_budget_usage(instance)

        data["id"] = instance.pk
        data["categoryId"] = instance.category_id
        data["limitRub"] = decimal_to_number(instance.amount_limit)
        data["spentRub"] = decimal_to_number(usage.spent_amount)
        data["usagePercent"] = percent_to_number(usage.usage_percent)

        return data

    @extend_schema_field(OpenApiTypes.STR)
    def get_periodLabel(self, obj: Budget) -> str:
        return get_period_label(obj)

    @extend_schema_field(OpenApiTypes.NUMBER)
    def get_spentRub(self, obj: Budget) -> float:
        return decimal_to_number(get_budget_usage(obj).spent_amount)

    @extend_schema_field(OpenApiTypes.STR)
    def get_usageStatus(self, obj: Budget) -> str:
        return get_budget_usage(obj).usage_status

    @extend_schema_field(OpenApiTypes.STR)
    def get_usageStatusLabel(self, obj: Budget) -> str:
        usage_status = get_budget_usage(obj).usage_status
        return BudgetUsageStatus(usage_status).label

    @extend_schema_field(OpenApiTypes.NUMBER)
    def get_usagePercent(self, obj: Budget) -> float:
        return percent_to_number(get_budget_usage(obj).usage_percent)

    def validate_category(self, category: Category) -> Category:
        request = self.context.get("request")

        if request and category.user_id != request.user.id:
            raise serializers.ValidationError(
                "Категория должна принадлежать текущему пользователю."
            )

        if not category.is_active:
            raise serializers.ValidationError(
                "Нельзя использовать неактивную категорию."
            )

        if category.is_archived:
            raise serializers.ValidationError(
                "Нельзя использовать архивную категорию."
            )

        return category

    def validate_currency(self, currency: str) -> str:
        request = self.context.get("request")
        normalized_currency = currency.upper()

        if request and request.user and request.user.is_authenticated:
            return validate_user_currency_available(
                request.user,
                normalized_currency,
                field_name=None,
                require_visible=True,
            )

        return normalized_currency

    def validate(self, attrs):
        request = self.context.get("request")
        instance = self.instance

        category = attrs.get("category") or getattr(instance, "category", None)
        kind = attrs.get("kind") or getattr(instance, "kind", BudgetKind.EXPENSE)
        period_type = attrs.get("period_type") or getattr(
            instance,
            "period_type",
            BudgetPeriodType.MONTH,
        )
        period_start = attrs.get("period_start") or getattr(instance, "period_start", None)
        period_end = attrs.get("period_end") or getattr(instance, "period_end", None)

        if request and instance is None and not attrs.get("currency"):
            attrs["currency"] = get_user_default_currency_code(request.user)

        if category and kind and category.type != kind:
            raise serializers.ValidationError(
                {
                    "categoryId": [
                        "Тип категории должен совпадать с типом бюджета."
                    ]
                }
            )

        if period_start and period_end and period_end < period_start:
            raise serializers.ValidationError(
                {
                    "periodEnd": [
                        "Дата окончания периода не может быть раньше даты начала."
                    ]
                }
            )

        if request and category and period_start and period_end:
            exclude_id = instance.pk if instance else None

            if budget_duplicate_exists(
                user=request.user,
                category=category,
                kind=kind,
                period_type=period_type,
                period_start=period_start,
                period_end=period_end,
                exclude_id=exclude_id,
            ):
                raise serializers.ValidationError(
                    {
                        "general": [
                            "Бюджет для выбранной категории, типа и периода уже существует."
                        ]
                    }
                )

        return attrs

    def create(self, validated_data):
        request = self.context.get("request")

        if request and request.user and request.user.is_authenticated:
            validated_data["user"] = request.user

        return super().create(validated_data)


class BudgetDetailStatsSerializer(serializers.Serializer):
    limitRub = serializers.FloatField()
    spentRub = serializers.FloatField()
    remainingRub = serializers.FloatField()
    avgDailyRub = serializers.FloatField()
    forecastRub = serializers.FloatField()
    forecastWithinLimit = serializers.BooleanField()


class BudgetChartPointSerializer(serializers.Serializer):
    label = serializers.CharField()
    factPct = serializers.FloatField()
    forecastPct = serializers.FloatField()


class BudgetOperationRowSerializer(serializers.Serializer):
    id = serializers.CharField()
    title = serializers.CharField()
    subtitle = serializers.CharField()
    dateLabel = serializers.CharField()
    amountRub = serializers.FloatField()
    icon = serializers.CharField()


class BudgetDetailSerializer(serializers.Serializer):
    budget = BudgetSerializer()
    stats = BudgetDetailStatsSerializer()
    chart = BudgetChartPointSerializer(many=True)
    operations = BudgetOperationRowSerializer(many=True)


class BudgetListSummarySerializer(serializers.Serializer):
    totalCount = serializers.IntegerField()
    normalCount = serializers.IntegerField()
    attentionCount = serializers.IntegerField()


class BudgetListPaginationSerializer(serializers.Serializer):
    page = serializers.IntegerField()
    perPage = serializers.IntegerField()
    totalItems = serializers.IntegerField()
    totalPages = serializers.IntegerField()


class BudgetListResponseSerializer(serializers.Serializer):
    items = BudgetSerializer(many=True)
    summary = BudgetListSummarySerializer()
    pagination = BudgetListPaginationSerializer()


class CheckBudgetDuplicateSerializer(serializers.Serializer):
    excludeId = serializers.IntegerField(required=False, allow_null=True)
    categoryId = serializers.IntegerField(required=False)
    categoryName = serializers.CharField(max_length=100, required=False)
    periodType = serializers.ChoiceField(choices=BudgetPeriodType.choices)
    periodStart = serializers.DateField()
    periodEnd = serializers.DateField(required=False)
    kind = serializers.ChoiceField(choices=BudgetKind.choices)


class CheckBudgetDuplicateResponseSerializer(serializers.Serializer):
    isDuplicate = serializers.BooleanField()
    message = serializers.CharField(required=False, allow_blank=True)


class ValidateBudgetFormSerializer(serializers.Serializer):
    categoryName = serializers.CharField(max_length=100, required=False, allow_blank=True)
    categoryId = serializers.IntegerField(required=False)
    limitRub = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
        coerce_to_string=False,
    )
    periodStart = serializers.DateField()
    periodEnd = serializers.DateField()


class ValidateBudgetFormResponseSerializer(serializers.Serializer):
    ok = serializers.BooleanField()
    fieldErrors = serializers.DictField(child=serializers.CharField())


class BudgetWarningItemSerializer(serializers.Serializer):
    budgetId = serializers.CharField()
    categoryName = serializers.CharField()
    periodLabel = serializers.CharField()
    status = serializers.ChoiceField(choices=BudgetUsageStatus.choices)
    percent = serializers.FloatField()
    spentRub = serializers.FloatField()
    limitRub = serializers.FloatField()
    remainingRub = serializers.FloatField()
    message = serializers.CharField(required=False)


class BudgetWarningsResponseSerializer(serializers.Serializer):
    items = BudgetWarningItemSerializer(many=True)
    attentionCount = serializers.IntegerField()


class DeleteBudgetResponseSerializer(serializers.Serializer):
    deleted = serializers.BooleanField()
    id = serializers.CharField()


class BudgetOptionSerializer(serializers.Serializer):
    title = serializers.CharField()
    value = serializers.CharField()
    icon = serializers.CharField(required=False)
    color = serializers.CharField(required=False)
    kind = serializers.CharField(required=False)
    symbol = serializers.CharField(required=False)
    isPrimary = serializers.BooleanField(required=False)
    isDefault = serializers.BooleanField(required=False)


class BudgetsListMetaSerializer(serializers.Serializer):
    categories = BudgetOptionSerializer(many=True)
    categoryGroups = BudgetOptionSerializer(many=True)
    periodTypes = BudgetOptionSerializer(many=True)
    currencies = BudgetOptionSerializer(many=True)
    defaultCurrency = serializers.CharField(required=False)
    kinds = BudgetOptionSerializer(many=True)
    usageStatuses = BudgetOptionSerializer(many=True)


def serializer_errors_to_field_errors(errors) -> dict[str, str]:
    field_errors = {}

    for field_name, field_errors_value in errors.items():
        if isinstance(field_errors_value, list):
            field_errors[field_name] = str(field_errors_value[0])
        else:
            field_errors[field_name] = str(field_errors_value)

    return field_errors


def get_budget_form_validation_errors(validated_data: dict) -> dict[str, str]:
    errors = {}

    category_name = validated_data.get("categoryName", "")
    category_id = validated_data.get("categoryId")
    period_start = validated_data.get("periodStart")
    period_end = validated_data.get("periodEnd")

    if not category_id and not category_name.strip():
        errors["categoryName"] = "Выберите категорию бюджета."

    if period_start and period_end and period_end < period_start:
        errors["period"] = "Дата окончания периода не может быть раньше даты начала."

    return errors


def get_budget_meta_categories(user) -> list[dict]:
    categories = (
        Category.objects
        .filter(user=user, is_active=True, is_archived=False)
        .order_by("type", "sort_order", "name", "id")
    )

    return [
        {
            "title": category.name,
            "value": str(category.pk),
            "icon": category.icon,
            "color": category.color,
            "kind": category.type,
        }
        for category in categories
    ]


def get_budget_meta_payload(user) -> dict:
    return {
        "categories": get_budget_meta_categories(user),
        "categoryGroups": BUDGET_CATEGORY_GROUP_OPTIONS,
        "periodTypes": BUDGET_PERIOD_TYPE_OPTIONS,
        "currencies": build_currency_select_options(user),
        "defaultCurrency": get_user_default_currency_code(user),
        "kinds": BUDGET_KIND_OPTIONS,
        "usageStatuses": BUDGET_USAGE_STATUS_OPTIONS,
    }
