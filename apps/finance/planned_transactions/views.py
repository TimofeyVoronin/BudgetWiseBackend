from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.db.models import Q, Sum
from django.utils import timezone
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiTypes,
    extend_schema,
    extend_schema_view,
)
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.common.pagination import StandardResultsSetPagination
from apps.finance.models import (
    Account,
    Category,
    PlannedStatus,
    PlannedTransaction,
    TransactionType,
)
from apps.finance.permissions import IsObjectOwner
from apps.finance.planned_transactions.serializers import (
    CheckPlannedDuplicateResponseSerializer,
    CheckPlannedDuplicateSerializer,
    MAX_PLANNED_SEARCH_LENGTH,
    DEFAULT_PLANNED_FORECAST_TIME_RANGE,
    PLANNED_FORECAST_TIME_RANGES,
    PLANNED_STATUS_OPTIONS,
    ConvertPlannedResponseSerializer,
    ConvertPlannedTransactionSerializer,
    PlannedCalendarResponseSerializer,
    PlannedForecastResponseSerializer,
    PlannedMetaSerializer,
    PlannedSummarySerializer,
    PlannedTransactionSerializer,
    PlannedValidationResponseSerializer,
    ValidatePlannedFormSerializer,
    get_planned_validation_errors,
)
from apps.finance.planned_transactions.services import (
    PlannedConversionError,
    convert_planned_transaction,
)


PLANNED_STATUS_TAB_ALL = "all"
PLANNED_STATUS_TAB_PENDING = "pending"
PLANNED_STATUS_TAB_CONFIRMED = "confirmed"
PLANNED_STATUS_TAB_CANCELLED = "cancelled"

PLANNED_STATUS_TAB_VALUES = {
    PLANNED_STATUS_TAB_ALL,
    PLANNED_STATUS_TAB_PENDING,
    PLANNED_STATUS_TAB_CONFIRMED,
    PLANNED_STATUS_TAB_CANCELLED,
}

MONTH_LABELS_RU = {
    1: "Январь",
    2: "Февраль",
    3: "Март",
    4: "Апрель",
    5: "Май",
    6: "Июнь",
    7: "Июль",
    8: "Август",
    9: "Сентябрь",
    10: "Октябрь",
    11: "Ноябрь",
    12: "Декабрь",
}


def get_first_query_value(query_params, *names):
    for name in names:
        value = query_params.get(name)

        if value not in (None, ""):
            return value

    return None


def parse_multi_value_query_param(query_params, name: str, *, allowed_values=None) -> list[str]:
    values = []

    for raw_value in query_params.getlist(name):
        values.extend(
            value.strip()
            for value in str(raw_value).split(",")
            if value.strip()
        )

    alias_name = f"{name}[]"
    for raw_value in query_params.getlist(alias_name):
        values.extend(
            value.strip()
            for value in str(raw_value).split(",")
            if value.strip()
        )

    if allowed_values is not None:
        invalid_values = [
            value
            for value in values
            if value not in allowed_values
        ]

        if invalid_values:
            raise ValidationError(
                {
                    name: [
                        (
                            "Недопустимое значение фильтра: "
                            f"{', '.join(invalid_values)}."
                        )
                    ]
                }
            )

    return values


def parse_multi_int_query_param(query_params, name: str) -> list[int]:
    raw_values = parse_multi_value_query_param(query_params, name)
    values = []

    for raw_value in raw_values:
        try:
            values.append(int(raw_value))
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                {
                    name: [
                        "Значения фильтра должны быть целыми числами."
                    ]
                }
            ) from exc

    return values


def parse_decimal_query_param(query_params, *names) -> Decimal | None:
    raw_value = get_first_query_value(query_params, *names)

    if raw_value is None:
        return None

    try:
        return Decimal(str(raw_value))
    except (InvalidOperation, ValueError) as exc:
        raise ValidationError(
            {
                names[0]: [
                    "Значение должно быть числом."
                ]
            }
        ) from exc


def parse_bool_query_param(query_params, *names) -> bool | None:
    raw_value = get_first_query_value(query_params, *names)

    if raw_value is None:
        return None

    normalized_value = str(raw_value).strip().lower()

    if normalized_value in {"true", "1", "yes"}:
        return True

    if normalized_value in {"false", "0", "no"}:
        return False

    raise ValidationError(
        {
            names[0]: [
                "Значение должно быть true или false."
            ]
        }
    )


def parse_date_query_param(query_params, *names) -> date | None:
    raw_value = get_first_query_value(query_params, *names)

    if raw_value is None:
        return None

    try:
        return date.fromisoformat(str(raw_value))
    except ValueError as exc:
        raise ValidationError(
            {
                names[0]: [
                    "Дата должна быть в формате YYYY-MM-DD."
                ]
            }
        ) from exc


def get_month_range(value: date) -> tuple[date, date]:
    start = date(value.year, value.month, 1)
    end = date(
        value.year,
        value.month,
        calendar.monthrange(value.year, value.month)[1],
    )
    return start, end


def format_money(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'))} ₽"


@extend_schema_view(
    list=extend_schema(
        tags=["finance-planned-transactions"],
        summary="Получить список планируемых операций",
        description=(
            "Возвращает планируемые операции текущего пользователя. "
            "Поддерживаются фильтры по статусу, периоду, счёту, категории, "
            "сумме, дубликатам и поиску. Планируемые операции не меняют "
            "текущий баланс до конвертации в фактическую операцию."
        ),
        parameters=[
            OpenApiParameter("page", OpenApiTypes.INT, description="Номер страницы."),
            OpenApiParameter("page_size", OpenApiTypes.INT, description="Размер страницы."),
            OpenApiParameter("statusTab", OpenApiTypes.STR, description="Вкладка: all, pending, confirmed или cancelled."),
            OpenApiParameter("search", OpenApiTypes.STR, description="Поиск по названию, категории или счёту."),
            OpenApiParameter("dateFrom", OpenApiTypes.DATE, description="Дата начала периода."),
            OpenApiParameter("dateTo", OpenApiTypes.DATE, description="Дата конца периода."),
            OpenApiParameter("categories", OpenApiTypes.STR, description="ID категорий через запятую."),
            OpenApiParameter("accounts", OpenApiTypes.STR, description="ID счетов через запятую."),
            OpenApiParameter("statuses", OpenApiTypes.STR, description="Статусы через запятую."),
            OpenApiParameter("amountMin", OpenApiTypes.NUMBER, description="Минимальная сумма."),
            OpenApiParameter("amountMax", OpenApiTypes.NUMBER, description="Максимальная сумма."),
            OpenApiParameter("onlyDuplicates", OpenApiTypes.BOOL, description="Только возможные дубликаты."),
        ],
        responses={200: PlannedTransactionSerializer(many=True)},
    ),
    create=extend_schema(
        tags=["finance-planned-transactions"],
        summary="Создать планируемую операцию",
        request=PlannedTransactionSerializer,
        responses={201: PlannedTransactionSerializer},
        examples=[
            OpenApiExample(
                "Создание планируемой операции",
                value={
                    "name": "Такси в аэропорт",
                    "kind": "expense",
                    "amountRub": "2800.00",
                    "categoryId": 2,
                    "accountId": 1,
                    "plannedDate": "2026-06-11",
                    "includeInForecast": True,
                    "comment": "Будущая операция без влияния на текущий баланс",
                },
                request_only=True,
            )
        ],
    ),
    retrieve=extend_schema(
        tags=["finance-planned-transactions"],
        summary="Получить планируемую операцию",
        responses={200: PlannedTransactionSerializer},
    ),
    partial_update=extend_schema(
        tags=["finance-planned-transactions"],
        summary="Частично обновить планируемую операцию",
        request=PlannedTransactionSerializer,
        responses={200: PlannedTransactionSerializer},
    ),
    update=extend_schema(
        tags=["finance-planned-transactions"],
        summary="Полностью обновить планируемую операцию",
        request=PlannedTransactionSerializer,
        responses={200: PlannedTransactionSerializer},
    ),
    destroy=extend_schema(
        tags=["finance-planned-transactions"],
        summary="Удалить планируемую операцию",
        responses={200: OpenApiTypes.OBJECT},
    ),
)
class PlannedTransactionViewSet(viewsets.ModelViewSet):
    serializer_class = PlannedTransactionSerializer
    permission_classes = [IsAuthenticated, IsObjectOwner]
    pagination_class = StandardResultsSetPagination
    lookup_value_regex = r"\d+"

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return PlannedTransaction.objects.none()

        queryset = self.get_base_queryset()

        if self.action != "list":
            return queryset.order_by("planned_date", "name", "id")

        return self.apply_list_filters(queryset).order_by("planned_date", "name", "id")

    def get_base_queryset(self):
        return (
            PlannedTransaction.objects
            .filter(user=self.request.user)
            .select_related("account", "category", "converted_transaction")
        )

    def apply_list_filters(self, queryset):
        query_params = self.request.query_params
        status_tab = query_params.get("statusTab") or query_params.get("status_tab") or ""

        if status_tab:
            if status_tab not in PLANNED_STATUS_TAB_VALUES:
                raise ValidationError(
                    {
                        "statusTab": [
                            "Вкладка статуса должна быть all, pending, confirmed или cancelled."
                        ]
                    }
                )

            if status_tab != PLANNED_STATUS_TAB_ALL:
                queryset = queryset.filter(status=status_tab)

        date_from = parse_date_query_param(query_params, "dateFrom", "date_from")
        date_to = parse_date_query_param(query_params, "dateTo", "date_to")
        categories = parse_multi_int_query_param(query_params, "categories")
        accounts = parse_multi_int_query_param(query_params, "accounts")
        statuses = parse_multi_value_query_param(
            query_params,
            "statuses",
            allowed_values=set(PlannedStatus.values),
        )
        amount_min = parse_decimal_query_param(query_params, "amountMin", "amount_min")
        amount_max = parse_decimal_query_param(query_params, "amountMax", "amount_max")
        only_duplicates = parse_bool_query_param(
            query_params,
            "onlyDuplicates",
            "only_duplicates",
        )
        search = query_params.get("search")

        if date_from and date_to and date_from > date_to:
            raise ValidationError(
                {
                    "dateFrom": [
                        "Дата начала не может быть позже даты окончания."
                    ]
                }
            )

        if amount_min is not None and amount_max is not None and amount_min > amount_max:
            raise ValidationError(
                {
                    "amountMin": [
                        "Минимальная сумма не может быть больше максимальной."
                    ]
                }
            )

        if date_from:
            queryset = queryset.filter(planned_date__gte=date_from)

        if date_to:
            queryset = queryset.filter(planned_date__lte=date_to)

        if categories:
            queryset = queryset.filter(category_id__in=categories)

        if accounts:
            queryset = queryset.filter(account_id__in=accounts)

        if statuses:
            queryset = queryset.filter(status__in=statuses)

        if amount_min is not None:
            queryset = queryset.filter(amount__gte=amount_min)

        if amount_max is not None:
            queryset = queryset.filter(amount__lte=amount_max)

        if only_duplicates is True:
            queryset = self.filter_duplicates(queryset)

        if search:
            search_value = search.strip()

            if len(search_value) > MAX_PLANNED_SEARCH_LENGTH:
                raise ValidationError(
                    {
                        "search": [
                            (
                                "Параметр search не может быть длиннее "
                                f"{MAX_PLANNED_SEARCH_LENGTH} символов."
                            )
                        ]
                    }
                )

            if search_value:
                queryset = queryset.filter(
                    Q(name__icontains=search_value)
                    | Q(account__name__icontains=search_value)
                    | Q(category__name__icontains=search_value)
                )

        return queryset

    def filter_duplicates(self, queryset):
        duplicate_keys = (
            queryset
            .values("name", "planned_date", "account_id", "category_id", "amount")
            .annotate(total=Sum("id"))
        )
        duplicate_query = Q()

        for key in duplicate_keys:
            same_count = queryset.filter(
                name=key["name"],
                planned_date=key["planned_date"],
                account_id=key["account_id"],
                category_id=key["category_id"],
                amount=key["amount"],
            ).count()

            if same_count > 1:
                duplicate_query |= Q(
                    name=key["name"],
                    planned_date=key["planned_date"],
                    account_id=key["account_id"],
                    category_id=key["category_id"],
                    amount=key["amount"],
                )

        if not duplicate_query:
            return queryset.none()

        return queryset.filter(duplicate_query)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def destroy(self, request, *args, **kwargs):
        planned = self.get_object()
        planned_id = planned.pk
        planned.delete()

        return Response(
            {
                "deleted": True,
                "id": planned_id,
            },
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        tags=["finance-planned-transactions"],
        summary="Подтвердить планируемую операцию",
        responses={200: PlannedTransactionSerializer},
    )
    @action(detail=True, methods=["post"], url_path="confirm")
    def confirm(self, request, pk=None):
        planned = self.get_object()
        planned.status = PlannedStatus.CONFIRMED
        planned.last_error_code = ""
        planned.last_error_message = ""
        planned.last_failed_at = None
        planned.save(
            update_fields=[
                "status",
                "last_error_code",
                "last_error_message",
                "last_failed_at",
                "updated_at",
            ]
        )

        serializer = self.get_serializer(planned)
        return Response(serializer.data)

    @extend_schema(
        tags=["finance-planned-transactions"],
        summary="Отменить планируемую операцию",
        responses={200: PlannedTransactionSerializer},
    )
    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        planned = self.get_object()
        planned.status = PlannedStatus.CANCELLED
        planned.save(update_fields=["status", "updated_at"])

        serializer = self.get_serializer(planned)
        return Response(serializer.data)

    @extend_schema(
        tags=["finance-planned-transactions"],
        summary="Вернуть планируемую операцию в ожидание",
        responses={200: PlannedTransactionSerializer},
    )
    @action(detail=True, methods=["post"], url_path="restore")
    def restore(self, request, pk=None):
        planned = self.get_object()
        planned.status = PlannedStatus.PENDING
        planned.last_error_code = ""
        planned.last_error_message = ""
        planned.last_failed_at = None
        planned.save(
            update_fields=[
                "status",
                "last_error_code",
                "last_error_message",
                "last_failed_at",
                "updated_at",
            ]
        )

        serializer = self.get_serializer(planned)
        return Response(serializer.data)

    @extend_schema(
        tags=["finance-planned-transactions"],
        summary="Конвертировать планируемую операцию в фактическую",
        description=(
            "Создаёт обычную финансовую операцию на основе планируемой, "
            "обновляет баланс счёта и связывает план с созданной операцией. "
            "Повторный вызов для уже конвертированной операции не создаёт дубль."
        ),
        request=ConvertPlannedTransactionSerializer,
        responses={200: ConvertPlannedResponseSerializer},
        examples=[
            OpenApiExample(
                "Конвертация планируемой операции",
                value={
                    "operationDate": "2026-06-11",
                },
                request_only=True,
            )
        ],
    )
    @action(detail=True, methods=["post"], url_path="convert")
    def convert(self, request, pk=None):
        planned = self.get_object()
        request_serializer = ConvertPlannedTransactionSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)

        try:
            result = convert_planned_transaction(
                planned_id=planned.pk,
                user=request.user,
                operation_date=request_serializer.validated_data.get("operation_date"),
                mark_overdue_on_failure=True,
            )
        except PlannedConversionError as exc:
            raise ValidationError(
                {
                    "code": exc.code,
                    "message": exc.message,
                }
            ) from exc

        serializer = self.get_serializer(result.planned)
        return Response(
            {
                "planned": serializer.data,
                "operationId": result.transaction_id,
            }
        )

    @extend_schema(
        tags=["finance-planned-transactions"],
        summary="Получить сводку планируемых операций",
        responses={200: PlannedSummarySerializer},
    )
    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        today = timezone.localdate()
        month_start, month_end = get_month_range(today)
        month_queryset = PlannedTransaction.objects.filter(
            user=request.user,
            planned_date__gte=month_start,
            planned_date__lte=month_end,
            status__in=[
                PlannedStatus.PENDING,
                PlannedStatus.CONFIRMED,
                PlannedStatus.CONVERTED,
            ],
        )
        forecast_queryset = PlannedTransaction.objects.filter(
            user=request.user,
            include_in_forecast=True,
            status__in=[
                PlannedStatus.PENDING,
                PlannedStatus.CONFIRMED,
            ],
        )
        planned_month_total = (
            month_queryset.aggregate(value=Sum("amount"))["value"]
            or Decimal("0.00")
        )
        forecast_delta = sum(
            (planned.forecast_delta for planned in forecast_queryset),
            Decimal("0.00"),
        )
        forecast_delta_label = format_money(forecast_delta)
        payload = {
            "planned_month_label": f"Запланировано на {MONTH_LABELS_RU[today.month]}",
            "planned_month_rub": planned_month_total,
            "to_confirm_count": PlannedTransaction.objects.filter(
                user=request.user,
                status=PlannedStatus.PENDING,
            ).count(),
            "forecast_delta_rub": forecast_delta,
            "forecast_delta_label": forecast_delta_label,
            "plannedMonthLabel": f"Запланировано на {MONTH_LABELS_RU[today.month]}",
            "plannedMonthRub": planned_month_total,
            "toConfirmCount": PlannedTransaction.objects.filter(
                user=request.user,
                status=PlannedStatus.PENDING,
            ).count(),
            "forecastDeltaRub": forecast_delta,
            "forecastDeltaLabel": forecast_delta_label,
        }
        serializer = PlannedSummarySerializer(payload)

        return Response(serializer.data)

    @extend_schema(
        tags=["finance-planned-transactions"],
        summary="Получить справочники для планируемых операций",
        responses={200: PlannedMetaSerializer},
    )
    @action(detail=False, methods=["get"], url_path="meta")
    def meta(self, request):
        accounts = [
            {
                "title": account.name,
                "value": str(account.id),
                "icon": account.icon,
            }
            for account in Account.objects.filter(
                user=request.user,
                is_active=True,
                is_archived=False,
            ).order_by("name")
        ]
        categories = [
            {
                "title": category.name,
                "value": str(category.id),
                "icon": category.icon,
                "color": category.color,
            }
            for category in Category.objects.filter(
                user=request.user,
                is_active=True,
                is_archived=False,
            ).order_by("type", "name")
        ]
        payload = {
            "categories": categories,
            "accounts": accounts,
            "statuses": PLANNED_STATUS_OPTIONS,
        }
        serializer = PlannedMetaSerializer(payload)

        return Response(serializer.data)

    @extend_schema(
        tags=["finance-planned-transactions"],
        summary="Проверить возможный дубликат планируемой операции",
        request=CheckPlannedDuplicateSerializer,
        responses={200: CheckPlannedDuplicateResponseSerializer},
    )
    @action(detail=False, methods=["post"], url_path="check-duplicate")
    def check_duplicate(self, request):
        serializer = CheckPlannedDuplicateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        queryset = PlannedTransaction.objects.filter(
            user=request.user,
            name__iexact=data["name"].strip(),
            planned_date=data["plannedDate"],
            amount=data["amountRub"],
        ).exclude(status=PlannedStatus.CANCELLED)

        exclude_id = data.get("excludeId")
        if exclude_id:
            queryset = queryset.exclude(pk=exclude_id)

        account_id = data.get("accountId")
        category_id = data.get("categoryId")

        if account_id:
            queryset = queryset.filter(account_id=account_id)
        elif data.get("accountName"):
            queryset = queryset.filter(account__name__iexact=data["accountName"].strip())

        if category_id:
            queryset = queryset.filter(category_id=category_id)
        elif data.get("categoryName"):
            queryset = queryset.filter(category__name__iexact=data["categoryName"].strip())

        is_duplicate = queryset.exists()
        response_serializer = CheckPlannedDuplicateResponseSerializer(
            {
                "isDuplicate": is_duplicate,
                "message": (
                    "Похожая планируемая операция уже существует."
                    if is_duplicate
                    else ""
                ),
            }
        )

        return Response(response_serializer.data)

    @extend_schema(
        tags=["finance-planned-transactions"],
        summary="Проверить данные формы планируемой операции",
        request=ValidatePlannedFormSerializer,
        responses={200: PlannedValidationResponseSerializer},
    )
    @action(detail=False, methods=["post"], url_path="validate")
    def validate_form(self, request):
        serializer = ValidatePlannedFormSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        field_errors = get_planned_validation_errors(
            serializer.validated_data,
            today=timezone.localdate(),
        )
        response_serializer = PlannedValidationResponseSerializer(
            {
                "ok": not bool(field_errors),
                "fieldErrors": field_errors,
            }
        )

        return Response(response_serializer.data)

    @extend_schema(
        tags=["finance-planned-transactions"],
        summary="Получить календарь планируемых операций",
        parameters=[
            OpenApiParameter("year", OpenApiTypes.INT, required=True, description="Год."),
            OpenApiParameter("month", OpenApiTypes.INT, required=True, description="Месяц от 1 до 12."),
            OpenApiParameter("search", OpenApiTypes.STR, description="Поиск."),
            OpenApiParameter("statuses", OpenApiTypes.STR, description="Статусы через запятую."),
            OpenApiParameter("categories", OpenApiTypes.STR, description="ID категорий через запятую."),
            OpenApiParameter("accounts", OpenApiTypes.STR, description="ID счетов через запятую."),
        ],
        responses={200: PlannedCalendarResponseSerializer},
    )
    @action(detail=False, methods=["get"], url_path="calendar")
    def calendar(self, request):
        try:
            year = int(request.query_params.get("year"))
            month = int(request.query_params.get("month"))
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                {
                    "year": [
                        "year и month должны быть целыми числами."
                    ]
                }
            ) from exc

        if month < 1 or month > 12:
            raise ValidationError(
                {
                    "month": [
                        "month должен быть от 1 до 12."
                    ]
                }
            )

        first_day = date(year, month, 1)
        month_last_day = calendar.monthrange(year, month)[1]
        last_day = date(year, month, month_last_day)
        grid_start = first_day - timedelta(days=first_day.weekday())
        grid_end = grid_start + timedelta(days=41)

        queryset = self.apply_list_filters(
            self.get_base_queryset().filter(
                planned_date__gte=grid_start,
                planned_date__lte=grid_end,
            )
        )
        plans_by_date: dict[date, list[PlannedTransaction]] = {}

        for planned in queryset.order_by("planned_date", "name", "id"):
            plans_by_date.setdefault(planned.planned_date, []).append(planned)

        today = timezone.localdate()
        cells = []
        current_date = grid_start

        while current_date <= grid_end:
            badges = []
            for planned in plans_by_date.get(current_date, [])[:3]:
                badges.append(
                    {
                        "id": str(planned.id),
                        "label": (
                            f"+{planned.amount.quantize(Decimal('0.01'))} ₽"
                            if planned.type == TransactionType.INCOME
                            else f"-{planned.amount.quantize(Decimal('0.01'))} ₽"
                        ),
                        "tone": (
                            "income"
                            if planned.type == TransactionType.INCOME
                            else "expense"
                        ),
                    }
                )

            cells.append(
                {
                    "iso": current_date,
                    "day": current_date.day,
                    "inMonth": first_day <= current_date <= last_day,
                    "isToday": current_date == today,
                    "badges": badges,
                }
            )
            current_date += timedelta(days=1)

        serializer = PlannedCalendarResponseSerializer(
            {
                "year": year,
                "month": month,
                "cells": cells,
            }
        )

        return Response(serializer.data)

    @extend_schema(
        tags=["finance-planned-transactions"],
        summary="Получить прогноз баланса с учётом планируемых операций",
        parameters=[
            OpenApiParameter("timeRange", OpenApiTypes.STR, description="7 дней, 1 мес, 3 мес, 6 мес, 1 год или Всё время."),
            OpenApiParameter("includePlanned", OpenApiTypes.BOOL, description="Учитывать плановые операции."),
            OpenApiParameter("dateFrom", OpenApiTypes.DATE, description="Дата начала периода."),
            OpenApiParameter("dateTo", OpenApiTypes.DATE, description="Дата конца периода."),
        ],
        responses={200: PlannedForecastResponseSerializer},
    )
    @action(detail=False, methods=["get"], url_path="forecast")
    def forecast(self, request):
        today = timezone.localdate()
        time_range = request.query_params.get("timeRange") or DEFAULT_PLANNED_FORECAST_TIME_RANGE

        if time_range not in PLANNED_FORECAST_TIME_RANGES:
            raise ValidationError(
                {
                    "timeRange": [
                        "Недопустимый диапазон прогноза."
                    ]
                }
            )

        include_planned = parse_bool_query_param(
            request.query_params,
            "includePlanned",
            "include_planned",
        )
        if include_planned is None:
            include_planned = True

        date_from = parse_date_query_param(request.query_params, "dateFrom", "date_from") or today
        date_to = parse_date_query_param(request.query_params, "dateTo", "date_to")

        if date_to is None:
            date_to = self.get_forecast_end_date(date_from, time_range)

        if date_from > date_to:
            raise ValidationError(
                {
                    "dateFrom": [
                        "Дата начала не может быть позже даты окончания."
                    ]
                }
            )

        current_balance = (
            Account.objects.filter(
                user=request.user,
                is_active=True,
                is_archived=False,
            ).aggregate(value=Sum("balance"))["value"]
            or Decimal("0.00")
        )
        planned_queryset = PlannedTransaction.objects.filter(
            user=request.user,
            include_in_forecast=True,
            planned_date__gte=date_from,
            planned_date__lte=date_to,
            status__in=[
                PlannedStatus.PENDING,
                PlannedStatus.CONFIRMED,
            ],
        ).order_by("planned_date", "id")
        total_planned_expenses = (
            planned_queryset
            .filter(type=TransactionType.EXPENSE)
            .aggregate(value=Sum("amount"))["value"]
            or Decimal("0.00")
        )
        planned_by_date: dict[date, Decimal] = {}
        expenses_by_date: dict[date, Decimal] = {}

        for planned in planned_queryset:
            planned_by_date[planned.planned_date] = (
                planned_by_date.get(planned.planned_date, Decimal("0.00"))
                + planned.forecast_delta
            )
            if planned.type == TransactionType.EXPENSE:
                expenses_by_date[planned.planned_date] = (
                    expenses_by_date.get(planned.planned_date, Decimal("0.00"))
                    + planned.amount
                )

        points = []
        running_with_plans = current_balance
        running_without_plans = current_balance
        point_dates = self.build_forecast_point_dates(date_from, date_to)
        raw_values = [current_balance]

        for point_date in point_dates:
            running_with_plans += planned_by_date.get(point_date, Decimal("0.00"))
            raw_values.append(running_with_plans)
            raw_values.append(running_without_plans)

        min_value = min(raw_values) if raw_values else Decimal("0.00")
        max_value = max(raw_values) if raw_values else Decimal("1.00")

        if min_value == max_value:
            max_value = min_value + Decimal("1.00")

        running_with_plans = current_balance
        running_without_plans = current_balance

        for point_date in point_dates:
            if include_planned:
                running_with_plans += planned_by_date.get(point_date, Decimal("0.00"))

            point = {
                "label": point_date.strftime("%d.%m"),
                "withPlansPct": self.to_percent(running_with_plans, min_value, max_value),
                "withoutPlansPct": self.to_percent(running_without_plans, min_value, max_value),
            }

            if point_date in expenses_by_date:
                point["markerExpense"] = {
                    "label": point_date.strftime("%d.%m"),
                    "amountRub": str(expenses_by_date[point_date].quantize(Decimal("0.01"))),
                }

            points.append(point)

        response_serializer = PlannedForecastResponseSerializer(
            {
                "legendWithPlans": "С учётом планов",
                "legendWithPlansValue": format_money(running_with_plans),
                "legendWithoutPlans": "Без планов",
                "legendWithoutPlansValue": format_money(running_without_plans),
                "yAxisLabels": self.build_axis_labels(min_value, max_value),
                "points": points,
                "timeRanges": PLANNED_FORECAST_TIME_RANGES,
                "defaultTimeRange": DEFAULT_PLANNED_FORECAST_TIME_RANGE,
                "totalPlannedExpensesLabel": "Итого плановых расходов",
                "totalPlannedExpensesRub": total_planned_expenses,
            }
        )

        return Response(response_serializer.data)

    def get_forecast_end_date(self, start_date: date, time_range: str) -> date:
        if time_range == "7 дней":
            return start_date + timedelta(days=7)
        if time_range == "1 мес":
            return start_date + timedelta(days=30)
        if time_range == "3 мес":
            return start_date + timedelta(days=90)
        if time_range == "6 мес":
            return start_date + timedelta(days=180)
        if time_range == "1 год":
            return start_date + timedelta(days=365)

        last_plan = (
            PlannedTransaction.objects
            .filter(user=self.request.user)
            .order_by("-planned_date")
            .first()
        )
        return last_plan.planned_date if last_plan else start_date + timedelta(days=90)

    def build_forecast_point_dates(self, start_date: date, end_date: date) -> list[date]:
        total_days = (end_date - start_date).days

        if total_days <= 0:
            return [start_date]

        if total_days <= 31:
            step = 7
        elif total_days <= 120:
            step = 14
        else:
            step = 30

        dates = []
        current_date = start_date

        while current_date <= end_date:
            dates.append(current_date)
            current_date += timedelta(days=step)

        if dates[-1] != end_date:
            dates.append(end_date)

        return dates

    def to_percent(self, value: Decimal, min_value: Decimal, max_value: Decimal) -> Decimal:
        percent = (value - min_value) / (max_value - min_value) * Decimal("100")
        return percent.quantize(Decimal("0.01"))

    def build_axis_labels(self, min_value: Decimal, max_value: Decimal) -> list[str]:
        middle = (min_value + max_value) / Decimal("2")
        return [
            format_money(max_value),
            format_money(middle),
            format_money(min_value),
        ]
