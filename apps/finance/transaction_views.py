from django.db.models import Q
from django.http import HttpResponse
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiTypes,
    extend_schema,
    extend_schema_view,
)
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.common.pagination import StandardResultsSetPagination
from apps.common.validation import (
    get_bool_query_param,
    get_date_query_param,
    get_decimal_query_param,
    get_int_query_param,
    validate_choice_query_param,
    validate_ordering_fields,
)
from apps.finance.exporters import (
    TRANSACTION_EXPORT_FORMATS,
    build_transaction_export,
)
from apps.finance.accounting import (
    create_transaction_with_balance_update,
    delete_transaction_with_balance_update,
    update_transaction_with_balance_update,
)
from apps.finance.models import Transaction, TransactionType
from apps.finance.permissions import IsObjectOwner
from apps.finance.transaction_serializers import TransactionSerializer


MAX_TRANSACTION_SEARCH_LENGTH = 100
MAX_TRANSACTION_EXPORT_ROWS = 5000

TRANSACTION_SORT_FIELDS = {
    "date": "operation_date",
    "operation_date": "operation_date",
    "description": "description",
    "name": "description",
    "amount": "amount",
    "amountRub": "amount",
    "amount_rub": "amount",
    "category": "category__name",
    "categoryName": "category__name",
    "account": "account__name",
    "accountName": "account__name",
    "created_at": "created_at",
}

TRANSACTION_SORT_DIRECTIONS = {
    "asc",
    "desc",
}


def get_first_query_value(query_params, *names):
    for name in names:
        value = query_params.get(name)

        if value not in (None, ""):
            return value

    return None


def get_aliased_int_query_param(query_params, *names):
    for name in names:
        if query_params.get(name) not in (None, ""):
            return get_int_query_param(query_params, name)

    return None


def get_aliased_date_query_param(query_params, *names):
    for name in names:
        if query_params.get(name) not in (None, ""):
            return get_date_query_param(query_params, name)

    return None


def get_aliased_decimal_query_param(query_params, *names):
    for name in names:
        if query_params.get(name) not in (None, ""):
            return get_decimal_query_param(query_params, name)

    return None


def get_aliased_bool_query_param(query_params, *names):
    for name in names:
        if query_params.get(name) not in (None, ""):
            return get_bool_query_param(query_params, name)

    return None


def get_transaction_type_query_param(query_params):
    value = get_first_query_value(query_params, "type", "kind")

    if value in (None, "", "all"):
        return None

    if query_params.get("type") not in (None, ""):
        return validate_choice_query_param(
            query_params,
            "type",
            TransactionType.values,
        )

    return validate_choice_query_param(
        query_params,
        "kind",
        TransactionType.values,
    )


def get_transaction_ordering_fields(query_params):
    ordering = query_params.get("ordering")

    if ordering:
        return validate_ordering_fields(
            ordering,
            TRANSACTION_SORT_FIELDS,
        )

    sort_by = query_params.get("sortBy") or query_params.get("sort_by")

    if not sort_by:
        return []

    if sort_by not in TRANSACTION_SORT_FIELDS:
        raise ValidationError(
            {
                "sortBy": [
                    (
                        "Недопустимое поле сортировки. "
                        "Поддерживаются: date, description, amount, amountRub, "
                        "category, account, created_at."
                    )
                ]
            }
        )

    sort_dir = query_params.get("sortDir") or query_params.get("sort_dir") or "asc"

    if sort_dir not in TRANSACTION_SORT_DIRECTIONS:
        raise ValidationError(
            {
                "sortDir": [
                    "Направление сортировки должно быть asc или desc."
                ]
            }
        )

    ordering_field = TRANSACTION_SORT_FIELDS[sort_by]

    if sort_dir == "desc":
        ordering_field = f"-{ordering_field}"

    return [
        ordering_field,
        "-created_at",
        "-id",
    ]

def get_transaction_queryset_for_request(request):
    if not request.user.is_authenticated:
        return Transaction.objects.none()

    queryset = (
        Transaction.objects
        .filter(user=request.user)
        .select_related("account", "category")
    )

    query_params = request.query_params

    account_id = get_aliased_int_query_param(
        query_params,
        "account",
        "accountId",
        "account_id",
    )
    category_id = get_aliased_int_query_param(
        query_params,
        "category",
        "categoryId",
        "category_id",
    )
    transaction_type = get_transaction_type_query_param(query_params)
    date_from = get_aliased_date_query_param(
        query_params,
        "date_from",
        "dateFrom",
    )
    date_to = get_aliased_date_query_param(
        query_params,
        "date_to",
        "dateTo",
    )
    amount_min = get_aliased_decimal_query_param(
        query_params,
        "amount_min",
        "amountMin",
    )
    amount_max = get_aliased_decimal_query_param(
        query_params,
        "amount_max",
        "amountMax",
    )
    only_with_comment = get_aliased_bool_query_param(
        query_params,
        "only_with_comment",
        "onlyWithComment",
    )
    search = query_params.get("search")
    ordering_fields = get_transaction_ordering_fields(query_params)

    if (
        amount_min is not None
        and amount_max is not None
        and amount_min > amount_max
    ):
        raise ValidationError(
            {
                "amount_min": [
                    "Параметр amount_min не может быть больше amount_max."
                ]
            }
        )

    if account_id is not None:
        queryset = queryset.filter(account_id=account_id)

    if category_id is not None:
        queryset = queryset.filter(category_id=category_id)

    if transaction_type:
        queryset = queryset.filter(type=transaction_type)

    if date_from:
        queryset = queryset.filter(operation_date__gte=date_from)

    if date_to:
        queryset = queryset.filter(operation_date__lte=date_to)

    if amount_min is not None:
        queryset = queryset.filter(amount__gte=amount_min)

    if amount_max is not None:
        queryset = queryset.filter(amount__lte=amount_max)

    if only_with_comment is True:
        queryset = queryset.exclude(description="")

    if only_with_comment is False:
        queryset = queryset.filter(description="")

    if search:
        search_value = search.strip()

        if len(search_value) > MAX_TRANSACTION_SEARCH_LENGTH:
            raise ValidationError(
                {
                    "search": [
                        (
                            "Параметр search не может быть длиннее "
                            f"{MAX_TRANSACTION_SEARCH_LENGTH} символов."
                        )
                    ]
                }
            )

        if search_value:
            queryset = queryset.filter(
                Q(description__icontains=search_value)
                | Q(category__name__icontains=search_value)
                | Q(account__name__icontains=search_value)
            )

    if ordering_fields:
        queryset = queryset.order_by(*ordering_fields)
    else:
        queryset = queryset.order_by("-operation_date", "-created_at", "-id")

    return queryset

class TransactionExportView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["finance-transactions"],
        summary="Экспортировать список операций",
        description=(
            "Экспортирует операции текущего пользователя с учётом тех же фильтров, "
            "которые используются в списке операций. Поддерживаются форматы CSV, "
            "XLSX и PDF. Для защиты от слишком тяжёлых выгрузок действует лимит "
            f"{MAX_TRANSACTION_EXPORT_ROWS} операций."
        ),
        parameters=[
            OpenApiParameter(
                "format",
                OpenApiTypes.STR,
                description="Формат экспорта: csv, xlsx или pdf.",
                required=True,
            ),
            OpenApiParameter("type", OpenApiTypes.STR),
            OpenApiParameter("kind", OpenApiTypes.STR),
            OpenApiParameter("date_from", OpenApiTypes.DATE),
            OpenApiParameter("dateFrom", OpenApiTypes.DATE),
            OpenApiParameter("date_to", OpenApiTypes.DATE),
            OpenApiParameter("dateTo", OpenApiTypes.DATE),
            OpenApiParameter("account", OpenApiTypes.INT),
            OpenApiParameter("accountId", OpenApiTypes.INT),
            OpenApiParameter("category", OpenApiTypes.INT),
            OpenApiParameter("categoryId", OpenApiTypes.INT),
            OpenApiParameter("amount_min", OpenApiTypes.NUMBER),
            OpenApiParameter("amountMin", OpenApiTypes.NUMBER),
            OpenApiParameter("amount_max", OpenApiTypes.NUMBER),
            OpenApiParameter("amountMax", OpenApiTypes.NUMBER),
            OpenApiParameter("search", OpenApiTypes.STR),
            OpenApiParameter("only_with_comment", OpenApiTypes.BOOL),
            OpenApiParameter("onlyWithComment", OpenApiTypes.BOOL),
            OpenApiParameter("ordering", OpenApiTypes.STR),
            OpenApiParameter("sortBy", OpenApiTypes.STR),
            OpenApiParameter("sortDir", OpenApiTypes.STR),
        ],
        responses={
            200: OpenApiTypes.BINARY,
            400: OpenApiTypes.OBJECT,
        },
    )
    def get(self, request):
        export_format = request.query_params.get("format", "csv").lower()

        if export_format not in TRANSACTION_EXPORT_FORMATS:
            raise ValidationError(
                {
                    "format": [
                        "Формат экспорта должен быть csv, xlsx или pdf."
                    ]
                }
            )

        queryset = get_transaction_queryset_for_request(request)
        total_count = queryset.count()

        if total_count > MAX_TRANSACTION_EXPORT_ROWS:
            raise ValidationError(
                {
                    "detail": (
                        "Экспорт ограничен "
                        f"{MAX_TRANSACTION_EXPORT_ROWS} операциями. "
                        "Уточните фильтры."
                    )
                }
            )

        export_result = build_transaction_export(
            transactions=queryset,
            export_format=export_format,
        )

        response = HttpResponse(
            export_result.content,
            content_type=export_result.content_type,
        )
        response["Content-Disposition"] = (
            f'attachment; filename="{export_result.filename}"'
        )

        return response



@extend_schema_view(
    list=extend_schema(
        tags=["finance-transactions"],
        summary="Получить список операций",
        description=(
            "Возвращает операции текущего пользователя с пагинацией. "
            "Поддерживает backend-параметры и frontend-friendly alias-параметры "
            "для фильтров, поиска и сортировки. Поиск выполняется по описанию "
            "операции, названию категории и названию счёта."
        ),
        parameters=[
            OpenApiParameter(
                "page",
                OpenApiTypes.INT,
                description="Номер страницы. По умолчанию используется первая страница.",
            ),
            OpenApiParameter(
                "page_size",
                OpenApiTypes.INT,
                description="Размер страницы. По умолчанию 20, максимум 100.",
            ),
            OpenApiParameter(
                "limit",
                OpenApiTypes.INT,
                description=(
                    "Frontend-friendly alias для page_size. "
                    "Если pagination-класс поддерживает только page_size, "
                    "используйте page_size."
                ),
            ),
            OpenApiParameter(
                "account",
                OpenApiTypes.INT,
                description="ID счёта.",
            ),
            OpenApiParameter(
                "accountId",
                OpenApiTypes.INT,
                description="Frontend-friendly alias для account.",
            ),
            OpenApiParameter(
                "category",
                OpenApiTypes.INT,
                description="ID категории.",
            ),
            OpenApiParameter(
                "categoryId",
                OpenApiTypes.INT,
                description="Frontend-friendly alias для category.",
            ),
            OpenApiParameter(
                "type",
                OpenApiTypes.STR,
                description="Тип операции: income или expense.",
            ),
            OpenApiParameter(
                "kind",
                OpenApiTypes.STR,
                description=(
                    "Frontend-friendly alias для type. "
                    "Допустимые значения: income, expense, all."
                ),
            ),
            OpenApiParameter(
                "date_from",
                OpenApiTypes.DATE,
                description="Дата начала периода в формате YYYY-MM-DD.",
            ),
            OpenApiParameter(
                "dateFrom",
                OpenApiTypes.DATE,
                description="Frontend-friendly alias для date_from.",
            ),
            OpenApiParameter(
                "date_to",
                OpenApiTypes.DATE,
                description="Дата окончания периода в формате YYYY-MM-DD.",
            ),
            OpenApiParameter(
                "dateTo",
                OpenApiTypes.DATE,
                description="Frontend-friendly alias для date_to.",
            ),
            OpenApiParameter(
                "amount_min",
                OpenApiTypes.NUMBER,
                description="Минимальная сумма операции.",
            ),
            OpenApiParameter(
                "amountMin",
                OpenApiTypes.NUMBER,
                description="Frontend-friendly alias для amount_min.",
            ),
            OpenApiParameter(
                "amount_max",
                OpenApiTypes.NUMBER,
                description="Максимальная сумма операции.",
            ),
            OpenApiParameter(
                "amountMax",
                OpenApiTypes.NUMBER,
                description="Frontend-friendly alias для amount_max.",
            ),
            OpenApiParameter(
                "only_with_comment",
                OpenApiTypes.BOOL,
                description=(
                    "Только операции с непустым описанием. "
                    "Пока отдельного поля comment нет, используется description."
                ),
            ),
            OpenApiParameter(
                "onlyWithComment",
                OpenApiTypes.BOOL,
                description="Frontend-friendly alias для only_with_comment.",
            ),
            OpenApiParameter(
                "search",
                OpenApiTypes.STR,
                description=(
                    "Поиск по описанию операции, названию категории и названию счёта. "
                    "Максимальная длина 100 символов."
                ),
            ),
            OpenApiParameter(
                "ordering",
                OpenApiTypes.STR,
                description=(
                    "Backend-сортировка. Поддерживаются поля: date, operation_date, "
                    "amount, description, category, account, created_at. "
                    "Можно передать несколько полей через запятую, например: "
                    "-operation_date,amount."
                ),
            ),
            OpenApiParameter(
                "sortBy",
                OpenApiTypes.STR,
                description=(
                    "Frontend-friendly поле сортировки. Поддерживаются: "
                    "date, description, amount, amountRub, category, account, created_at."
                ),
            ),
            OpenApiParameter(
                "sortDir",
                OpenApiTypes.STR,
                description="Frontend-friendly направление сортировки: asc или desc.",
            ),
        ],
        responses={200: TransactionSerializer(many=True)},
        examples=[
            OpenApiExample(
                "Список операций",
                value={
                    "count": 1,
                    "next": None,
                    "previous": None,
                    "results": [
                        {
                            "id": 1,
                            "account": 1,
                            "account_name": "Текущий",
                            "account_currency": "RUB",
                            "category": 2,
                            "category_name": "Продукты",
                            "category_icon": "shopping-cart",
                            "category_color": "#10B981",
                            "type": "expense",
                            "kind": "expense",
                            "amount": "1245.00",
                            "amount_abs": "1245.00",
                            "signed_amount": "-1245.00",
                            "description": "Покупка в супермаркете",
                            "operation_date": "2026-05-15",
                            "date": "2026-05-15",
                            "created_at": "2026-05-15T12:00:00+0300",
                            "updated_at": "2026-05-15T12:00:00+0300",
                        }
                    ],
                },
                response_only=True,
            )
        ],
    ),
    create=extend_schema(
        tags=["finance-transactions"],
        summary="Создать операцию",
        description=(
            "Создаёт финансовую операцию текущего пользователя. "
            "Счёт и категория должны принадлежать текущему пользователю. "
            "Тип категории должен совпадать с типом операции."
        ),
        request=TransactionSerializer,
        responses={201: TransactionSerializer},
        examples=[
            OpenApiExample(
                "Создание расходной операции",
                value={
                    "account": 1,
                    "category": 2,
                    "type": "expense",
                    "amount": "1500.00",
                    "description": "Покупка продуктов",
                    "operation_date": "2026-05-15",
                },
                request_only=True,
            )
        ],
    ),
    retrieve=extend_schema(
        tags=["finance-transactions"],
        summary="Получить операцию",
        description="Возвращает одну финансовую операцию текущего пользователя по ID.",
        responses={200: TransactionSerializer},
    ),
    update=extend_schema(
        tags=["finance-transactions"],
        summary="Полностью обновить операцию",
        description=(
            "Полностью обновляет финансовую операцию текущего пользователя. "
            "Endpoint принимает полный набор обязательных полей операции. "
            "Счёт и категория должны принадлежать текущему пользователю, "
            "а тип категории должен совпадать с типом операции."
        ),
        request=TransactionSerializer,
        responses={200: TransactionSerializer},
        examples=[
            OpenApiExample(
                "Полное обновление операции",
                value={
                    "account": 1,
                    "category": 2,
                    "type": "expense",
                    "amount": "1245.00",
                    "description": "Покупка в супермаркете",
                    "operation_date": "2026-05-15",
                },
                request_only=True,
            )
        ],
    ),
    partial_update=extend_schema(
        tags=["finance-transactions"],
        summary="Частично обновить операцию",
        description=(
            "Частично обновляет финансовую операцию. "
            "При смене счёта или категории повторно проверяется владелец, "
            "активность сущностей и соответствие типа категории типу операции."
        ),
        request=TransactionSerializer,
        responses={200: TransactionSerializer},
        examples=[
            OpenApiExample(
                "Обновление описания операции",
                value={
                    "description": "Покупка продуктов и бытовых товаров",
                },
                request_only=True,
            )
        ],
    ),
    destroy=extend_schema(
        tags=["finance-transactions"],
        summary="Удалить операцию",
        description=(
            "Удаляет финансовую операцию текущего пользователя. "
            "Перед удалением влияние операции на баланс счёта откатывается."
        ),
    ),
)
class TransactionViewSet(viewsets.ModelViewSet):
    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated, IsObjectOwner]
    pagination_class = StandardResultsSetPagination
    lookup_value_regex = r"\d+"
    http_method_names = [
        "get",
        "post",
        "put",
        "patch",
        "delete",
        "head",
        "options",
    ]

    def get_queryset(self):
        return get_transaction_queryset_for_request(self.request)

    def perform_create(self, serializer):
        create_transaction_with_balance_update(serializer)

    def perform_update(self, serializer):
        update_transaction_with_balance_update(serializer)

    def perform_destroy(self, instance):
        delete_transaction_with_balance_update(instance)
