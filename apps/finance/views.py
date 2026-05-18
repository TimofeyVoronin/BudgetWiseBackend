from django.db.models import Count, Q
from django.http import HttpResponse
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiTypes,
    extend_schema,
    extend_schema_view,
)
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.exceptions import ConflictError
from apps.common.pagination import StandardResultsSetPagination
from apps.common.validation import (
    get_bool_query_param,
    get_date_query_param,
    get_decimal_query_param,
    get_int_query_param,
    validate_choice_query_param,
    validate_ordering,
    validate_ordering_fields,
)
from apps.finance.exporters import (
    TRANSACTION_EXPORT_FORMATS,
    build_transaction_export,
)
from apps.finance.dashboard import (
    DASHBOARD_PERIOD_CUSTOM,
    DASHBOARD_PERIOD_TYPES,
    DEFAULT_DASHBOARD_CURRENCY,
    DEFAULT_DASHBOARD_PERIOD,
    DEFAULT_DASHBOARD_RECENT_LIMIT,
    MAX_DASHBOARD_RECENT_LIMIT,
    build_dashboard_summary,
)
from apps.finance.models import Category, Transaction, TransactionType
from apps.finance.permissions import IsObjectOwner
from apps.finance.serializers import (
    CategoryArchiveSerializer,
    CategoryFavoriteSerializer,
    CategoryReorderSerializer,
    CategorySerializer,
    CategorySuggestSerializer,
    CategoryTreeSerializer,
    TransactionSerializer,
    DashboardSummarySerializer,
)


MAX_CATEGORY_SEARCH_LENGTH = 100
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


def get_dashboard_recent_limit(query_params) -> int:
    value = query_params.get("limit")

    if value in (None, ""):
        return DEFAULT_DASHBOARD_RECENT_LIMIT

    limit = get_int_query_param(query_params, "limit")

    if limit < 1 or limit > MAX_DASHBOARD_RECENT_LIMIT:
        raise ValidationError(
            {
                "limit": [
                    (
                        "Параметр limit должен быть от 1 до "
                        f"{MAX_DASHBOARD_RECENT_LIMIT}."
                    )
                ]
            }
        )

    return limit


def get_dashboard_period_query_param(query_params) -> str:
    period = query_params.get("period") or DEFAULT_DASHBOARD_PERIOD

    if period not in DASHBOARD_PERIOD_TYPES:
        raise ValidationError(
            {
                "period": [
                    "Параметр period должен быть week, month, year или custom."
                ]
            }
        )

    return period


def get_dashboard_currency_query_param(query_params) -> str:
    currency = query_params.get("currency") or DEFAULT_DASHBOARD_CURRENCY
    currency = currency.upper()

    if len(currency) != 3 or not currency.isalpha():
        raise ValidationError(
            {
                "currency": [
                    "Параметр currency должен быть ISO-кодом из 3 букв, например RUB."
                ]
            }
        )

    return currency


def get_dashboard_date_range_query_params(query_params, period: str):
    date_from = get_date_query_param(query_params, "date_from")
    date_to = get_date_query_param(query_params, "date_to")

    if period == DASHBOARD_PERIOD_CUSTOM and (date_from is None or date_to is None):
        raise ValidationError(
            {
                "date_from": [
                    "Для period=custom нужно указать date_from и date_to."
                ]
            }
        )

    if date_from is not None and date_to is not None and date_from > date_to:
        raise ValidationError(
            {
                "date_from": [
                    "Параметр date_from не может быть позже date_to."
                ]
            }
        )

    return date_from, date_to


def get_dashboard_query_params(query_params) -> dict:
    period = get_dashboard_period_query_param(query_params)
    date_from, date_to = get_dashboard_date_range_query_params(
        query_params,
        period,
    )

    return {
        "period_type": period,
        "date_from": date_from,
        "date_to": date_to,
        "currency": get_dashboard_currency_query_param(query_params),
        "recent_limit": get_dashboard_recent_limit(query_params),
    }


@extend_schema_view(
    list=extend_schema(
        tags=["finance"],
        summary="Получить список категорий",
        description=(
            "Возвращает категории текущего пользователя с пагинацией. "
            "Поддерживает фильтрацию по типу, родителю, активности, архиву, "
            "избранному и поиску по названию. Используется для таблиц, списков "
            "и форм выбора категории на фронте."
        ),
        parameters=[
            OpenApiParameter(
                "type",
                OpenApiTypes.STR,
                description="Тип категории: income или expense.",
            ),
            OpenApiParameter(
                "parent",
                OpenApiTypes.INT,
                description="ID родительской категории.",
            ),
            OpenApiParameter(
                "root",
                OpenApiTypes.BOOL,
                description=(
                    "Фильтр по уровню иерархии. "
                    "true - только корневые категории, false - только дочерние."
                ),
            ),
            OpenApiParameter(
                "is_active",
                OpenApiTypes.BOOL,
                description=(
                    "Фильтр по активности категории. "
                    "true - только активные, false - только неактивные."
                ),
            ),
            OpenApiParameter(
                "is_archived",
                OpenApiTypes.BOOL,
                description=(
                    "Фильтр по архивному состоянию категории. "
                    "true - только архивные, false - только неархивные."
                ),
            ),
            OpenApiParameter(
                "is_favorite",
                OpenApiTypes.BOOL,
                description=(
                    "Фильтр по избранным категориям. "
                    "true - только избранные, false - только не избранные."
                ),
            ),
            OpenApiParameter(
                "search",
                OpenApiTypes.STR,
                description=(
                    "Поиск по названию категории. "
                    "Максимальная длина 100 символов."
                ),
            ),
            OpenApiParameter(
                "ordering",
                OpenApiTypes.STR,
                description=(
                    "Сортировка категорий. Поддерживаются поля: name, type, "
                    "sort_order, created_at, updated_at. "
                    "Для сортировки по убыванию используйте префикс '-'."
                ),
            ),
        ],
        responses={200: CategorySerializer(many=True)},
        examples=[
            OpenApiExample(
                "Список активных расходных категорий",
                value={
                    "count": 2,
                    "next": None,
                    "previous": None,
                    "results": [
                        {
                            "id": 1,
                            "parent": None,
                            "name": "Продукты",
                            "type": "expense",
                            "icon": "shopping-cart",
                            "color": "#10B981",
                            "sort_order": 0,
                            "is_favorite": True,
                            "is_archived": False,
                            "is_active": True,
                            "children_count": 1,
                            "budgets_count": 1,
                            "active_budgets_count": 1,
                            "is_available_for_budget": True,
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
        tags=["finance"],
        summary="Создать категорию",
        description=(
            "Создаёт категорию доходов или расходов для текущего пользователя. "
            "Категория может быть корневой или дочерней. Родительская категория "
            "должна принадлежать тому же пользователю и иметь тот же тип."
        ),
        request=CategorySerializer,
        responses={201: CategorySerializer},
        examples=[
            OpenApiExample(
                "Создание категории расходов",
                value={
                    "parent": None,
                    "name": "Кафе и рестораны",
                    "type": "expense",
                    "icon": "utensils",
                    "color": "#F59E0B",
                    "sort_order": 10,
                    "is_favorite": False,
                    "is_archived": False,
                    "is_active": True,
                },
                request_only=True,
            )
        ],
    ),
    retrieve=extend_schema(
        tags=["finance"],
        summary="Получить категорию",
        description="Возвращает одну категорию текущего пользователя по ID.",
        responses={200: CategorySerializer},
    ),
    update=extend_schema(
        tags=["finance"],
        summary="Полностью обновить категорию",
        description=(
            "Полностью обновляет категорию текущего пользователя. "
            "При изменении родителя проверяется владелец, тип категории "
            "и отсутствие циклов в иерархии."
        ),
        request=CategorySerializer,
        responses={200: CategorySerializer},
    ),
    partial_update=extend_schema(
        tags=["finance"],
        summary="Частично обновить категорию",
        description=(
            "Частично обновляет категорию текущего пользователя. "
            "Подходит для изменения названия, иконки, цвета, родителя, "
            "активности и порядка сортировки."
        ),
        request=CategorySerializer,
        responses={200: CategorySerializer},
        examples=[
            OpenApiExample(
                "Обновление категории",
                value={
                    "name": "Кафе, рестораны и доставка",
                    "icon": "coffee",
                    "color": "#EF4444",
                    "parent": None,
                },
                request_only=True,
            )
        ],
    ),
    destroy=extend_schema(
        tags=["finance"],
        summary="Удалить категорию",
        description=(
            "Удаляет категорию текущего пользователя. Удаление запрещено, "
            "если у категории есть дочерние категории, операции или бюджеты. "
            "В таких случаях API возвращает 409 Conflict."
        ),
    ),
)
class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated, IsObjectOwner]
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
        if not self.request.user.is_authenticated:
            return Category.objects.none()

        queryset = (
            Category.objects
            .filter(user=self.request.user)
            .annotate(
                budget_count=Count("budgets", distinct=True),
                active_budget_count=Count(
                    "budgets",
                    filter=Q(budgets__is_active=True),
                    distinct=True,
                ),
            )
        )

        category_type = validate_choice_query_param(
            self.request.query_params,
            "type",
            TransactionType.values,
        )
        parent_id = get_int_query_param(self.request.query_params, "parent")
        root = get_bool_query_param(self.request.query_params, "root")
        is_active = get_bool_query_param(self.request.query_params, "is_active")
        is_archived = get_bool_query_param(
            self.request.query_params,
            "is_archived",
        )
        is_favorite = get_bool_query_param(
            self.request.query_params,
            "is_favorite",
        )
        search = self.request.query_params.get("search")
        ordering = validate_ordering(
            self.request.query_params.get("ordering"),
            {
                "name",
                "-name",
                "type",
                "-type",
                "sort_order",
                "-sort_order",
                "created_at",
                "-created_at",
                "updated_at",
                "-updated_at",
            },
        )

        if category_type:
            queryset = queryset.filter(type=category_type)

        if parent_id is not None:
            queryset = queryset.filter(parent_id=parent_id)

        if root is True:
            queryset = queryset.filter(parent__isnull=True)

        if root is False:
            queryset = queryset.filter(parent__isnull=False)

        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)

        if is_archived is not None:
            queryset = queryset.filter(is_archived=is_archived)

        if is_favorite is not None:
            queryset = queryset.filter(is_favorite=is_favorite)

        if search:
            search_value = search.strip()

            if len(search_value) > MAX_CATEGORY_SEARCH_LENGTH:
                raise ValidationError(
                    {
                        "search": [
                            (
                                "Параметр search не может быть длиннее "
                                f"{MAX_CATEGORY_SEARCH_LENGTH} символов."
                            )
                        ]
                    }
                )

            if search_value:
                queryset = queryset.filter(name__icontains=search_value)

        if ordering:
            queryset = queryset.order_by(ordering)
        else:
            queryset = queryset.order_by(
                "type",
                "parent_id",
                "sort_order",
                "name",
                "id",
            )

        return queryset

    @extend_schema(
        tags=["finance"],
        summary="Получить дерево категорий",
        description=(
            "Возвращает дерево категорий текущего пользователя. "
            "В ответ попадают только корневые категории, а дочерние категории "
            "возвращаются во вложенном поле children. Endpoint используется "
            "для древовидного отображения категорий на фронте."
        ),
        parameters=[
            OpenApiParameter(
                "type",
                OpenApiTypes.STR,
                description="Тип категории: income или expense.",
            ),
            OpenApiParameter(
                "is_active",
                OpenApiTypes.BOOL,
                description=(
                    "Фильтр по активности категории. "
                    "true - только активные, false - только неактивные."
                ),
            ),
            OpenApiParameter(
                "is_archived",
                OpenApiTypes.BOOL,
                description=(
                    "Фильтр по архивному состоянию категории. "
                    "true - только архивные, false - только неархивные."
                ),
            ),
            OpenApiParameter(
                "is_favorite",
                OpenApiTypes.BOOL,
                description=(
                    "Фильтр по избранным категориям. "
                    "true - только избранные, false - только не избранные."
                ),
            ),
            OpenApiParameter(
                "search",
                OpenApiTypes.STR,
                description=(
                    "Поиск по названию корневой категории. "
                    "Максимальная длина 100 символов."
                ),
            ),
        ],
        responses={200: CategoryTreeSerializer(many=True)},
        examples=[
            OpenApiExample(
                "Дерево категорий расходов",
                value=[
                    {
                        "id": 1,
                        "parent": None,
                        "name": "Продукты",
                        "type": "expense",
                        "icon": "shopping-cart",
                        "color": "#10B981",
                        "sort_order": 0,
                        "is_favorite": True,
                        "is_archived": False,
                        "is_active": True,
                        "budgets_count": 1,
                        "active_budgets_count": 1,
                        "is_available_for_budget": True,
                        "children": [
                            {
                                "id": 2,
                                "parent": 1,
                                "name": "Супермаркеты",
                                "type": "expense",
                                "icon": "store",
                                "color": "#4F46E5",
                                "sort_order": 0,
                                "is_favorite": False,
                                "is_archived": False,
                                "is_active": True,
                                "budgets_count": 0,
                                "active_budgets_count": 0,
                                "is_available_for_budget": True,
                                "children": [],
                                "created_at": "2026-05-15T12:00:00+0300",
                                "updated_at": "2026-05-15T12:00:00+0300",
                            }
                        ],
                        "created_at": "2026-05-15T12:00:00+0300",
                        "updated_at": "2026-05-15T12:00:00+0300",
                    }
                ],
                response_only=True,
            )
        ],
    )
    @action(detail=False, methods=["get"], url_path="tree")
    def tree(self, request):
        queryset = (
            self.get_queryset()
            .filter(parent__isnull=True)
            .order_by("type", "sort_order", "name", "id")
        )
        serializer = CategoryTreeSerializer(
            queryset,
            many=True,
            context=self.get_serializer_context(),
        )
        return Response(serializer.data)

    @extend_schema(
        tags=["finance"],
        summary="Изменить признак избранной категории",
        description=(
            "Добавляет категорию в избранное или удаляет её из избранного. "
            "Используется для быстрого доступа к часто используемым категориям."
        ),
        request=CategoryFavoriteSerializer,
        responses={200: CategoryFavoriteSerializer},
        examples=[
            OpenApiExample(
                "Добавить категорию в избранное",
                value={
                    "favorite": True,
                },
                request_only=True,
            ),
            OpenApiExample(
                "Успешный ответ",
                value={
                    "id": 1,
                    "is_favorite": True,
                    "detail": "Категория добавлена в избранное.",
                },
                response_only=True,
            ),
        ],
    )
    @action(detail=True, methods=["patch"], url_path="favorite")
    def favorite(self, request, pk=None):
        instance = self.get_object()
        serializer = CategoryFavoriteSerializer(
            instance=instance,
            data=request.data,
            context=self.get_serializer_context(),
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data)

    @extend_schema(
        tags=["finance"],
        summary="Архивировать или восстановить категорию",
        description=(
            "Архивирует категорию или восстанавливает её из архива. "
            "При архивировании категория также становится неактивной. "
            "Архивные категории не предлагаются для новых операций и бюджетов. "
            "Если тело запроса пустое, категория архивируется. "
            "Для восстановления передайте archived=false."
        ),
        request=CategoryArchiveSerializer,
        responses={200: CategoryArchiveSerializer},
        examples=[
            OpenApiExample(
                "Архивировать категорию",
                value={
                    "archived": True,
                },
                request_only=True,
            ),
            OpenApiExample(
                "Восстановить категорию",
                value={
                    "archived": False,
                },
                request_only=True,
            ),
            OpenApiExample(
                "Успешный ответ",
                value={
                    "id": 1,
                    "is_archived": True,
                    "is_active": False,
                    "budgets_count": 1,
                    "active_budgets_count": 1,
                    "detail": "Категория отправлена в архив.",
                },
                response_only=True,
            ),
        ],
    )
    @action(detail=True, methods=["post"], url_path="archive")
    def archive(self, request, pk=None):
        instance = self.get_object()
        serializer = CategoryArchiveSerializer(
            instance=instance,
            data=request.data,
            context=self.get_serializer_context(),
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data)

    @extend_schema(
        tags=["finance"],
        summary="Изменить порядок и иерархию категорий",
        description=(
            "Endpoint используется после drag and drop на фронте. "
            "Поддерживает backend-формат parent/sort_order и frontend-формат "
            "parentId/position. Все категории в order должны принадлежать "
            "текущему пользователю и иметь один тип."
        ),
        request=CategoryReorderSerializer,
        responses={200: CategoryReorderSerializer},
        examples=[
            OpenApiExample(
                "Frontend-формат reorder",
                value={
                    "kind": "expense",
                    "order": [
                        {
                            "id": 1,
                            "parentId": None,
                            "position": 0,
                        },
                        {
                            "id": 2,
                            "parentId": 1,
                            "position": 0,
                        },
                    ],
                },
                request_only=True,
            ),
            OpenApiExample(
                "Успешный ответ",
                value={
                    "detail": "Порядок категорий обновлён.",
                    "updated_count": 2,
                },
                response_only=True,
            ),
        ],
    )
    @action(detail=False, methods=["put"], url_path="reorder")
    def reorder(self, request):
        serializer = CategoryReorderSerializer(
            data=request.data,
            context=self.get_serializer_context(),
        )
        serializer.is_valid(raise_exception=True)
        result = serializer.save()

        return Response(result)

    @extend_schema(
        tags=["finance"],
        summary="Получить подсказки категорий по описанию операции",
        description=(
            "Интеграционная точка для smart categorization. "
            "Endpoint использует простой rule-based алгоритм по названию "
            "категории и ключевым словам. Возвращаются только активные "
            "и неархивные категории текущего пользователя. Можно передавать "
            "type или frontend-поле kind."
        ),
        request=CategorySuggestSerializer,
        responses={200: CategorySuggestSerializer},
        examples=[
            OpenApiExample(
                "Подбор категории по описанию",
                value={
                    "description": "Покупка продуктов в пятерочке",
                    "type": "expense",
                    "limit": 3,
                },
                request_only=True,
            ),
            OpenApiExample(
                "Frontend-вариант с kind",
                value={
                    "description": "Такси до университета",
                    "kind": "expense",
                    "limit": 3,
                },
                request_only=True,
            ),
            OpenApiExample(
                "Успешный ответ",
                value={
                    "suggestions": [
                        {
                            "id": 1,
                            "category": 1,
                            "parent": None,
                            "name": "Продукты",
                            "type": "expense",
                            "icon": "shopping-cart",
                            "color": "#10B981",
                            "confidence": 0.92,
                            "reason": (
                                "Найдено совпадение по ключевому слову: продукт."
                            ),
                            "matched_keyword": "продукт",
                        }
                    ]
                },
                response_only=True,
            ),
        ],
    )
    @action(detail=False, methods=["post"], url_path="suggest")
    def suggest(self, request):
        serializer = CategorySuggestSerializer(
            data=request.data,
            context=self.get_serializer_context(),
        )
        serializer.is_valid(raise_exception=True)
        result = serializer.save()

        return Response(result)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()

        if instance.children.exists():
            raise ConflictError(
                {
                    "detail": (
                        "Категорию нельзя удалить, так как у неё есть "
                        "дочерние категории."
                    ),
                    "code": "category_has_children",
                }
            )

        if instance.transactions.exists():
            raise ConflictError(
                {
                    "detail": (
                        "Категорию нельзя удалить, так как она используется "
                        "в операциях."
                    ),
                    "code": "category_has_transactions",
                }
            )

        if instance.budgets.exists():
            raise ConflictError(
                {
                    "detail": (
                        "Категорию нельзя удалить, так как она используется "
                        "в бюджетах."
                    ),
                    "code": "category_has_budgets",
                }
            )

        return super().destroy(request, *args, **kwargs)


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


class DashboardSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["finance"],
        summary="Получить агрегированные данные главного дашборда",
        description=(
            "Возвращает основные агрегаты для главной страницы: общий баланс "
            "активных счетов, сумму доходов и расходов за текущий месяц, "
            "чистый результат, последние операции и топ категорий расходов. "
            "Блок reminders зарезервирован для будущего эпика напоминаний "
            "и пока возвращается с пустым списком rows."
        ),
        parameters=[
            OpenApiParameter(
                "period",
                OpenApiTypes.STR,
                description=(
                    "Период dashboard: week, month, year или custom. "
                    "По умолчанию month."
                ),
            ),
            OpenApiParameter(
                "date_from",
                OpenApiTypes.DATE,
                description=(
                    "Дата начала периода. Обязательна для period=custom."
                ),
            ),
            OpenApiParameter(
                "date_to",
                OpenApiTypes.DATE,
                description=(
                    "Дата окончания периода. Обязательна для period=custom."
                ),
            ),
            OpenApiParameter(
                "currency",
                OpenApiTypes.STR,
                description=(
                    "Валюта dashboard, например RUB. Конвертация валют не выполняется, "
                    "данные фильтруются по валюте счёта."
                ),
            ),
            OpenApiParameter(
                "limit",
                OpenApiTypes.INT,
                description=(
                    "Количество последних операций в блоке recent_transactions. "
                    f"По умолчанию {DEFAULT_DASHBOARD_RECENT_LIMIT}, "
                    f"максимум {MAX_DASHBOARD_RECENT_LIMIT}."
                ),
            ),
        ],
        responses={200: DashboardSummarySerializer},
        examples=[
            OpenApiExample(
                "Dashboard summary",
                value={
                    "period": {
                        "type": "month",
                        "date_from": "2026-05-01",
                        "date_to": "2026-05-17",
                    },
                    "currency": "RUB",
                    "totals": {
                        "accounts_balance": "13000.00",
                        "income": "50000.00",
                        "expense": "12450.00",
                        "net": "37550.00",
                    },
                    "recent_transactions": [
                        {
                            "id": 1,
                            "account": 1,
                            "account_name": "Основная карта",
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
                            "description": "Покупка продуктов",
                            "operation_date": "2026-05-17",
                            "date": "2026-05-17",
                            "created_at": "2026-05-17T12:00:00+0300",
                            "updated_at": "2026-05-17T12:00:00+0300",
                        }
                    ],
                    "top_expense_categories": [
                        {
                            "category": 2,
                            "category_name": "Продукты",
                            "category_icon": "shopping-cart",
                            "category_color": "#10B981",
                            "total": "12450.00",
                        }
                    ],
                    "reminders": {
                        "title": "Напоминания",
                        "headerIcon": "bell",
                        "rows": [],
                        "footerLinkLabel": "Все напоминания",
                    },
                },
                response_only=True,
            )
        ],
    )
    def get(self, request):
        query_params = get_dashboard_query_params(request.query_params)
        dashboard_data = build_dashboard_summary(
            user=request.user,
            **query_params,
        )
        serializer = DashboardSummarySerializer(dashboard_data)

        return Response(serializer.data)


class TransactionExportView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["finance"],
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
        tags=["finance"],
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
        tags=["finance"],
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
        tags=["finance"],
        summary="Получить операцию",
        description="Возвращает одну финансовую операцию текущего пользователя по ID.",
        responses={200: TransactionSerializer},
    ),
    update=extend_schema(
        tags=["finance"],
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
        tags=["finance"],
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
        tags=["finance"],
        summary="Удалить операцию",
        description="Удаляет финансовую операцию текущего пользователя.",
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