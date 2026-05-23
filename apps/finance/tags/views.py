from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.db.models import Q
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiTypes,
    extend_schema,
    extend_schema_view,
)
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.common.domain_errors import DomainConflictError

from apps.finance.models import Account, Category, Tag, Transaction, TransactionType
from apps.finance.tags.serializers import (
    DeleteTagConflictResponseSerializer,
    DeleteTagResponseSerializer,
    MoveTagGroupSerializer,
    RenameTagResponseSerializer,
    RenameTagSerializer,
    SetTagVisibilitySerializer,
    TagSerializer,
    TagsGroupsResponseSerializer,
    TagsListResponseSerializer,
    TagTransactionsReportResponseSerializer,
    TagsMetaResponseSerializer,
    TagsSelectOptionsResponseSerializer,
    ValidateTagResponseSerializer,
    ValidateTagSerializer,
    get_tag_group_payload,
    get_tags_meta_payload,
    serializer_errors_to_field_errors,
    validate_tag_form,
)
from apps.finance.transactions.serializers import TransactionSerializer
from apps.finance.tags.services import (
    MAX_TAG_SEARCH_LENGTH,
    TAG_SORT_FIELDS,
    TAG_SORT_ORDERS,
    build_tags_summary,
    get_accessible_tag_groups,
    get_accessible_tags,
    get_tag_operations_count,
)


MAX_TAG_TRANSACTIONS_REPORT_PAGE_SIZE = 100
DEFAULT_TAG_TRANSACTIONS_REPORT_PAGE_SIZE = 20

TAG_REPORT_SORT_FIELDS = {
    "date": "operation_date",
    "operationDate": "operation_date",
    "operation_date": "operation_date",
    "amount": "amount",
    "description": "description",
    "category": "category__name",
    "categoryName": "category__name",
    "account": "account__name",
    "accountName": "account__name",
    "createdAt": "created_at",
    "created_at": "created_at",
}


def _money(value: Decimal) -> str:
    return str(Decimal(value or "0").quantize(Decimal("0.01")))


def _signed_amount(transaction: Transaction) -> Decimal:
    amount = abs(transaction.amount)
    if transaction.type == TransactionType.EXPENSE:
        return -amount
    return amount


def _empty_money_pair() -> dict:
    return {
        "income": Decimal("0.00"),
        "expense": Decimal("0.00"),
        "transactionsCount": 0,
    }


def _add_transaction_to_bucket(bucket: dict, transaction: Transaction) -> None:
    amount = abs(transaction.amount)
    if transaction.type == TransactionType.INCOME:
        bucket["income"] += amount
    else:
        bucket["expense"] += amount
    bucket["transactionsCount"] += 1


def _bucket_net_amount(bucket: dict) -> Decimal:
    return bucket["income"] - bucket["expense"]


def _bucket_total_abs_amount(bucket: dict) -> Decimal:
    return bucket["income"] + bucket["expense"]


def _percent(part: Decimal, total: Decimal) -> float:
    if total <= 0:
        return 0.0
    return round(float((part / total) * Decimal("100")), 2)


@extend_schema_view(
    list=extend_schema(
        tags=["finance-tags"],
        summary="Получить список тегов операций",
        description=(
            "Возвращает теги текущего пользователя и системные теги. "
            "Список используется на странице централизованного управления "
            "тегами операций, в фильтрах и формах выбора тегов. "
            "Ответ содержит строки тегов, сводку и список групп."
        ),
        parameters=[
            OpenApiParameter(
                "search",
                OpenApiTypes.STR,
                description="Поиск по названию тега, группе или описанию.",
            ),
            OpenApiParameter(
                "groupId",
                OpenApiTypes.INT,
                description="ID группы тегов. Для тегов без группы передайте null или none.",
            ),
            OpenApiParameter(
                "tagIds",
                OpenApiTypes.STR,
                description="Список ID тегов через запятую, например 1,2,3.",
            ),
            OpenApiParameter(
                "onlyWithOperations",
                OpenApiTypes.BOOL,
                description="true - вернуть только теги, связанные хотя бы с одной операцией.",
            ),
            OpenApiParameter(
                "includeHidden",
                OpenApiTypes.BOOL,
                description="true - включить теги, скрытые из форм операций.",
            ),
            OpenApiParameter(
                "sortBy",
                OpenApiTypes.STR,
                description=(
                    "Поле сортировки: name, operationsCount, createdAt, "
                    "updatedAt или isVisible."
                ),
            ),
            OpenApiParameter(
                "sortOrder",
                OpenApiTypes.STR,
                description=(
                    "Порядок сортировки: asc, desc, asc-nulls-first, "
                    "desc-nulls-first, asc-nulls-last, desc-nulls-last."
                ),
            ),
        ],
        responses={200: TagsListResponseSerializer},
        examples=[
            OpenApiExample(
                "Список тегов",
                value={
                    "items": [
                        {
                            "id": 1,
                            "name": "Продукты",
                            "groupId": 1,
                            "groupName": "Покупки",
                            "color": "#66BB6A",
                            "icon": "cart",
                            "operationsCount": 0,
                            "createdAt": "2026-05-21T10:00:00+0300",
                            "updatedAt": "2026-05-21T10:00:00+0300",
                            "isVisible": True,
                            "isSystem": False,
                            "description": "Повседневные покупки продуктов",
                        }
                    ],
                    "summary": {
                        "totalCount": 1,
                        "withOperationsCount": 0,
                        "withoutOperationsCount": 1,
                    },
                    "groups": [
                        {"id": None, "name": "Без группы"},
                        {"id": 1, "name": "Покупки"},
                    ],
                },
                response_only=True,
            )
        ],
    ),
    create=extend_schema(
        tags=["finance-tags"],
        summary="Создать тег операции",
        description=(
            "Создаёт пользовательский тег для операций. Название тега должно "
            "быть уникальным в пределах пользователя с учётом регистра и лишних пробелов."
        ),
        request=TagSerializer,
        responses={201: TagSerializer},
        examples=[
            OpenApiExample(
                "Создание тега",
                value={
                    "name": "Продукты",
                    "groupId": 1,
                    "color": "#66BB6A",
                    "icon": "cart",
                    "isVisible": True,
                    "description": "Повседневные покупки продуктов",
                },
                request_only=True,
            )
        ],
    ),
    retrieve=extend_schema(
        tags=["finance-tags"],
        summary="Получить тег операции",
        description="Возвращает пользовательский или системный тег по ID.",
        responses={200: TagSerializer},
    ),
    update=extend_schema(
        tags=["finance-tags"],
        summary="Полностью обновить тег операции",
        description="Полностью обновляет пользовательский тег операции.",
        request=TagSerializer,
        responses={200: TagSerializer},
    ),
    partial_update=extend_schema(
        tags=["finance-tags"],
        summary="Частично обновить тег операции",
        description=(
            "Частично обновляет пользовательский тег: название, группу, цвет, "
            "иконку, видимость в формах и описание."
        ),
        request=TagSerializer,
        responses={200: TagSerializer},
    ),
    destroy=extend_schema(
        tags=["finance-tags"],
        summary="Удалить тег операции",
        description=(
            "Удаляет пользовательский тег, если он не используется в операциях. "
            "Если тег связан с операциями, API возвращает 409 Conflict и предлагает "
            "скрыть тег из форм вместо удаления."
        ),
        responses={
            200: DeleteTagResponseSerializer,
            409: DeleteTagConflictResponseSerializer,
        },
    ),
)
class TagViewSet(viewsets.ModelViewSet):
    serializer_class = TagSerializer
    permission_classes = [IsAuthenticated]
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
        queryset = get_accessible_tags(self.request.user)

        # Для detail/action endpoints нельзя скрывать is_visible=False теги.
        # Иначе после PATCH /visibility/ false тег становится недоступен
        # для повторного редактирования и обратного PATCH /visibility/ true.
        if self.action != "list":
            return queryset.order_by("name", "id")

        query_params = self.request.query_params

        search = query_params.get("search")
        if search:
            if len(search) > MAX_TAG_SEARCH_LENGTH:
                raise ValidationError(
                    {
                        "search": [
                            f"Поиск не может быть длиннее {MAX_TAG_SEARCH_LENGTH} символов."
                        ]
                    }
                )

            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(description__icontains=search)
                | Q(group__name__icontains=search)
            )

        group_id = query_params.get("groupId") or query_params.get("group_id")
        if group_id not in (None, ""):
            normalized_group_id = str(group_id).strip().lower()

            if normalized_group_id in {"null", "none", "without", "without_group"}:
                queryset = queryset.filter(group__isnull=True)
            else:
                try:
                    queryset = queryset.filter(group_id=int(group_id))
                except (TypeError, ValueError) as exc:
                    raise ValidationError(
                        {"groupId": ["ID группы должен быть целым числом."]}
                    ) from exc

        tag_ids = self._get_int_list_query_param("tagIds", "tag_ids")
        if tag_ids:
            queryset = queryset.filter(pk__in=tag_ids)

        include_hidden = self._get_bool_query_param("includeHidden", "include_hidden")
        if include_hidden is not True:
            queryset = queryset.filter(is_visible=True)

        only_with_operations = self._get_bool_query_param(
            "onlyWithOperations",
            "only_with_operations",
        )
        if only_with_operations is True:
            queryset = queryset.filter(operations_count__gt=0)

        sort_by = query_params.get("sortBy") or query_params.get("sort_by") or "name"
        sort_order = query_params.get("sortOrder") or query_params.get("sort_order") or "asc"

        if sort_by not in TAG_SORT_FIELDS:
            raise ValidationError(
                {
                    "sortBy": [
                        "Допустимые значения: name, operationsCount, createdAt, updatedAt, isVisible."
                    ]
                }
            )

        if sort_order not in TAG_SORT_ORDERS:
            raise ValidationError(
                {
                    "sortOrder": [
                        (
                            "Допустимые значения: asc, desc, asc-nulls-first, "
                            "desc-nulls-first, asc-nulls-last, desc-nulls-last."
                        )
                    ]
                }
            )

        ordering_field = TAG_SORT_FIELDS[sort_by]
        if sort_order.startswith("desc"):
            ordering_field = f"-{ordering_field}"

        return queryset.order_by(ordering_field, "id")

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)

        return Response(
            {
                "items": serializer.data,
                "summary": build_tags_summary(queryset),
                "groups": get_tag_group_payload(request.user, include_empty_group=True),
            }
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance_id = instance.pk

        if instance.is_system:
            raise PermissionDenied("Системный тег нельзя удалить.")

        operations_count = get_tag_operations_count(instance)

        if operations_count > 0:
            raise DomainConflictError(
                code="tag_has_operations",
                message=(
                    "Тег нельзя удалить, так как он используется в операциях. "
                    "Скройте тег из форм, если он больше не нужен для новых операций."
                ),
                detail={
                    "code": "HAS_OPERATIONS",
                    "message": "Тег используется в операциях.",
                    "operationsCount": operations_count,
                    "canHide": True,
                },
            )

        self.perform_destroy(instance)

        return Response(
            {
                "deleted": True,
                "id": instance_id,
            },
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        tags=["finance-tags"],
        summary="Получить группы тегов",
        description="Возвращает системные и пользовательские группы тегов для фильтров и форм.",
        responses={200: TagsGroupsResponseSerializer},
    )
    @action(detail=False, methods=["get"], url_path="groups")
    def groups(self, request):
        return Response(
            {
                "groups": get_tag_group_payload(request.user, include_empty_group=True),
            }
        )

    @extend_schema(
        tags=["finance-tags"],
        summary="Получить теги для селектов",
        description=(
            "Возвращает сокращённый список видимых тегов для форм операций, "
            "шаблонов и фильтров."
        ),
        responses={200: TagsSelectOptionsResponseSerializer},
    )
    @action(detail=False, methods=["get"], url_path="select-options")
    def select_options(self, request):
        queryset = get_accessible_tags(request.user).filter(is_visible=True).order_by(
            "name",
            "id",
        )

        return Response(
            {
                "options": [
                    {
                        "title": tag.name,
                        "value": tag.pk,
                        "color": tag.color,
                        "icon": tag.icon,
                    }
                    for tag in queryset
                ]
            }
        )

    @extend_schema(
        tags=["finance-tags"],
        summary="Получить справочники тегов",
        description="Возвращает группы, цвета и иконки для формы создания и редактирования тега.",
        responses={200: TagsMetaResponseSerializer},
    )
    @action(detail=False, methods=["get"], url_path="meta")
    def meta(self, request):
        return Response(get_tags_meta_payload(request.user))

    @extend_schema(
        tags=["finance-tags"],
        summary="Проверить форму тега",
        description=(
            "Проверяет форму создания или редактирования тега без сохранения. "
            "Используется фронтом для отображения ошибок до отправки основной формы."
        ),
        request=ValidateTagSerializer,
        responses={200: ValidateTagResponseSerializer},
    )
    @action(detail=False, methods=["post"], url_path="validate")
    def validate_form(self, request):
        serializer = ValidateTagSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                {
                    "ok": False,
                    "fieldErrors": serializer_errors_to_field_errors(serializer.errors),
                },
                status=status.HTTP_200_OK,
            )

        field_errors = validate_tag_form(
            user=request.user,
            data=serializer.validated_data,
        )

        return Response(
            {
                "ok": not bool(field_errors),
                "fieldErrors": field_errors,
            }
        )

    @extend_schema(
        tags=["finance-tags"],
        summary="Переименовать тег",
        description="Обновляет только название пользовательского тега.",
        request=RenameTagSerializer,
        responses={200: RenameTagResponseSerializer},
    )
    @action(detail=True, methods=["patch"], url_path="rename")
    def rename(self, request, pk=None):
        tag = self.get_object()
        serializer = RenameTagSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        update_serializer = self.get_serializer(
            tag,
            data={"name": serializer.validated_data["name"]},
            partial=True,
        )
        update_serializer.is_valid(raise_exception=True)
        tag = update_serializer.save()

        return Response(
            {
                "tag": self.get_serializer(tag).data,
                "operationsCount": int(getattr(tag, "operations_count", 0) or 0),
            }
        )

    @extend_schema(
        tags=["finance-tags"],
        summary="Переместить тег в группу",
        description="Обновляет только группу пользовательского тега.",
        request=MoveTagGroupSerializer,
        responses={200: TagSerializer},
    )
    @action(detail=True, methods=["patch"], url_path="group")
    def move_group(self, request, pk=None):
        tag = self.get_object()
        serializer = MoveTagGroupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        group_id = serializer.validated_data.get("groupId")
        group = None

        if group_id is not None:
            try:
                group = get_accessible_tag_groups(request.user).get(pk=group_id)
            except Exception as exc:
                raise ValidationError(
                    {"groupId": ["Выберите существующую группу тегов."]}
                ) from exc

        update_serializer = self.get_serializer(
            tag,
            data={"groupId": group.pk if group else None},
            partial=True,
        )
        update_serializer.is_valid(raise_exception=True)
        tag = update_serializer.save()

        return Response(self.get_serializer(tag).data)

    @extend_schema(
        tags=["finance-tags"],
        summary="Изменить видимость тега",
        description="Скрывает или показывает пользовательский тег в формах операций и фильтрах.",
        request=SetTagVisibilitySerializer,
        responses={200: TagSerializer},
    )
    @action(detail=True, methods=["patch"], url_path="visibility")
    def visibility(self, request, pk=None):
        tag = self.get_object()
        serializer = SetTagVisibilitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        update_serializer = self.get_serializer(
            tag,
            data={"isVisible": serializer.validated_data["isVisible"]},
            partial=True,
        )
        update_serializer.is_valid(raise_exception=True)
        tag = update_serializer.save()

        return Response(self.get_serializer(tag).data)


    @extend_schema(
        tags=["finance-tags"],
        summary="Получить операции и отчёт по тегу",
        description=(
            "Возвращает страницу операций, связанных с выбранным тегом, и связанные "
            "агрегаты: количество операций, суммы доходов и расходов, чистую сумму, "
            "распределение по категориям и счетам, а также динамику по дням. "
            "Endpoint используется для страницы Transactions by Tag. Если операций нет, "
            "возвращается 200 с пустыми items, categories, accounts и dynamics."
        ),
        parameters=[
            OpenApiParameter("dateFrom", OpenApiTypes.DATE, description="Дата начала периода в формате YYYY-MM-DD."),
            OpenApiParameter("dateTo", OpenApiTypes.DATE, description="Дата окончания периода в формате YYYY-MM-DD."),
            OpenApiParameter("type", OpenApiTypes.STR, description="Тип операции: income или expense."),
            OpenApiParameter("kind", OpenApiTypes.STR, description="Alias для type: income, expense или all."),
            OpenApiParameter("accounts", OpenApiTypes.STR, description="ID счетов через запятую, например accounts=1,2."),
            OpenApiParameter("accountIds", OpenApiTypes.STR, description="Alias для accounts."),
            OpenApiParameter("categories", OpenApiTypes.STR, description="ID категорий через запятую, например categories=3,4."),
            OpenApiParameter("categoryIds", OpenApiTypes.STR, description="Alias для categories."),
            OpenApiParameter("search", OpenApiTypes.STR, description="Поиск по описанию операции, категории, счёту и тегам."),
            OpenApiParameter("ordering", OpenApiTypes.STR, description="Сортировка: date, -date, amount, -amount, category, account, createdAt."),
            OpenApiParameter("page", OpenApiTypes.INT, description="Номер страницы. По умолчанию 1."),
            OpenApiParameter("perPage", OpenApiTypes.INT, description="Размер страницы. По умолчанию 20, максимум 100."),
            OpenApiParameter("page_size", OpenApiTypes.INT, description="Backend alias для perPage."),
            OpenApiParameter("limit", OpenApiTypes.INT, description="Frontend alias для perPage."),
        ],
        responses={
            200: TagTransactionsReportResponseSerializer,
            400: OpenApiTypes.OBJECT,
            404: OpenApiTypes.OBJECT,
        },
        examples=[
            OpenApiExample(
                "Отчёт по тегу",
                value={
                    "tag": {
                        "id": 1,
                        "name": "Продукты",
                        "groupId": 1,
                        "groupName": "Покупки",
                        "color": "#66BB6A",
                        "icon": "cart",
                        "isVisible": True,
                    },
                    "summary": {
                        "transactionsCount": 12,
                        "totalIncome": "0.00",
                        "totalExpense": "18600.00",
                        "netAmount": "-18600.00",
                        "averageAmount": "1550.00",
                    },
                    "categories": [
                        {
                            "categoryId": 3,
                            "categoryName": "Продукты",
                            "categoryIcon": "cart",
                            "categoryColor": "#66BB6A",
                            "income": "0.00",
                            "expense": "15600.00",
                            "netAmount": "-15600.00",
                            "transactionsCount": 9,
                            "percent": 83.87,
                        }
                    ],
                    "accounts": [
                        {
                            "accountId": 1,
                            "accountName": "Основная карта",
                            "currency": "RUB",
                            "income": "0.00",
                            "expense": "18600.00",
                            "netAmount": "-18600.00",
                            "transactionsCount": 12,
                            "percent": 100.0,
                        }
                    ],
                    "dynamics": [
                        {
                            "date": "2026-05-01",
                            "income": "0.00",
                            "expense": "1200.00",
                            "netAmount": "-1200.00",
                            "transactionsCount": 1,
                        }
                    ],
                    "items": [],
                    "pagination": {
                        "page": 1,
                        "perPage": 20,
                        "totalItems": 12,
                        "totalPages": 1,
                    },
                },
                response_only=True,
            ),
            OpenApiExample(
                "Пустой отчёт по тегу",
                value={
                    "tag": {
                        "id": 1,
                        "name": "Продукты",
                        "groupId": 1,
                        "groupName": "Покупки",
                        "color": "#66BB6A",
                        "icon": "cart",
                        "isVisible": False,
                    },
                    "summary": {
                        "transactionsCount": 0,
                        "totalIncome": "0.00",
                        "totalExpense": "0.00",
                        "netAmount": "0.00",
                        "averageAmount": "0.00",
                    },
                    "categories": [],
                    "accounts": [],
                    "dynamics": [],
                    "items": [],
                    "pagination": {
                        "page": 1,
                        "perPage": 20,
                        "totalItems": 0,
                        "totalPages": 1,
                    },
                },
                response_only=True,
            ),
            OpenApiExample(
                "Некорректный фильтр отчёта",
                value={
                    "success": False,
                    "error": {
                        "status_code": 400,
                        "code": "validation_error",
                        "message": "Некорректные данные запроса.",
                        "field_errors": {
                            "accounts": [
                                "Некоторые счета не найдены или недоступны текущему пользователю."
                            ]
                        },
                        "detail": None,
                        "trace_id": None,
                    },
                },
                response_only=True,
                status_codes=["400"],
            ),
            OpenApiExample(
                "Тег не найден или недоступен",
                value={
                    "success": False,
                    "error": {
                        "status_code": 404,
                        "code": "not_found",
                        "message": "Объект не найден.",
                        "field_errors": None,
                        "detail": "No Tag matches the given query.",
                        "trace_id": None,
                    },
                },
                response_only=True,
                status_codes=["404"],
            ),
        ],
    )
    @action(detail=True, methods=["get"], url_path="transactions")
    def transactions(self, request, pk=None):
        tag = self.get_object()
        queryset = self._get_tag_transactions_queryset(tag)
        all_transactions = list(queryset)
        page, per_page = self._get_report_pagination_params()
        total_items = len(all_transactions)
        total_pages = max((total_items + per_page - 1) // per_page, 1)

        if page > total_pages:
            raise ValidationError({"page": ["Запрошенная страница находится за пределами результата."]})

        offset = (page - 1) * per_page
        page_transactions = all_transactions[offset:offset + per_page]

        return Response(
            {
                "tag": self._build_tag_report_payload(tag),
                "summary": self._build_tag_transactions_summary(all_transactions),
                "categories": self._build_tag_transactions_categories(all_transactions),
                "accounts": self._build_tag_transactions_accounts(all_transactions),
                "dynamics": self._build_tag_transactions_dynamics(all_transactions),
                "items": TransactionSerializer(
                    page_transactions,
                    many=True,
                    context={"request": request},
                ).data,
                "pagination": {
                    "page": page,
                    "perPage": per_page,
                    "totalItems": total_items,
                    "totalPages": total_pages,
                },
            }
        )

    def _get_tag_transactions_queryset(self, tag: Tag):
        query_params = self.request.query_params
        queryset = (
            Transaction.objects
            .filter(user=self.request.user, tags=tag)
            .select_related("account", "category")
            .prefetch_related("tags__group")
        )

        date_from = self._get_date_query_param("dateFrom", "date_from")
        date_to = self._get_date_query_param("dateTo", "date_to")

        if date_from and date_to and date_from > date_to:
            raise ValidationError({"dateFrom": ["Дата начала не может быть позже даты окончания."]})

        transaction_type = self._get_transaction_type_query_param()
        account_ids = self._get_int_list_query_param("accounts", "accountIds", "account_ids")
        category_ids = self._get_int_list_query_param("categories", "categoryIds", "category_ids")
        self._validate_report_related_filters(
            account_ids=account_ids,
            category_ids=category_ids,
        )
        search = query_params.get("search")
        ordering = self._get_report_ordering()

        if date_from:
            queryset = queryset.filter(operation_date__gte=date_from)

        if date_to:
            queryset = queryset.filter(operation_date__lte=date_to)

        if transaction_type:
            queryset = queryset.filter(type=transaction_type)

        if account_ids:
            queryset = queryset.filter(account_id__in=account_ids)

        if category_ids:
            queryset = queryset.filter(category_id__in=category_ids)

        if search:
            search_value = search.strip()

            if len(search_value) > MAX_TAG_SEARCH_LENGTH:
                raise ValidationError({"search": [f"Поиск не может быть длиннее {MAX_TAG_SEARCH_LENGTH} символов."]})

            if search_value:
                queryset = queryset.filter(
                    Q(description__icontains=search_value)
                    | Q(account__name__icontains=search_value)
                    | Q(category__name__icontains=search_value)
                    | Q(tags__name__icontains=search_value)
                ).distinct()

        return queryset.order_by(*ordering)


    def _validate_report_related_filters(
        self,
        *,
        account_ids: list[int],
        category_ids: list[int],
    ) -> None:
        """
        Проверяет, что фильтры отчёта ссылаются только на сущности текущего пользователя.

        Без этой проверки чужие или несуществующие счета/категории просто давали бы
        пустой отчёт. Для страницы Transactions by Tag это плохой UX: фронт не сможет
        отличить реальное отсутствие операций от некорректного фильтра.
        """
        field_errors: dict[str, list[str]] = {}

        if account_ids:
            existing_account_ids = set(
                Account.objects.filter(
                    user=self.request.user,
                    pk__in=account_ids,
                ).values_list("pk", flat=True)
            )
            missing_account_ids = sorted(set(account_ids) - existing_account_ids)

            if missing_account_ids:
                field_errors["accounts"] = [
                    "Некоторые счета не найдены или недоступны текущему пользователю."
                ]

        if category_ids:
            existing_category_ids = set(
                Category.objects.filter(
                    user=self.request.user,
                    pk__in=category_ids,
                ).values_list("pk", flat=True)
            )
            missing_category_ids = sorted(set(category_ids) - existing_category_ids)

            if missing_category_ids:
                field_errors["categories"] = [
                    "Некоторые категории не найдены или недоступны текущему пользователю."
                ]

        if field_errors:
            raise ValidationError(field_errors)

    def _get_date_query_param(self, *names: str):
        from django.utils.dateparse import parse_date

        for name in names:
            value = self.request.query_params.get(name)

            if value not in (None, ""):
                parsed_value = parse_date(value)

                if parsed_value is None:
                    raise ValidationError({name: ["Дата должна быть в формате YYYY-MM-DD."]})

                return parsed_value

        return None

    def _get_transaction_type_query_param(self) -> str | None:
        value = None
        used_name = "type"

        for name in ("type", "kind"):
            candidate = self.request.query_params.get(name)

            if candidate not in (None, ""):
                value = candidate
                used_name = name
                break

        if value in (None, "", "all"):
            return None

        if value not in TransactionType.values:
            raise ValidationError({used_name: ["Допустимые значения: income, expense или all."]})

        return value

    def _get_report_ordering(self) -> list[str]:
        ordering = self.request.query_params.get("ordering") or "-date"
        result = []

        for raw_field in ordering.split(","):
            field = raw_field.strip()

            if not field:
                continue

            direction = ""
            if field.startswith("-"):
                direction = "-"
                field = field[1:]

            if field not in TAG_REPORT_SORT_FIELDS:
                allowed_values = sorted(
                    list(TAG_REPORT_SORT_FIELDS.keys())
                    + [f"-{allowed_field}" for allowed_field in TAG_REPORT_SORT_FIELDS.keys()]
                )
                raise ValidationError(
                    {"ordering": ["Допустимые значения: " + ", ".join(allowed_values) + "."]}
                )

            result.append(f"{direction}{TAG_REPORT_SORT_FIELDS[field]}")

        return result or ["-operation_date", "-created_at", "-id"]

    def _get_report_pagination_params(self) -> tuple[int, int]:
        page = self._get_positive_int_query_param("page", default=1)
        per_page = self._get_positive_int_query_param(
            "perPage",
            "page_size",
            "limit",
            default=DEFAULT_TAG_TRANSACTIONS_REPORT_PAGE_SIZE,
        )

        if per_page > MAX_TAG_TRANSACTIONS_REPORT_PAGE_SIZE:
            per_page = MAX_TAG_TRANSACTIONS_REPORT_PAGE_SIZE

        return page, per_page

    def _get_positive_int_query_param(self, *names: str, default: int) -> int:
        for name in names:
            value = self.request.query_params.get(name)

            if value not in (None, ""):
                try:
                    parsed_value = int(value)
                except (TypeError, ValueError) as exc:
                    raise ValidationError({name: ["Параметр должен быть положительным целым числом."]}) from exc

                if parsed_value <= 0:
                    raise ValidationError({name: ["Параметр должен быть положительным целым числом."]})

                return parsed_value

        return default

    def _build_tag_report_payload(self, tag: Tag) -> dict:
        return {
            "id": tag.pk,
            "name": tag.name,
            "groupId": tag.group_id,
            "groupName": tag.group.name if tag.group_id else "Без группы",
            "color": tag.color,
            "icon": tag.icon,
            "isVisible": tag.is_visible,
        }

    def _build_tag_transactions_summary(self, transactions: list[Transaction]) -> dict:
        income = Decimal("0.00")
        expense = Decimal("0.00")

        for transaction in transactions:
            amount = abs(transaction.amount)
            if transaction.type == TransactionType.INCOME:
                income += amount
            else:
                expense += amount

        total_count = len(transactions)
        total_abs_amount = income + expense
        average_amount = total_abs_amount / total_count if total_count else Decimal("0.00")

        return {
            "transactionsCount": total_count,
            "totalIncome": _money(income),
            "totalExpense": _money(expense),
            "netAmount": _money(income - expense),
            "averageAmount": _money(average_amount),
        }

    def _build_tag_transactions_categories(self, transactions: list[Transaction]) -> list[dict]:
        buckets = defaultdict(_empty_money_pair)

        for transaction in transactions:
            category = transaction.category
            key = category.pk if category else None
            bucket = buckets[key]
            bucket["categoryId"] = category.pk if category else None
            bucket["categoryName"] = category.name if category else "Без категории"
            bucket["categoryIcon"] = category.icon if category else ""
            bucket["categoryColor"] = category.color if category else ""
            _add_transaction_to_bucket(bucket, transaction)

        total_amount = sum(_bucket_total_abs_amount(bucket) for bucket in buckets.values())

        result = []
        for bucket in buckets.values():
            result.append(
                {
                    "categoryId": bucket["categoryId"],
                    "categoryName": bucket["categoryName"],
                    "categoryIcon": bucket["categoryIcon"],
                    "categoryColor": bucket["categoryColor"],
                    "income": _money(bucket["income"]),
                    "expense": _money(bucket["expense"]),
                    "netAmount": _money(_bucket_net_amount(bucket)),
                    "transactionsCount": bucket["transactionsCount"],
                    "percent": _percent(_bucket_total_abs_amount(bucket), total_amount),
                }
            )

        return sorted(result, key=lambda item: (-item["transactionsCount"], item["categoryName"]))

    def _build_tag_transactions_accounts(self, transactions: list[Transaction]) -> list[dict]:
        buckets = defaultdict(_empty_money_pair)

        for transaction in transactions:
            account = transaction.account
            key = account.pk if account else None
            bucket = buckets[key]
            bucket["accountId"] = account.pk if account else None
            bucket["accountName"] = account.name if account else "Без счёта"
            bucket["currency"] = account.currency if account else "RUB"
            _add_transaction_to_bucket(bucket, transaction)

        total_amount = sum(_bucket_total_abs_amount(bucket) for bucket in buckets.values())

        result = []
        for bucket in buckets.values():
            result.append(
                {
                    "accountId": bucket["accountId"],
                    "accountName": bucket["accountName"],
                    "currency": bucket["currency"],
                    "income": _money(bucket["income"]),
                    "expense": _money(bucket["expense"]),
                    "netAmount": _money(_bucket_net_amount(bucket)),
                    "transactionsCount": bucket["transactionsCount"],
                    "percent": _percent(_bucket_total_abs_amount(bucket), total_amount),
                }
            )

        return sorted(result, key=lambda item: (-item["transactionsCount"], item["accountName"]))

    def _build_tag_transactions_dynamics(self, transactions: list[Transaction]) -> list[dict]:
        buckets = defaultdict(_empty_money_pair)

        for transaction in transactions:
            bucket = buckets[transaction.operation_date]
            _add_transaction_to_bucket(bucket, transaction)

        result = []
        for operation_date, bucket in sorted(buckets.items(), key=lambda item: item[0]):
            result.append(
                {
                    "date": operation_date.isoformat(),
                    "income": _money(bucket["income"]),
                    "expense": _money(bucket["expense"]),
                    "netAmount": _money(_bucket_net_amount(bucket)),
                    "transactionsCount": bucket["transactionsCount"],
                }
            )

        return result

    def _get_bool_query_param(self, *names: str) -> bool | None:
        for name in names:
            value = self.request.query_params.get(name)

            if value not in (None, ""):
                normalized_value = str(value).strip().lower()

                if normalized_value in {"true", "1", "yes"}:
                    return True

                if normalized_value in {"false", "0", "no"}:
                    return False

                raise ValidationError(
                    {names[0]: ["Значение должно быть true или false."]}
                )

        return None

    def _get_int_list_query_param(self, *names: str) -> list[int]:
        raw_values = []

        for name in names:
            for raw_value in self.request.query_params.getlist(name):
                raw_values.extend(
                    value.strip()
                    for value in str(raw_value).split(",")
                    if value.strip()
                )

            for raw_value in self.request.query_params.getlist(f"{name}[]"):
                raw_values.extend(
                    value.strip()
                    for value in str(raw_value).split(",")
                    if value.strip()
                )

        result = []

        for raw_value in raw_values:
            try:
                result.append(int(raw_value))
            except (TypeError, ValueError) as exc:
                raise ValidationError(
                    {names[0]: ["Значения фильтра должны быть целыми числами."]}
                ) from exc

        return result
