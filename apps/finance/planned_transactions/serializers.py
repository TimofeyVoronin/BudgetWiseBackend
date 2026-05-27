from __future__ import annotations

from datetime import date
from decimal import Decimal

from drf_spectacular.utils import OpenApiTypes, extend_schema_field
from rest_framework import serializers

from apps.finance.currencies.money import MoneyAmountSerializer, build_money_payload
from apps.finance.currencies.services import validate_user_currency_available
from apps.finance.models import (
    Account,
    Category,
    PlannedStatus,
    PlannedTransaction,
    TransactionType,
)


MAX_PLANNED_SEARCH_LENGTH = 100
PLANNED_FORECAST_TIME_RANGES = [
    "7 дней",
    "1 мес",
    "3 мес",
    "6 мес",
    "1 год",
    "Всё время",
]
DEFAULT_PLANNED_FORECAST_TIME_RANGE = "3 мес"


PLANNED_STATUS_OPTIONS = [
    {
        "title": "Ожидает",
        "value": PlannedStatus.PENDING,
    },
    {
        "title": "Подтверждена",
        "value": PlannedStatus.CONFIRMED,
    },
    {
        "title": "Отменена",
        "value": PlannedStatus.CANCELLED,
    },
    {
        "title": "Конвертирована",
        "value": PlannedStatus.CONVERTED,
    },
    {
        "title": "Просрочена",
        "value": PlannedStatus.OVERDUE,
    },
]


class PlannedTransactionSerializer(serializers.ModelSerializer):
    kind = serializers.ChoiceField(
        source="type",
        choices=TransactionType.choices,
        required=False,
    )
    amountRub = serializers.SerializerMethodField(read_only=True)
    amountDisplay = serializers.SerializerMethodField(read_only=True)
    amountAbsDisplay = serializers.SerializerMethodField(read_only=True)
    signedAmountDisplay = serializers.SerializerMethodField(read_only=True)
    sourceCurrency = serializers.SerializerMethodField(read_only=True)
    categoryId = serializers.SerializerMethodField(read_only=True)
    categoryName = serializers.CharField(
        source="category.name",
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
    accountId = serializers.SerializerMethodField(read_only=True)
    accountName = serializers.CharField(
        source="account.name",
        read_only=True,
    )
    accountIcon = serializers.CharField(
        source="account.icon",
        read_only=True,
    )
    plannedDate = serializers.DateField(
        source="planned_date",
        read_only=True,
    )
    statusLabel = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )
    includeInForecast = serializers.BooleanField(
        source="include_in_forecast",
        read_only=True,
    )
    convertedTransactionId = serializers.SerializerMethodField(read_only=True)
    operationId = serializers.SerializerMethodField(read_only=True)
    convertedAt = serializers.DateTimeField(
        source="converted_at",
        read_only=True,
        allow_null=True,
    )
    lastErrorCode = serializers.CharField(
        source="last_error_code",
        read_only=True,
    )
    lastErrorMessage = serializers.CharField(
        source="last_error_message",
        read_only=True,
    )
    lastFailedAt = serializers.DateTimeField(
        source="last_failed_at",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = PlannedTransaction
        fields = [
            "id",
            "name",
            "type",
            "kind",
            "amount",
            "amountRub",
            "amountDisplay",
            "amountAbsDisplay",
            "signedAmountDisplay",
            "sourceCurrency",
            "category",
            "categoryId",
            "categoryName",
            "categoryIcon",
            "categoryColor",
            "account",
            "accountId",
            "accountName",
            "accountIcon",
            "planned_date",
            "plannedDate",
            "status",
            "statusLabel",
            "comment",
            "include_in_forecast",
            "includeInForecast",
            "converted_transaction",
            "convertedTransactionId",
            "operationId",
            "converted_at",
            "convertedAt",
            "last_error_code",
            "lastErrorCode",
            "last_error_message",
            "lastErrorMessage",
            "last_failed_at",
            "lastFailedAt",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "amountRub",
            "amountDisplay",
            "amountAbsDisplay",
            "signedAmountDisplay",
            "sourceCurrency",
            "categoryId",
            "categoryName",
            "categoryIcon",
            "categoryColor",
            "accountId",
            "accountName",
            "accountIcon",
            "plannedDate",
            "statusLabel",
            "includeInForecast",
            "converted_transaction",
            "convertedTransactionId",
            "operationId",
            "converted_at",
            "convertedAt",
            "last_error_code",
            "lastErrorCode",
            "last_error_message",
            "lastErrorMessage",
            "last_failed_at",
            "lastFailedAt",
            "created_at",
            "updated_at",
        ]

    def to_internal_value(self, data):
        mutable_data = data.copy()
        alias_map = {
            "amountRub": "amount",
            "categoryId": "category",
            "accountId": "account",
            "plannedDate": "planned_date",
            "includeInForecast": "include_in_forecast",
        }

        for alias, field_name in alias_map.items():
            if alias in mutable_data and field_name not in mutable_data:
                mutable_data[field_name] = mutable_data[alias]

        return super().to_internal_value(mutable_data)

    @extend_schema_field(OpenApiTypes.STR)
    def get_amountRub(self, obj) -> str:
        return self._format_decimal(self._display_money(obj, obj.amount)["amount"])

    @extend_schema_field(MoneyAmountSerializer)
    def get_amountDisplay(self, obj) -> dict:
        return self._display_money(obj, obj.amount)

    @extend_schema_field(MoneyAmountSerializer)
    def get_amountAbsDisplay(self, obj) -> dict:
        return self._display_money(obj, abs(obj.amount))

    @extend_schema_field(MoneyAmountSerializer)
    def get_signedAmountDisplay(self, obj) -> dict:
        return self._display_money(obj, self._signed_amount_value(obj))

    @extend_schema_field(OpenApiTypes.STR)
    def get_sourceCurrency(self, obj) -> str:
        return self._source_currency(obj)

    def _format_decimal(self, value) -> str:
        return str(Decimal(str(value)).quantize(Decimal("0.01")))

    def _signed_amount_value(self, obj) -> Decimal:
        amount = abs(obj.amount)

        if obj.type == TransactionType.EXPENSE:
            amount = -amount

        return amount

    def _source_currency(self, obj) -> str:
        account = getattr(obj, "account", None)
        return getattr(account, "currency", None) or "RUB"

    def _display_money(self, obj, value) -> dict:
        converter = self.context.get("currency_converter")
        source_currency = self._source_currency(obj)

        if converter is None:
            return build_money_payload(value, currency=source_currency)

        return converter.display_amount_payload(
            value,
            source_currency=source_currency,
        )

    @extend_schema_field(OpenApiTypes.INT)
    def get_categoryId(self, obj) -> int:
        return obj.category_id

    @extend_schema_field(OpenApiTypes.INT)
    def get_accountId(self, obj) -> int:
        return obj.account_id

    @extend_schema_field(OpenApiTypes.INT)
    def get_convertedTransactionId(self, obj) -> int | None:
        return obj.converted_transaction_id

    @extend_schema_field(OpenApiTypes.INT)
    def get_operationId(self, obj) -> int | None:
        return obj.converted_transaction_id

    def validate_account(self, account: Account) -> Account:
        request = self.context.get("request")

        if request and account.user_id != request.user.id:
            raise serializers.ValidationError(
                "Счёт должен принадлежать текущему пользователю."
            )

        if request:
            validate_user_currency_available(
                request.user,
                account.currency,
                field_name="account",
                require_visible=True,
            )

        if not account.is_active:
            raise serializers.ValidationError(
                "Нельзя использовать неактивный счёт."
            )

        if account.is_archived:
            raise serializers.ValidationError(
                "Нельзя использовать архивный счёт."
            )

        return account

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

    def validate(self, attrs):
        request = self.context.get("request")
        instance = self.instance

        account = attrs.get("account") or getattr(instance, "account", None)
        category = attrs.get("category") or getattr(instance, "category", None)
        transaction_type = attrs.get("type") or getattr(instance, "type", None)

        if request:
            if account and account.user_id != request.user.id:
                raise serializers.ValidationError(
                    {
                        "account": [
                            "Счёт должен принадлежать текущему пользователю."
                        ]
                    }
                )

            if category and category.user_id != request.user.id:
                raise serializers.ValidationError(
                    {
                        "category": [
                            "Категория должна принадлежать текущему пользователю."
                        ]
                    }
                )

        if account:
            if not account.is_active:
                raise serializers.ValidationError(
                    {
                        "account": [
                            "Нельзя использовать неактивный счёт."
                        ]
                    }
                )

            if account.is_archived:
                raise serializers.ValidationError(
                    {
                        "account": [
                            "Нельзя использовать архивный счёт."
                        ]
                    }
                )

        if category:
            if not category.is_active:
                raise serializers.ValidationError(
                    {
                        "category": [
                            "Нельзя использовать неактивную категорию."
                        ]
                    }
                )

            if category.is_archived:
                raise serializers.ValidationError(
                    {
                        "category": [
                            "Нельзя использовать архивную категорию."
                        ]
                    }
                )

        if category and transaction_type and category.type != transaction_type:
            raise serializers.ValidationError(
                {
                    "category": [
                        "Тип категории должен совпадать с типом операции."
                    ]
                }
            )

        return attrs


class PlannedSummarySerializer(serializers.Serializer):
    planned_month_label = serializers.CharField()
    planned_month_rub = serializers.DecimalField(max_digits=14, decimal_places=2)
    planned_month = MoneyAmountSerializer()
    to_confirm_count = serializers.IntegerField()
    forecast_delta_rub = serializers.DecimalField(max_digits=14, decimal_places=2)
    forecast_delta = MoneyAmountSerializer()
    forecast_delta_label = serializers.CharField(required=False, allow_blank=True)

    plannedMonthLabel = serializers.CharField()
    plannedMonthRub = serializers.DecimalField(max_digits=14, decimal_places=2)
    plannedMonth = MoneyAmountSerializer()
    toConfirmCount = serializers.IntegerField()
    forecastDeltaRub = serializers.DecimalField(max_digits=14, decimal_places=2)
    forecastDelta = MoneyAmountSerializer()
    forecastDeltaLabel = serializers.CharField(required=False, allow_blank=True)
    currencyContext = serializers.DictField(read_only=True)


class PlannedOptionSerializer(serializers.Serializer):
    title = serializers.CharField()
    value = serializers.CharField()
    icon = serializers.CharField(required=False)
    color = serializers.CharField(required=False)


class PlannedMetaSerializer(serializers.Serializer):
    categories = PlannedOptionSerializer(many=True)
    accounts = PlannedOptionSerializer(many=True)
    statuses = PlannedOptionSerializer(many=True)


class PlannedCalendarDayBadgeSerializer(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()
    tone = serializers.ChoiceField(choices=["income", "expense", "subscription"])
    amountDisplay = MoneyAmountSerializer(required=False)
    sourceCurrency = serializers.CharField(required=False)


class PlannedCalendarDayCellSerializer(serializers.Serializer):
    iso = serializers.DateField()
    day = serializers.IntegerField()
    inMonth = serializers.BooleanField()
    isToday = serializers.BooleanField()
    badges = PlannedCalendarDayBadgeSerializer(many=True)


class PlannedCalendarResponseSerializer(serializers.Serializer):
    year = serializers.IntegerField()
    month = serializers.IntegerField()
    cells = PlannedCalendarDayCellSerializer(many=True)
    currencyContext = serializers.DictField(read_only=True)


class ValidatePlannedFormSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150, allow_blank=False)
    kind = serializers.ChoiceField(choices=TransactionType.choices)
    amountAbs = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    plannedDate = serializers.DateField()
    allowPastDate = serializers.BooleanField(required=False, default=False)


class PlannedValidationResponseSerializer(serializers.Serializer):
    ok = serializers.BooleanField()
    fieldErrors = serializers.DictField(child=serializers.CharField())


class CheckPlannedDuplicateSerializer(serializers.Serializer):
    excludeId = serializers.IntegerField(required=False, allow_null=True)
    name = serializers.CharField(max_length=150)
    plannedDate = serializers.DateField()
    categoryId = serializers.IntegerField(required=False, allow_null=True)
    categoryName = serializers.CharField(required=False, allow_blank=True)
    accountId = serializers.IntegerField(required=False, allow_null=True)
    accountName = serializers.CharField(required=False, allow_blank=True)
    amountRub = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))


class CheckPlannedDuplicateResponseSerializer(serializers.Serializer):
    isDuplicate = serializers.BooleanField()
    message = serializers.CharField(required=False, allow_blank=True)


class PlannedForecastChartPointSerializer(serializers.Serializer):
    label = serializers.CharField()
    withPlansPct = serializers.DecimalField(max_digits=6, decimal_places=2)
    withoutPlansPct = serializers.DecimalField(max_digits=6, decimal_places=2)
    markerExpense = serializers.DictField(required=False)


class PlannedForecastResponseSerializer(serializers.Serializer):
    legendWithPlans = serializers.CharField()
    legendWithPlansValue = serializers.CharField()
    legendWithoutPlans = serializers.CharField()
    legendWithoutPlansValue = serializers.CharField()
    yAxisLabels = serializers.ListField(child=serializers.CharField())
    points = PlannedForecastChartPointSerializer(many=True)
    timeRanges = serializers.ListField(child=serializers.CharField())
    defaultTimeRange = serializers.CharField()
    totalPlannedExpensesLabel = serializers.CharField()
    totalPlannedExpensesRub = serializers.DecimalField(max_digits=14, decimal_places=2)
    totalPlannedExpenses = MoneyAmountSerializer()
    currencyContext = serializers.DictField(read_only=True)


def get_planned_validation_errors(data: dict, *, today: date) -> dict:
    errors = {}
    name = (data.get("name") or "").strip()
    amount = data.get("amountAbs")
    planned_date = data.get("plannedDate")
    allow_past_date = data.get("allowPastDate", False)

    if not name:
        errors["name"] = "Укажите название плановой операции."

    if amount is None or amount <= Decimal("0.00"):
        errors["amount"] = "Сумма должна быть больше нуля."

    if not planned_date:
        errors["plannedDate"] = "Укажите дату плановой операции."

    if planned_date and not allow_past_date and planned_date < today:
        errors["plannedDate"] = "Дата плановой операции не может быть в прошлом."

    return errors


class ConvertPlannedTransactionSerializer(serializers.Serializer):
    operationDate = serializers.DateField(required=False)
    operation_date = serializers.DateField(required=False, write_only=True)

    def validate(self, attrs):
        operation_date = attrs.get("operationDate") or attrs.get("operation_date")

        return {
            "operation_date": operation_date,
        }


class ConvertPlannedResponseSerializer(serializers.Serializer):
    planned = PlannedTransactionSerializer()
    operationId = serializers.IntegerField()
