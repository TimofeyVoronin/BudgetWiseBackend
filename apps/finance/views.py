from drf_spectacular.utils import (
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
from apps.finance.models import Category, Transaction, TransactionType
from apps.finance.permissions import IsObjectOwner
from apps.finance.serializers import (
    CategorySerializer,
    CategoryTreeSerializer,
    TransactionSerializer,
)


MAX_TRANSACTION_SEARCH_LENGTH = 100


@extend_schema_view(
    list=extend_schema(
        tags=["finance"],
        summary="Получить список категорий",
        parameters=[
            OpenApiParameter("type", OpenApiTypes.STR),
            OpenApiParameter("parent", OpenApiTypes.INT),
            OpenApiParameter("is_active", OpenApiTypes.BOOL),
            OpenApiParameter("ordering", OpenApiTypes.STR),
        ],
    ),
    create=extend_schema(
        tags=["finance"],
        summary="Создать категорию",
    ),
    retrieve=extend_schema(
        tags=["finance"],
        summary="Получить категорию",
    ),
    partial_update=extend_schema(
        tags=["finance"],
        summary="Частично обновить категорию",
    ),
    destroy=extend_schema(
        tags=["finance"],
        summary="Удалить категорию",
    ),
)
class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated, IsObjectOwner]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return Category.objects.none()

        queryset = (
            Category.objects
            .filter(user=self.request.user)
            .order_by("type", "name")
        )

        category_type = validate_choice_query_param(
            self.request.query_params,
            "type",
            TransactionType.values,
        )
        parent_id = get_int_query_param(self.request.query_params, "parent")
        is_active = get_bool_query_param(self.request.query_params, "is_active")
        ordering = validate_ordering(
            self.request.query_params.get("ordering"),
            {
                "name",
                "-name",
                "type",
                "-type",
                "created_at",
                "-created_at",
            },
        )

        if category_type:
            queryset = queryset.filter(type=category_type)

        if parent_id is not None:
            queryset = queryset.filter(parent_id=parent_id)

        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)

        if ordering:
            queryset = queryset.order_by(ordering)

        return queryset

    @extend_schema(
        tags=["finance"],
        summary="Получить дерево категорий",
        parameters=[
            OpenApiParameter("type", OpenApiTypes.STR),
            OpenApiParameter("is_active", OpenApiTypes.BOOL),
        ],
        responses={200: CategoryTreeSerializer(many=True)},
    )
    @action(detail=False, methods=["get"], url_path="tree")
    def tree(self, request):
        queryset = (
            self.get_queryset()
            .filter(parent__isnull=True)
            .order_by("type", "name")
        )
        serializer = CategoryTreeSerializer(
            queryset,
            many=True,
            context=self.get_serializer_context(),
        )
        return Response(serializer.data)

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


@extend_schema_view(
    list=extend_schema(
        tags=["finance"],
        summary="Получить список операций",
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
            OpenApiParameter("account", OpenApiTypes.INT),
            OpenApiParameter("category", OpenApiTypes.INT),
            OpenApiParameter("type", OpenApiTypes.STR),
            OpenApiParameter("date_from", OpenApiTypes.DATE),
            OpenApiParameter("date_to", OpenApiTypes.DATE),
            OpenApiParameter(
                "amount_min",
                OpenApiTypes.NUMBER,
                description="Минимальная сумма операции.",
            ),
            OpenApiParameter(
                "amount_max",
                OpenApiTypes.NUMBER,
                description="Максимальная сумма операции.",
            ),
            OpenApiParameter(
                "search",
                OpenApiTypes.STR,
                description=(
                    "Поиск по описанию операции. Максимальная длина 100 символов."
                ),
            ),
            OpenApiParameter(
                "ordering",
                OpenApiTypes.STR,
                description=(
                    "Сортировка. Поддерживаются поля: date, operation_date, amount, "
                    "name, description, category, created_at. "
                    "Для сортировки по убыванию используйте префикс '-'. "
                    "Можно передать несколько полей через запятую, например: "
                    "-operation_date,amount."
                ),
            ),
        ],
    ),
    create=extend_schema(
        tags=["finance"],
        summary="Создать операцию",
    ),
    retrieve=extend_schema(
        tags=["finance"],
        summary="Получить операцию",
    ),
    partial_update=extend_schema(
        tags=["finance"],
        summary="Частично обновить операцию",
    ),
    destroy=extend_schema(
        tags=["finance"],
        summary="Удалить операцию",
    ),
)
class TransactionViewSet(viewsets.ModelViewSet):
    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated, IsObjectOwner]
    pagination_class = StandardResultsSetPagination
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return Transaction.objects.none()

        queryset = (
            Transaction.objects
            .filter(user=self.request.user)
            .select_related("account", "category")
            .order_by("-operation_date", "-created_at")
        )

        account_id = get_int_query_param(self.request.query_params, "account")
        category_id = get_int_query_param(self.request.query_params, "category")
        transaction_type = validate_choice_query_param(
            self.request.query_params,
            "type",
            TransactionType.values,
        )
        date_from = get_date_query_param(self.request.query_params, "date_from")
        date_to = get_date_query_param(self.request.query_params, "date_to")
        amount_min = get_decimal_query_param(self.request.query_params, "amount_min")
        amount_max = get_decimal_query_param(self.request.query_params, "amount_max")
        search = self.request.query_params.get("search")
        ordering_fields = validate_ordering_fields(
            self.request.query_params.get("ordering"),
            {
                "date": "operation_date",
                "operation_date": "operation_date",
                "amount": "amount",
                "name": "description",
                "description": "description",
                "category": "category__name",
                "created_at": "created_at",
            },
        )

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
                queryset = queryset.filter(description__icontains=search_value)

        if ordering_fields:
            queryset = queryset.order_by(*ordering_fields)

        return queryset