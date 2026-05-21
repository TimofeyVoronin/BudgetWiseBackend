from __future__ import annotations

from django.core.paginator import EmptyPage, Paginator
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
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.finance.budgets import (
    build_budget_chart,
    build_budget_detail_stats,
    build_budget_list_summary,
    build_budget_operations,
    build_budget_warning_item,
    budget_duplicate_exists,
    get_budget_usage,
)
from apps.finance.budget_serializers import (
    BudgetDetailSerializer,
    BudgetListResponseSerializer,
    BudgetSerializer,
    BudgetWarningsResponseSerializer,
    BudgetsListMetaSerializer,
    CheckBudgetDuplicateResponseSerializer,
    CheckBudgetDuplicateSerializer,
    MAX_BUDGET_SEARCH_LENGTH,
    ValidateBudgetFormResponseSerializer,
    ValidateBudgetFormSerializer,
    get_budget_form_validation_errors,
    get_budget_meta_payload,
    serializer_errors_to_field_errors,
)
from apps.finance.models import (
    Budget,
    BudgetCategoryGroup,
    BudgetKind,
    BudgetPeriodType,
    BudgetUsageStatus,
    Category,
)
from apps.finance.permissions import IsObjectOwner


BUDGET_PERIOD_TAB_ALL = "all"
BUDGET_PERIOD_TAB_VALUES = {
    BUDGET_PERIOD_TAB_ALL,
    BudgetPeriodType.MONTH,
    BudgetPeriodType.QUARTER,
    BudgetPeriodType.YEAR,
}

MAX_BUDGET_PAGE_SIZE = 100
DEFAULT_BUDGET_PAGE_SIZE = 20


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


def get_positive_int_query_param(query_params, *names, default: int) -> int:
    raw_value = get_first_query_value(query_params, *names)

    if raw_value is None:
        return default

    try:
        parsed_value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            {
                names[0]: [
                    "Значение должно быть целым числом."
                ]
            }
        ) from exc

    if parsed_value <= 0:
        raise ValidationError(
            {
                names[0]: [
                    "Значение должно быть больше нуля."
                ]
            }
        )

    return parsed_value


def normalize_budget_group_values(values: list[str]) -> list[str]:
    label_to_value = {
        BudgetCategoryGroup.MAIN.label: BudgetCategoryGroup.MAIN,
        BudgetCategoryGroup.FAMILY.label: BudgetCategoryGroup.FAMILY,
        BudgetCategoryGroup.PERSONAL.label: BudgetCategoryGroup.PERSONAL,
    }

    normalized_values = []

    for value in values:
        normalized_value = label_to_value.get(value, value)

        if normalized_value not in BudgetCategoryGroup.values:
            raise ValidationError(
                {
                    "categoryGroups": [
                        (
                            "Недопустимая группа бюджета. "
                            "Допустимые значения: main, family, personal."
                        )
                    ]
                }
            )

        normalized_values.append(normalized_value)

    return normalized_values


@extend_schema_view(
    list=extend_schema(
        tags=["finance-budgets"],
        summary="Получить список бюджетов",
        description=(
            "Возвращает бюджеты текущего пользователя с рассчитанными "
            "показателями использования: потрачено, процент прогресса, "
            "статус использования и сводка для верхних карточек страницы."
        ),
        parameters=[
            OpenApiParameter("page", OpenApiTypes.INT, description="Номер страницы."),
            OpenApiParameter("perPage", OpenApiTypes.INT, description="Размер страницы."),
            OpenApiParameter("page_size", OpenApiTypes.INT, description="Альтернативный размер страницы."),
            OpenApiParameter("search", OpenApiTypes.STR, description="Поиск по категории или комментарию."),
            OpenApiParameter("periodTab", OpenApiTypes.STR, description="Вкладка периода: all, month, quarter или year."),
            OpenApiParameter("periodTypes", OpenApiTypes.STR, description="Типы периодов через запятую."),
            OpenApiParameter("categories", OpenApiTypes.STR, description="ID категорий через запятую."),
            OpenApiParameter("categoryGroups", OpenApiTypes.STR, description="Группы бюджетов через запятую."),
            OpenApiParameter("usageStatuses", OpenApiTypes.STR, description="Статусы использования через запятую."),
            OpenApiParameter("kinds", OpenApiTypes.STR, description="Типы бюджетов через запятую: expense, income."),
            OpenApiParameter("onlyAtRisk", OpenApiTypes.BOOL, description="Только бюджеты со статусом warning или exceeded."),
        ],
        responses={200: BudgetListResponseSerializer},
    ),
    create=extend_schema(
        tags=["finance-budgets"],
        summary="Создать бюджет",
        request=BudgetSerializer,
        responses={201: BudgetSerializer},
        examples=[
            OpenApiExample(
                "Создание бюджета",
                value={
                    "categoryId": 1,
                    "categoryGroup": "main",
                    "periodType": "month",
                    "periodStart": "2026-05-01",
                    "periodEnd": "2026-05-31",
                    "limitRub": 30000,
                    "currency": "RUB",
                    "kind": "expense",
                    "rollover": False,
                    "comment": "Лимит на продукты",
                },
                request_only=True,
            )
        ],
    ),
    retrieve=extend_schema(
        tags=["finance-budgets"],
        summary="Получить бюджет с детальной статистикой",
        responses={200: BudgetDetailSerializer},
    ),
    partial_update=extend_schema(
        tags=["finance-budgets"],
        summary="Частично обновить бюджет",
        request=BudgetSerializer,
        responses={200: BudgetSerializer},
    ),
    update=extend_schema(
        tags=["finance-budgets"],
        summary="Полностью обновить бюджет",
        request=BudgetSerializer,
        responses={200: BudgetSerializer},
    ),
    destroy=extend_schema(
        tags=["finance-budgets"],
        summary="Удалить бюджет",
        responses={200: OpenApiTypes.OBJECT},
    ),
)
class BudgetViewSet(viewsets.ModelViewSet):
    serializer_class = BudgetSerializer
    permission_classes = [IsAuthenticated, IsObjectOwner]
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
        if not self.request.user.is_authenticated:
            return Budget.objects.none()

        return (
            Budget.objects
            .filter(user=self.request.user)
            .select_related("category")
            .order_by("-period_start", "category__name", "id")
        )

    def list(self, request, *args, **kwargs):
        queryset = self.apply_db_filters(self.get_queryset())
        budgets = list(queryset)
        budgets = self.apply_usage_filters(budgets)

        summary = build_budget_list_summary(budgets)
        page_number = get_positive_int_query_param(
            request.query_params,
            "page",
            default=1,
        )
        per_page = get_positive_int_query_param(
            request.query_params,
            "perPage",
            "page_size",
            "limit",
            default=DEFAULT_BUDGET_PAGE_SIZE,
        )
        per_page = min(per_page, MAX_BUDGET_PAGE_SIZE)

        paginator = Paginator(budgets, per_page)

        try:
            page = paginator.page(page_number)
        except EmptyPage:
            page = paginator.page(paginator.num_pages or 1)

        serializer = self.get_serializer(page.object_list, many=True)
        return Response(
            {
                "items": serializer.data,
                "summary": summary,
                "pagination": {
                    "page": page.number,
                    "perPage": per_page,
                    "totalItems": paginator.count,
                    "totalPages": paginator.num_pages,
                },
            }
        )

    def retrieve(self, request, *args, **kwargs):
        budget = self.get_object()

        return Response(
            {
                "budget": BudgetSerializer(
                    budget,
                    context=self.get_serializer_context(),
                ).data,
                "stats": build_budget_detail_stats(budget),
                "chart": build_budget_chart(budget),
                "operations": build_budget_operations(budget),
            }
        )

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def destroy(self, request, *args, **kwargs):
        budget = self.get_object()
        budget_id = str(budget.pk)
        budget.delete()

        return Response(
            {
                "deleted": True,
                "id": budget_id,
            },
            status=status.HTTP_200_OK,
        )

    def apply_db_filters(self, queryset):
        query_params = self.request.query_params
        period_tab = query_params.get("periodTab") or query_params.get("period_tab")

        if period_tab:
            if period_tab not in BUDGET_PERIOD_TAB_VALUES:
                raise ValidationError(
                    {
                        "periodTab": [
                            "Вкладка периода должна быть all, month, quarter или year."
                        ]
                    }
                )

            if period_tab != BUDGET_PERIOD_TAB_ALL:
                queryset = queryset.filter(period_type=period_tab)

        period_types = parse_multi_value_query_param(
            query_params,
            "periodTypes",
            allowed_values=set(BudgetPeriodType.values),
        )
        categories = parse_multi_int_query_param(query_params, "categories")
        category_groups = normalize_budget_group_values(
            parse_multi_value_query_param(query_params, "categoryGroups")
        )
        kinds = parse_multi_value_query_param(
            query_params,
            "kinds",
            allowed_values=set(BudgetKind.values),
        )
        search = query_params.get("search")

        if period_types:
            queryset = queryset.filter(period_type__in=period_types)

        if categories:
            queryset = queryset.filter(category_id__in=categories)

        if category_groups:
            queryset = queryset.filter(category_group__in=category_groups)

        if kinds:
            queryset = queryset.filter(kind__in=kinds)

        if search:
            search_value = search.strip()

            if len(search_value) > MAX_BUDGET_SEARCH_LENGTH:
                raise ValidationError(
                    {
                        "search": [
                            (
                                "Параметр search не может быть длиннее "
                                f"{MAX_BUDGET_SEARCH_LENGTH} символов."
                            )
                        ]
                    }
                )

            if search_value:
                queryset = queryset.filter(
                    Q(category__name__icontains=search_value)
                    | Q(comment__icontains=search_value)
                )

        return queryset

    def apply_usage_filters(self, budgets: list[Budget]) -> list[Budget]:
        query_params = self.request.query_params
        usage_statuses = parse_multi_value_query_param(
            query_params,
            "usageStatuses",
            allowed_values=set(BudgetUsageStatus.values),
        )
        only_at_risk = parse_bool_query_param(
            query_params,
            "onlyAtRisk",
            "only_at_risk",
        )

        if not usage_statuses and not only_at_risk:
            return budgets

        filtered_budgets = []

        for budget in budgets:
            usage_status = get_budget_usage(budget).usage_status

            if usage_statuses and usage_status not in usage_statuses:
                continue

            if (
                only_at_risk
                and usage_status not in {
                    BudgetUsageStatus.WARNING,
                    BudgetUsageStatus.EXCEEDED,
                }
            ):
                continue

            filtered_budgets.append(budget)

        return filtered_budgets

    @extend_schema(
        tags=["finance-budgets"],
        summary="Поставить бюджет на паузу",
        responses={200: BudgetSerializer},
    )
    @action(detail=True, methods=["post"], url_path="pause")
    def pause(self, request, pk=None):
        budget = self.get_object()
        budget.paused = True
        budget.save(update_fields=["paused", "updated_at"])

        return Response(self.get_serializer(budget).data)

    @extend_schema(
        tags=["finance-budgets"],
        summary="Возобновить бюджет",
        responses={200: BudgetSerializer},
    )
    @action(detail=True, methods=["post"], url_path="resume")
    def resume(self, request, pk=None):
        budget = self.get_object()
        budget.paused = False
        budget.save(update_fields=["paused", "updated_at"])

        return Response(self.get_serializer(budget).data)

    @extend_schema(
        tags=["finance-budgets"],
        summary="Получить предупреждения по бюджетам",
        description="Возвращает бюджеты со статусом warning или exceeded.",
        responses={200: BudgetWarningsResponseSerializer},
    )
    @action(detail=False, methods=["get"], url_path="warnings")
    def warnings(self, request):
        queryset = self.apply_db_filters(self.get_queryset())
        warning_items = []

        for budget in queryset:
            usage = get_budget_usage(budget)

            if usage.usage_status in {
                BudgetUsageStatus.WARNING,
                BudgetUsageStatus.EXCEEDED,
            }:
                warning_items.append(build_budget_warning_item(budget))

        return Response(
            {
                "items": warning_items,
                "attentionCount": len(warning_items),
            }
        )

    @extend_schema(
        tags=["finance-budgets"],
        summary="Получить справочники страницы бюджетов",
        responses={200: BudgetsListMetaSerializer},
    )
    @action(detail=False, methods=["get"], url_path="meta")
    def meta(self, request):
        serializer = BudgetsListMetaSerializer(get_budget_meta_payload(request.user))
        return Response(serializer.data)

    @extend_schema(
        tags=["finance-budgets"],
        summary="Проверить дубликат бюджета",
        request=CheckBudgetDuplicateSerializer,
        responses={200: CheckBudgetDuplicateResponseSerializer},
    )
    @action(detail=False, methods=["post"], url_path="check-duplicate")
    def check_duplicate(self, request):
        serializer = CheckBudgetDuplicateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        category = self.get_duplicate_category(data)

        is_duplicate = False
        if category:
            is_duplicate = budget_duplicate_exists(
                user=request.user,
                category=category,
                kind=data["kind"],
                period_type=data["periodType"],
                period_start=data["periodStart"],
                period_end=data.get("periodEnd"),
                exclude_id=data.get("excludeId"),
            )

        response_data = {
            "isDuplicate": is_duplicate,
        }

        if is_duplicate:
            response_data["message"] = (
                "Бюджет для выбранной категории, типа и периода уже существует."
            )

        return Response(response_data)

    @extend_schema(
        tags=["finance-budgets"],
        summary="Проверить форму бюджета",
        request=ValidateBudgetFormSerializer,
        responses={200: ValidateBudgetFormResponseSerializer},
    )
    @action(detail=False, methods=["post"], url_path="validate")
    def validate_form(self, request):
        serializer = ValidateBudgetFormSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                {
                    "ok": False,
                    "fieldErrors": serializer_errors_to_field_errors(serializer.errors),
                }
            )

        field_errors = get_budget_form_validation_errors(serializer.validated_data)

        return Response(
            {
                "ok": not bool(field_errors),
                "fieldErrors": field_errors,
            }
        )

    def get_duplicate_category(self, data: dict) -> Category | None:
        category_id = data.get("categoryId")
        category_name = data.get("categoryName")

        queryset = Category.objects.filter(
            user=self.request.user,
            is_active=True,
            is_archived=False,
            type=data["kind"],
        )

        if category_id:
            return queryset.filter(pk=category_id).first()

        if category_name:
            return queryset.filter(name=category_name).first()

        return None
