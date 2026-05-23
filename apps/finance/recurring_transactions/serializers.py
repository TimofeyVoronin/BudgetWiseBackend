from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Q
from drf_spectacular.utils import OpenApiTypes, extend_schema_field
from rest_framework import serializers

from apps.finance.models import (
    Account,
    Category,
    RecurringChargeStatus,
    RecurringFrequency,
    RecurringStatus,
    RecurringTransaction,
    RecurringTransactionCharge,
    TransactionType,
)


MAX_RECURRING_PREVIEW_COUNT = 24
DEFAULT_RECURRING_PREVIEW_COUNT = 6
MAX_RECURRING_SEARCH_LENGTH = 100
MAX_RECURRING_HISTORY_LIMIT = 100


RECURRING_FREQUENCY_OPTIONS = [
    {
        "title": "Ежедневно",
        "value": RecurringFrequency.DAILY,
    },
    {
        "title": "Еженедельно",
        "value": RecurringFrequency.WEEKLY,
    },
    {
        "title": "Ежемесячно",
        "value": RecurringFrequency.MONTHLY,
    },
    {
        "title": "Ежегодно",
        "value": RecurringFrequency.YEARLY,
    },
]


RECURRING_STATUS_OPTIONS = [
    {
        "title": "Активна",
        "value": RecurringStatus.ACTIVE,
    },
    {
        "title": "На паузе",
        "value": RecurringStatus.PAUSED,
    },
    {
        "title": "Завершена",
        "value": RecurringStatus.COMPLETED,
    },
    {
        "title": "Ошибка",
        "value": RecurringStatus.ERROR,
    },
]


RECURRING_TEMPLATE_OPTIONS = [
    {
        "title": "Подписка",
        "value": "subscription",
    },
    {
        "title": "Коммунальные платежи",
        "value": "utilities",
    },
    {
        "title": "Интернет и связь",
        "value": "internet",
    },
    {
        "title": "Ипотека",
        "value": "mortgage",
    },
    {
        "title": "Зарплата",
        "value": "salary",
    },
    {
        "title": "Другое",
        "value": "other",
    },
]


RECURRING_TEMPLATE_LABELS = {
    option["value"]: option["title"]
    for option in RECURRING_TEMPLATE_OPTIONS
}


def _month_date(year: int, month: int, day: int) -> date:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day, last_day))


def _add_months(value: date, months: int, *, day_of_month: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return _month_date(year, month, day_of_month)


def _first_monthly_date(start_date: date, day_of_month: int) -> date:
    candidate = _month_date(start_date.year, start_date.month, day_of_month)

    if candidate < start_date:
        candidate = _add_months(candidate, 1, day_of_month=day_of_month)

    return candidate


def _first_yearly_date(start_date: date, day_of_month: int) -> date:
    candidate = _month_date(start_date.year, start_date.month, day_of_month)

    if candidate < start_date:
        candidate = _month_date(start_date.year + 1, start_date.month, day_of_month)

    return candidate


def get_first_charge_date(
    *,
    frequency: str,
    start_date: date,
    day_of_month: int | None = None,
) -> date:
    if frequency in {RecurringFrequency.MONTHLY, RecurringFrequency.YEARLY}:
        day = day_of_month or start_date.day

        if frequency == RecurringFrequency.MONTHLY:
            return _first_monthly_date(start_date, day)

        return _first_yearly_date(start_date, day)

    return start_date


def get_next_charge_date(
    *,
    frequency: str,
    previous_date: date,
    day_of_month: int | None = None,
) -> date:
    if frequency == RecurringFrequency.DAILY:
        return previous_date + timedelta(days=1)

    if frequency == RecurringFrequency.WEEKLY:
        return previous_date + timedelta(days=7)

    if frequency == RecurringFrequency.MONTHLY:
        return _add_months(
            previous_date,
            1,
            day_of_month=day_of_month or previous_date.day,
        )

    if frequency == RecurringFrequency.YEARLY:
        return _month_date(
            previous_date.year + 1,
            previous_date.month,
            day_of_month or previous_date.day,
        )

    raise serializers.ValidationError(
        {
            "frequency": "Недопустимая периодичность."
        }
    )


def build_schedule_preview(
    *,
    frequency: str,
    start_date: date,
    day_of_month: int | None = None,
    count: int = DEFAULT_RECURRING_PREVIEW_COUNT,
    end_date: date | None = None,
) -> list[date]:
    first_date = get_first_charge_date(
        frequency=frequency,
        start_date=start_date,
        day_of_month=day_of_month,
    )
    dates = []
    current_date = first_date

    for _ in range(count):
        if end_date and current_date > end_date:
            break

        dates.append(current_date)
        current_date = get_next_charge_date(
            frequency=frequency,
            previous_date=current_date,
            day_of_month=day_of_month,
        )

    return dates


def get_schedule_validation_errors(data: dict) -> dict:
    errors = {}

    start_date = data.get("start_date")
    end_date = data.get("end_date")
    has_end = data.get("has_end", False)
    frequency = data.get("frequency")
    day_of_month = data.get("day_of_month")

    if not start_date:
        errors["startDate"] = "Укажите дату начала."

    if frequency not in RecurringFrequency.values:
        errors["frequency"] = "Недопустимая периодичность."

    if has_end and not end_date:
        errors["endDate"] = "Укажите дату окончания."

    if start_date and end_date and end_date < start_date:
        errors["endDate"] = "Дата окончания не может быть раньше даты начала."

    if day_of_month is not None and not 1 <= day_of_month <= 31:
        errors["dayOfMonth"] = "День месяца должен быть от 1 до 31."

    return errors


class RecurringScheduleSerializer(serializers.Serializer):
    frequency = serializers.ChoiceField(choices=RecurringFrequency.choices)
    dayOfMonth = serializers.IntegerField(
        min_value=1,
        max_value=31,
        required=False,
        allow_null=True,
    )
    startDate = serializers.DateField()
    hasEnd = serializers.BooleanField(default=False)
    endDate = serializers.DateField(
        required=False,
        allow_null=True,
    )
    templateId = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        max_length=100,
    )


class RecurringTransactionSerializer(serializers.ModelSerializer):
    kind = serializers.ChoiceField(
        source="type",
        choices=TransactionType.choices,
        required=False,
    )
    amountRub = serializers.SerializerMethodField(read_only=True)
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
    frequencyLabel = serializers.CharField(
        source="get_frequency_display",
        read_only=True,
    )
    dayOfMonth = serializers.SerializerMethodField(read_only=True)
    startDate = serializers.DateField(
        source="start_date",
        read_only=True,
    )
    hasEnd = serializers.BooleanField(
        source="has_end",
        read_only=True,
    )
    endDate = serializers.DateField(
        source="end_date",
        read_only=True,
        allow_null=True,
    )
    templateId = serializers.CharField(
        source="template_id",
        read_only=True,
    )
    templateName = serializers.CharField(
        source="template_name",
        read_only=True,
    )
    nextChargeDate = serializers.DateField(
        source="next_charge_date",
        read_only=True,
    )
    lastChargeDate = serializers.DateField(
        source="last_charge_date",
        read_only=True,
        allow_null=True,
    )
    statusLabel = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )
    createdCount = serializers.IntegerField(
        source="created_count",
        read_only=True,
    )
    lastErrorCode = serializers.CharField(
        source="last_error_code",
        read_only=True,
    )
    lastErrorMessage = serializers.CharField(
        source="last_error_message",
        read_only=True,
    )
    schedule = RecurringScheduleSerializer(
        write_only=True,
        required=False,
    )

    class Meta:
        model = RecurringTransaction
        fields = [
            "id",
            "name",
            "type",
            "kind",
            "amount",
            "amountRub",
            "category",
            "categoryId",
            "categoryName",
            "categoryIcon",
            "categoryColor",
            "account",
            "accountId",
            "accountName",
            "accountIcon",
            "frequency",
            "frequencyLabel",
            "day_of_month",
            "dayOfMonth",
            "start_date",
            "startDate",
            "has_end",
            "hasEnd",
            "end_date",
            "endDate",
            "template_id",
            "templateId",
            "template_name",
            "templateName",
            "next_charge_date",
            "nextChargeDate",
            "last_charge_date",
            "lastChargeDate",
            "status",
            "statusLabel",
            "created_count",
            "createdCount",
            "last_error_code",
            "lastErrorCode",
            "last_error_message",
            "lastErrorMessage",
            "last_failed_at",
            "comment",
            "schedule",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "amountRub",
            "categoryId",
            "categoryName",
            "categoryIcon",
            "categoryColor",
            "accountId",
            "accountName",
            "accountIcon",
            "frequencyLabel",
            "dayOfMonth",
            "startDate",
            "hasEnd",
            "endDate",
            "templateId",
            "templateName",
            "next_charge_date",
            "nextChargeDate",
            "last_charge_date",
            "lastChargeDate",
            "statusLabel",
            "created_count",
            "createdCount",
            "last_error_code",
            "lastErrorCode",
            "last_error_message",
            "lastErrorMessage",
            "last_failed_at",
            "created_at",
            "updated_at",
        ]

    def to_internal_value(self, data):
        mutable_data = data.copy()

        alias_map = {
            "amountRub": "amount",
            "categoryId": "category",
            "accountId": "account",
            "startDate": "start_date",
            "hasEnd": "has_end",
            "endDate": "end_date",
            "templateId": "template_id",
            "templateName": "template_name",
            "dayOfMonth": "day_of_month",
        }

        for alias, field_name in alias_map.items():
            if alias in mutable_data and field_name not in mutable_data:
                mutable_data[field_name] = mutable_data[alias]

        schedule = mutable_data.get("schedule")

        if isinstance(schedule, dict):
            schedule_map = {
                "frequency": "frequency",
                "dayOfMonth": "day_of_month",
                "startDate": "start_date",
                "hasEnd": "has_end",
                "endDate": "end_date",
                "templateId": "template_id",
            }

            for alias, field_name in schedule_map.items():
                if alias in schedule and field_name not in mutable_data:
                    mutable_data[field_name] = schedule[alias]

        if mutable_data.get("end_date") == "":
            mutable_data["end_date"] = None

        return super().to_internal_value(mutable_data)

    @extend_schema_field(OpenApiTypes.STR)
    def get_amountRub(self, obj) -> str:
        return str(obj.amount.quantize(Decimal("0.01")))

    @extend_schema_field(OpenApiTypes.INT)
    def get_categoryId(self, obj) -> int:
        return obj.category_id

    @extend_schema_field(OpenApiTypes.INT)
    def get_accountId(self, obj) -> int:
        return obj.account_id

    @extend_schema_field(OpenApiTypes.INT)
    def get_dayOfMonth(self, obj) -> int:
        return obj.day_of_month or obj.start_date.day

    def validate_account(self, account: Account) -> Account:
        request = self.context.get("request")

        if request and account.user_id != request.user.id:
            raise serializers.ValidationError(
                "Счёт должен принадлежать текущему пользователю."
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
        attrs.pop("schedule", None)

        request = self.context.get("request")
        instance = self.instance

        account = attrs.get("account", getattr(instance, "account", None))
        category = attrs.get("category", getattr(instance, "category", None))
        transaction_type = attrs.get("type", getattr(instance, "type", TransactionType.EXPENSE))
        frequency = attrs.get("frequency", getattr(instance, "frequency", None))
        start_date = attrs.get("start_date", getattr(instance, "start_date", None))
        has_end = attrs.get("has_end", getattr(instance, "has_end", False))
        end_date = attrs.get("end_date", getattr(instance, "end_date", None))
        day_of_month = attrs.get("day_of_month", getattr(instance, "day_of_month", None))

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

        if not start_date:
            raise serializers.ValidationError(
                {
                    "start_date": "Укажите дату начала."
                }
            )

        if has_end and not end_date:
            raise serializers.ValidationError(
                {
                    "end_date": "Укажите дату окончания."
                }
            )

        if start_date and end_date and end_date < start_date:
            raise serializers.ValidationError(
                {
                    "end_date": "Дата окончания не может быть раньше даты начала."
                }
            )

        if day_of_month is not None and not 1 <= day_of_month <= 31:
            raise serializers.ValidationError(
                {
                    "day_of_month": "День месяца должен быть от 1 до 31."
                }
            )

        if frequency in {RecurringFrequency.MONTHLY, RecurringFrequency.YEARLY} and start_date:
            attrs["day_of_month"] = day_of_month or start_date.day

        if not has_end:
            attrs["end_date"] = None

        schedule_fields = {
            "frequency",
            "day_of_month",
            "start_date",
            "has_end",
            "end_date",
        }
        should_recalculate_next_date = (
            instance is None
            or bool(schedule_fields.intersection(attrs.keys()))
        )

        if should_recalculate_next_date:
            next_charge_date = get_first_charge_date(
                frequency=frequency,
                start_date=start_date,
                day_of_month=attrs.get("day_of_month"),
            )

            if end_date and next_charge_date > end_date:
                raise serializers.ValidationError(
                    {
                        "end_date": (
                            "По указанному расписанию нет списаний "
                            "до даты окончания."
                        )
                    }
                )

            attrs["next_charge_date"] = next_charge_date

        if request:
            attrs["user"] = request.user

        if attrs.get("template_id") and not attrs.get("template_name"):
            attrs["template_name"] = RECURRING_TEMPLATE_LABELS.get(
                attrs["template_id"],
                "",
            )

        return attrs


class RecurringTransactionChargeSerializer(serializers.ModelSerializer):
    recurringId = serializers.SerializerMethodField(read_only=True)
    chargedAt = serializers.SerializerMethodField(read_only=True)
    amountRub = serializers.SerializerMethodField(read_only=True)
    errorMessage = serializers.CharField(
        source="error_message",
        read_only=True,
    )
    operationId = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = RecurringTransactionCharge
        fields = [
            "id",
            "recurring_transaction",
            "recurringId",
            "charged_at",
            "chargedAt",
            "scheduled_date",
            "amount",
            "amountRub",
            "status",
            "error_code",
            "error_message",
            "errorMessage",
            "transaction",
            "operationId",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    @extend_schema_field(OpenApiTypes.INT)
    def get_recurringId(self, obj) -> int:
        return obj.recurring_transaction_id

    @extend_schema_field(OpenApiTypes.DATETIME)
    def get_chargedAt(self, obj):
        return obj.charged_at

    @extend_schema_field(OpenApiTypes.STR)
    def get_amountRub(self, obj) -> str:
        return str(obj.amount.quantize(Decimal("0.01")))

    @extend_schema_field(OpenApiTypes.INT)
    def get_operationId(self, obj) -> int | None:
        return obj.transaction_id


class RecurringSummarySerializer(serializers.Serializer):
    active_count = serializers.IntegerField()
    paused_count = serializers.IntegerField()
    failed_count = serializers.IntegerField()
    next_charge_date = serializers.DateField(allow_null=True)
    next_charge_label = serializers.CharField()

    activeCount = serializers.IntegerField()
    pausedCount = serializers.IntegerField()
    failedCount = serializers.IntegerField()
    nextChargeDate = serializers.DateField(allow_null=True)
    nextChargeLabel = serializers.CharField()


class RecurringOptionSerializer(serializers.Serializer):
    title = serializers.CharField()
    value = serializers.CharField()
    icon = serializers.CharField(required=False)
    color = serializers.CharField(required=False)


class RecurringMetaSerializer(serializers.Serializer):
    frequencies = RecurringOptionSerializer(many=True)
    statuses = RecurringOptionSerializer(many=True)
    accounts = RecurringOptionSerializer(many=True)
    categories = RecurringOptionSerializer(many=True)
    templates = RecurringOptionSerializer(many=True)


class RecurringSchedulePreviewSerializer(serializers.Serializer):
    frequency = serializers.ChoiceField(choices=RecurringFrequency.choices)
    startDate = serializers.DateField()
    dayOfMonth = serializers.IntegerField(
        min_value=1,
        max_value=31,
        required=False,
        allow_null=True,
    )
    count = serializers.IntegerField(
        min_value=1,
        max_value=MAX_RECURRING_PREVIEW_COUNT,
        required=False,
        default=DEFAULT_RECURRING_PREVIEW_COUNT,
    )


class RecurringSchedulePreviewResponseSerializer(serializers.Serializer):
    dates = serializers.ListField(
        child=serializers.DateField(),
    )


class ValidateRecurringScheduleSerializer(serializers.Serializer):
    startDate = serializers.DateField()
    endDate = serializers.DateField(
        required=False,
        allow_null=True,
    )
    hasEnd = serializers.BooleanField(default=False)
    frequency = serializers.ChoiceField(choices=RecurringFrequency.choices)
    dayOfMonth = serializers.IntegerField(
        min_value=1,
        max_value=31,
        required=False,
        allow_null=True,
    )


class RecurringScheduleValidationResponseSerializer(serializers.Serializer):
    ok = serializers.BooleanField()
    fieldErrors = serializers.DictField(
        child=serializers.CharField(),
    )
