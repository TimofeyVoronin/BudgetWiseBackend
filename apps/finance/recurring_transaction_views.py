from decimal import Decimal, InvalidOperation

from django.db.models import Min, Q
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
    RecurringFrequency,
    RecurringStatus,
    RecurringTransaction,
    RecurringTransactionCharge,
)
from apps.finance.permissions import IsObjectOwner
from apps.finance.recurring_transaction_serializers import (
    MAX_RECURRING_HISTORY_LIMIT,
    MAX_RECURRING_SEARCH_LENGTH,
    RECURRING_FREQUENCY_OPTIONS,
    RECURRING_STATUS_OPTIONS,
    RECURRING_TEMPLATE_OPTIONS,
    RecurringMetaSerializer,
    RecurringSchedulePreviewResponseSerializer,
    RecurringSchedulePreviewSerializer,
    RecurringScheduleValidationResponseSerializer,
    RecurringSummarySerializer,
    RecurringTransactionChargeSerializer,
    RecurringTransactionSerializer,
    ValidateRecurringScheduleSerializer,
    build_schedule_preview,
    get_schedule_validation_errors,
)


RECURRING_STATUS_TAB_ACTIVE = "active"
RECURRING_STATUS_TAB_PAUSED = "paused"
RECURRING_STATUS_TAB_COMPLETED = "completed"

RECURRING_STATUS_TAB_VALUES = {
    RECURRING_STATUS_TAB_ACTIVE,
    RECURRING_STATUS_TAB_PAUSED,
    RECURRING_STATUS_TAB_COMPLETED,
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


@extend_schema_view(
    list=extend_schema(
        tags=["finance-recurring-transactions"],
        summary="Получить список регулярных операций",
        description=(
            "Возвращает регулярные операции текущего пользователя. "
            "Поддерживаются фильтры по вкладке статуса, периодичности, счёту, "
            "категории, сумме, ошибкам и поиску."
        ),
        parameters=[
            OpenApiParameter("page", OpenApiTypes.INT, description="Номер страницы."),
            OpenApiParameter("page_size", OpenApiTypes.INT, description="Размер страницы."),
            OpenApiParameter("statusTab", OpenApiTypes.STR, description="Вкладка: active, paused или completed."),
            OpenApiParameter("search", OpenApiTypes.STR, description="Поиск по названию операции, категории или счёту."),
            OpenApiParameter("frequencies", OpenApiTypes.STR, description="Периодичности через запятую: daily, weekly, monthly, yearly."),
            OpenApiParameter("accounts", OpenApiTypes.STR, description="ID счетов через запятую."),
            OpenApiParameter("categories", OpenApiTypes.STR, description="ID категорий через запятую."),
            OpenApiParameter("amountMin", OpenApiTypes.NUMBER, description="Минимальная сумма."),
            OpenApiParameter("amountMax", OpenApiTypes.NUMBER, description="Максимальная сумма."),
            OpenApiParameter("onlyWithErrors", OpenApiTypes.BOOL, description="Только операции с ошибками."),
        ],
        responses={200: RecurringTransactionSerializer(many=True)},
    ),
    create=extend_schema(
        tags=["finance-recurring-transactions"],
        summary="Создать регулярную операцию",
        request=RecurringTransactionSerializer,
        responses={201: RecurringTransactionSerializer},
        examples=[
            OpenApiExample(
                "Создание регулярной операции",
                value={
                    "name": "Интернет домашний",
                    "kind": "expense",
                    "amountRub": "890.00",
                    "categoryId": 2,
                    "accountId": 1,
                    "schedule": {
                        "frequency": "monthly",
                        "dayOfMonth": 15,
                        "startDate": "2026-05-15",
                        "hasEnd": False,
                        "endDate": None,
                        "templateId": "internet",
                    },
                    "comment": "Домашний интернет",
                },
                request_only=True,
            )
        ],
    ),
    retrieve=extend_schema(
        tags=["finance-recurring-transactions"],
        summary="Получить регулярную операцию",
        responses={200: RecurringTransactionSerializer},
    ),
    partial_update=extend_schema(
        tags=["finance-recurring-transactions"],
        summary="Частично обновить регулярную операцию",
        request=RecurringTransactionSerializer,
        responses={200: RecurringTransactionSerializer},
    ),
    update=extend_schema(
        tags=["finance-recurring-transactions"],
        summary="Полностью обновить регулярную операцию",
        request=RecurringTransactionSerializer,
        responses={200: RecurringTransactionSerializer},
    ),
    destroy=extend_schema(
        tags=["finance-recurring-transactions"],
        summary="Удалить регулярную операцию",
        responses={200: OpenApiTypes.OBJECT},
    ),
)
class RecurringTransactionViewSet(viewsets.ModelViewSet):
    serializer_class = RecurringTransactionSerializer
    permission_classes = [IsAuthenticated, IsObjectOwner]
    pagination_class = StandardResultsSetPagination
    lookup_value_regex = r"\d+"

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return RecurringTransaction.objects.none()

        queryset = (
            RecurringTransaction.objects
            .filter(user=self.request.user)
            .select_related("account", "category")
        )

        if self.action != "list":
            return queryset.order_by("next_charge_date", "name")

        query_params = self.request.query_params
        status_tab = query_params.get("statusTab") or query_params.get("status_tab") or ""

        if status_tab:
            if status_tab not in RECURRING_STATUS_TAB_VALUES:
                raise ValidationError(
                    {
                        "statusTab": [
                            "Вкладка статуса должна быть active, paused или completed."
                        ]
                    }
                )

            if status_tab == RECURRING_STATUS_TAB_ACTIVE:
                queryset = queryset.filter(
                    status__in=[
                        RecurringStatus.ACTIVE,
                        RecurringStatus.ERROR,
                    ]
                )

            if status_tab == RECURRING_STATUS_TAB_PAUSED:
                queryset = queryset.filter(status=RecurringStatus.PAUSED)

            if status_tab == RECURRING_STATUS_TAB_COMPLETED:
                queryset = queryset.filter(status=RecurringStatus.COMPLETED)

        frequencies = parse_multi_value_query_param(
            query_params,
            "frequencies",
            allowed_values=set(RecurringFrequency.values),
        )
        accounts = parse_multi_int_query_param(query_params, "accounts")
        categories = parse_multi_int_query_param(query_params, "categories")
        amount_min = parse_decimal_query_param(query_params, "amountMin", "amount_min")
        amount_max = parse_decimal_query_param(query_params, "amountMax", "amount_max")
        only_with_errors = parse_bool_query_param(
            query_params,
            "onlyWithErrors",
            "only_with_errors",
        )
        search = query_params.get("search")

        if amount_min is not None and amount_max is not None and amount_min > amount_max:
            raise ValidationError(
                {
                    "amountMin": [
                        "Минимальная сумма не может быть больше максимальной."
                    ]
                }
            )

        if frequencies:
            queryset = queryset.filter(frequency__in=frequencies)

        if accounts:
            queryset = queryset.filter(account_id__in=accounts)

        if categories:
            queryset = queryset.filter(category_id__in=categories)

        if amount_min is not None:
            queryset = queryset.filter(amount__gte=amount_min)

        if amount_max is not None:
            queryset = queryset.filter(amount__lte=amount_max)

        if only_with_errors is True:
            queryset = queryset.filter(status=RecurringStatus.ERROR)

        if only_with_errors is False:
            queryset = queryset.exclude(status=RecurringStatus.ERROR)

        if search:
            search_value = search.strip()

            if len(search_value) > MAX_RECURRING_SEARCH_LENGTH:
                raise ValidationError(
                    {
                        "search": [
                            (
                                "Параметр search не может быть длиннее "
                                f"{MAX_RECURRING_SEARCH_LENGTH} символов."
                            )
                        ]
                    }
                )

            if search_value:
                queryset = queryset.filter(
                    Q(name__icontains=search_value)
                    | Q(account__name__icontains=search_value)
                    | Q(category__name__icontains=search_value)
                    | Q(template_name__icontains=search_value)
                )

        return queryset.order_by("next_charge_date", "name", "id")

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def destroy(self, request, *args, **kwargs):
        recurring = self.get_object()
        recurring_id = recurring.pk
        recurring.delete()

        return Response(
            {
                "deleted": True,
                "id": recurring_id,
            },
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        tags=["finance-recurring-transactions"],
        summary="Поставить регулярную операцию на паузу",
        responses={200: RecurringTransactionSerializer},
    )
    @action(detail=True, methods=["post"], url_path="pause")
    def pause(self, request, pk=None):
        recurring = self.get_object()
        recurring.status = RecurringStatus.PAUSED
        recurring.save(update_fields=["status", "updated_at"])

        serializer = self.get_serializer(recurring)
        return Response(serializer.data)

    @extend_schema(
        tags=["finance-recurring-transactions"],
        summary="Возобновить регулярную операцию",
        responses={200: RecurringTransactionSerializer},
    )
    @action(detail=True, methods=["post"], url_path="resume")
    def resume(self, request, pk=None):
        recurring = self.get_object()
        recurring.status = RecurringStatus.ACTIVE
        recurring.last_error_code = ""
        recurring.last_error_message = ""
        recurring.last_failed_at = None
        recurring.save(
            update_fields=[
                "status",
                "last_error_code",
                "last_error_message",
                "last_failed_at",
                "updated_at",
            ]
        )

        serializer = self.get_serializer(recurring)
        return Response(serializer.data)

    @extend_schema(
        tags=["finance-recurring-transactions"],
        summary="Завершить регулярную операцию",
        responses={200: RecurringTransactionSerializer},
    )
    @action(detail=True, methods=["post"], url_path="complete")
    def complete(self, request, pk=None):
        recurring = self.get_object()
        recurring.status = RecurringStatus.COMPLETED
        recurring.save(update_fields=["status", "updated_at"])

        serializer = self.get_serializer(recurring)
        return Response(serializer.data)

    @extend_schema(
        tags=["finance-recurring-transactions"],
        summary="Получить историю списаний по регулярной операции",
        parameters=[
            OpenApiParameter("limit", OpenApiTypes.INT, description="Количество записей, максимум 100."),
            OpenApiParameter("offset", OpenApiTypes.INT, description="Смещение."),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    @action(detail=True, methods=["get"], url_path="charge-history")
    def charge_history(self, request, pk=None):
        recurring = self.get_object()

        try:
            limit = int(request.query_params.get("limit", 20))
            offset = int(request.query_params.get("offset", 0))
        except ValueError as exc:
            raise ValidationError(
                {
                    "limit": [
                        "limit и offset должны быть целыми числами."
                    ]
                }
            ) from exc

        if limit < 1 or limit > MAX_RECURRING_HISTORY_LIMIT:
            raise ValidationError(
                {
                    "limit": [
                        f"limit должен быть от 1 до {MAX_RECURRING_HISTORY_LIMIT}."
                    ]
                }
            )

        if offset < 0:
            raise ValidationError(
                {
                    "offset": [
                        "offset не может быть отрицательным."
                    ]
                }
            )

        queryset = recurring.charges.order_by("-charged_at", "-id")[offset:offset + limit]
        serializer = RecurringTransactionChargeSerializer(queryset, many=True)

        return Response(
            {
                "recurringId": recurring.id,
                "items": serializer.data,
            }
        )

    @extend_schema(
        tags=["finance-recurring-transactions"],
        summary="Получить сводку регулярных операций",
        responses={200: RecurringSummarySerializer},
    )
    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        base_queryset = RecurringTransaction.objects.filter(user=request.user)
        active_queryset = base_queryset.filter(
            status__in=[
                RecurringStatus.ACTIVE,
                RecurringStatus.ERROR,
            ]
        )
        next_charge_date = active_queryset.aggregate(
            value=Min("next_charge_date")
        )["value"]
        next_charge_label = ""

        if next_charge_date:
            next_charge_label = next_charge_date.strftime("%d.%m.%Y")

        payload = {
            "active_count": active_queryset.count(),
            "activeCount": active_queryset.count(),
            "paused_count": base_queryset.filter(status=RecurringStatus.PAUSED).count(),
            "pausedCount": base_queryset.filter(status=RecurringStatus.PAUSED).count(),
            "failed_count": base_queryset.filter(status=RecurringStatus.ERROR).count(),
            "failedCount": base_queryset.filter(status=RecurringStatus.ERROR).count(),
            "next_charge_date": next_charge_date,
            "nextChargeDate": next_charge_date,
            "next_charge_label": next_charge_label,
            "nextChargeLabel": next_charge_label,
        }
        serializer = RecurringSummarySerializer(payload)

        return Response(serializer.data)

    @extend_schema(
        tags=["finance-recurring-transactions"],
        summary="Получить справочники для регулярных операций",
        responses={200: RecurringMetaSerializer},
    )
    @action(detail=False, methods=["get"], url_path="meta")
    def meta(self, request):
        accounts = [
            {
                "title": account.name,
                "value": str(account.id),
                "icon": account.icon,
                "color": account.color,
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
            "frequencies": RECURRING_FREQUENCY_OPTIONS,
            "statuses": RECURRING_STATUS_OPTIONS,
            "accounts": accounts,
            "categories": categories,
            "templates": RECURRING_TEMPLATE_OPTIONS,
        }
        serializer = RecurringMetaSerializer(payload)

        return Response(serializer.data)

    @extend_schema(
        tags=["finance-recurring-transactions"],
        summary="Получить превью расписания",
        request=RecurringSchedulePreviewSerializer,
        responses={200: RecurringSchedulePreviewResponseSerializer},
    )
    @action(detail=False, methods=["post"], url_path="schedule-preview")
    def schedule_preview(self, request):
        serializer = RecurringSchedulePreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        dates = build_schedule_preview(
            frequency=data["frequency"],
            start_date=data["startDate"],
            day_of_month=data.get("dayOfMonth"),
            count=data["count"],
        )
        response_serializer = RecurringSchedulePreviewResponseSerializer(
            {
                "dates": dates,
            }
        )

        return Response(response_serializer.data)

    @extend_schema(
        tags=["finance-recurring-transactions"],
        summary="Проверить расписание",
        request=ValidateRecurringScheduleSerializer,
        responses={200: RecurringScheduleValidationResponseSerializer},
    )
    @action(detail=False, methods=["post"], url_path="validate-schedule")
    def validate_schedule(self, request):
        serializer = ValidateRecurringScheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        normalized_data = {
            "start_date": data["startDate"],
            "end_date": data.get("endDate"),
            "has_end": data["hasEnd"],
            "frequency": data["frequency"],
            "day_of_month": data.get("dayOfMonth"),
        }
        field_errors = get_schedule_validation_errors(normalized_data)
        response_serializer = RecurringScheduleValidationResponseSerializer(
            {
                "ok": not bool(field_errors),
                "fieldErrors": field_errors,
            }
        )

        return Response(response_serializer.data)
