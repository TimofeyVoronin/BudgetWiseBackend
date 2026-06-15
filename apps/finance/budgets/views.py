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

from apps.finance.budgets.services import (
    build_budget_chart,
    build_budget_detail_stats,
    build_budget_list_summary,
    build_budget_operations,
    build_budget_warning_item,
    budget_duplicate_exists,
    get_budget_usage,
    preload_budget_category_ids,
)
from apps.finance.currencies.conversion import get_currency_conversion_service
from apps.finance.budgets.serializers import (
    BudgetDetailSerializer,
    BudgetListResponseSerializer,
    BudgetSerializer,
    BudgetWarningsResponseSerializer,
    BudgetsListMetaSerializer,
    DeleteBudgetResponseSerializer,
    CheckBudgetDuplicateResponseSerializer,
    CheckBudgetDuplicateSerializer,
    MAX_BUDGET_SEARCH_LENGTH,
    ValidateBudgetFormResponseSerializer,
    ValidateBudgetFormSerializer,
    get_budget_form_validation_errors,
    get_budget_meta_payload,
    serializer_errors_to_field_errors,
)
from apps.finance.currencies.services import validate_user_currency_available
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
            OpenApiParameter("periodTypes", OpenApiTypes.STR, description="Типы периодов через запятую: month, quarter, year."),
            OpenApiParameter("categories", OpenApiTypes.STR, description="ID категорий через запятую, например 1,2,3."),
            OpenApiParameter("categoryGroups", OpenApiTypes.STR, description="Группы бюджетов через запятую: main, family, personal."),
            OpenApiParameter("usageStatuses", OpenApiTypes.STR, description="Статусы использования через запятую: normal, warning, exceeded."),
            OpenApiParameter("kinds", OpenApiTypes.STR, description="Типы бюджетов через запятую: expense, income."),
            OpenApiParameter("onlyAtRisk", OpenApiTypes.BOOL, description="Только бюджеты со статусом warning или exceeded."),
            OpenApiParameter("currency", OpenApiTypes.STR, description="Валюта отображения сумм. Если не передана, используется валюта из настроек пользователя."),
            OpenApiParameter("budgetCurrency", OpenApiTypes.STR, description="Фильтр по исходной валюте бюджета."),
        ],
        responses={200: BudgetListResponseSerializer},
    ),
    create=extend_schema(
        tags=["finance-budgets"],
        summary="Создать бюджет",
        description=(
            "Создаёт бюджет. Валюта должна быть добавлена пользователем и быть видимой; "
            "если currency не передан, используется основная валюта пользователя."
        ),
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
        description=(
            "Возвращает данные бюджета, рассчитанную статистику использования, "
            "точки графика факта/прогноза и последние операции по категории бюджета."
        ),
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
        description=(
            "Удаляет только запись бюджета. Финансовые операции, по которым считался "
            "прогресс бюджета, не удаляются и не изменяются."
        ),
        responses={200: DeleteBudgetResponseSerializer},
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

    def get_currency_converter(self):
        if not hasattr(self, "_currency_converter"):
            self._currency_converter = get_currency_conversion_service(
                user=self.request.user,
                display_currency=self.request.query_params.get("currency"),
            )

        return self._currency_converter

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["currency_converter"] = self.get_currency_converter()
        return context

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
        converter = self.get_currency_converter()
        queryset = self.apply_db_filters(self.get_queryset())
        budgets = preload_budget_category_ids(list(queryset))
        budgets = self.apply_usage_filters(budgets, converter=converter)

        summary = build_budget_list_summary(budgets, converter=converter)
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
                "currencyContext": converter.context_payload(),
            }
        )

    def retrieve(self, request, *args, **kwargs):
        budget = self.get_object()
        preload_budget_category_ids([budget])
        converter = self.get_currency_converter()

        return Response(
            {
                "budget": BudgetSerializer(
                    budget,
                    context=self.get_serializer_context(),
                ).data,
                "stats": build_budget_detail_stats(budget, converter=converter),
                "chart": build_budget_chart(budget, converter=converter),
                "operations": build_budget_operations(budget, converter=converter),
                "currencyContext": converter.context_payload(),
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
        budget_currency = get_first_query_value(
            query_params,
            "budgetCurrency",
            "budget_currency",
            "sourceCurrency",
            "source_currency",
        )

        if budget_currency:
            budget_currency = validate_user_currency_available(
                self.request.user,
                budget_currency,
                field_name="budgetCurrency",
                require_visible=False,
            )
            queryset = queryset.filter(currency=budget_currency)

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

    def apply_usage_filters(self, budgets: list[Budget], *, converter=None) -> list[Budget]:
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
            usage_status = get_budget_usage(budget, converter=converter).usage_status

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
        description="Помечает бюджет как приостановленный. Расчёт суммы остаётся доступен, но статус риска возвращается как normal.",
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
        description="Снимает паузу с бюджета и снова включает его в расчёт предупреждений по лимиту.",
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
        converter = self.get_currency_converter()
        queryset = self.apply_db_filters(self.get_queryset())
        warning_items = []

        for budget in preload_budget_category_ids(list(queryset)):
            usage = get_budget_usage(budget, converter=converter)

            if usage.usage_status in {
                BudgetUsageStatus.WARNING,
                BudgetUsageStatus.EXCEEDED,
            }:
                warning_items.append(build_budget_warning_item(budget, converter=converter))

        return Response(
            {
                "items": warning_items,
                "attentionCount": len(warning_items),
                "currencyContext": converter.context_payload(),
            }
        )

    @extend_schema(
        tags=["finance-budgets"],
        summary="Получить справочники страницы бюджетов",
        description="Возвращает категории пользователя, группы бюджета, типы периода, видимые валюты пользователя, типы бюджета и статусы использования.",
        responses={200: BudgetsListMetaSerializer},
    )
    @action(detail=False, methods=["get"], url_path="meta")
    def meta(self, request):
        serializer = BudgetsListMetaSerializer(get_budget_meta_payload(request.user))
        return Response(serializer.data)

    @extend_schema(
        tags=["finance-budgets"],
        summary="Проверить дубликат бюджета",
        description=(
            "Проверяет, существует ли у пользователя бюджет с той же категорией, "
            "типом бюджета, типом периода и датами периода. Используется формой создания и редактирования."
        ),
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
        description="Возвращает ok=false и fieldErrors, если данные формы бюджета требуют исправления.",
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
