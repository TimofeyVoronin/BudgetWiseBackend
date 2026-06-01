from decimal import Decimal

from django.db.models import Count, ExpressionWrapper, F, FloatField, Q, Sum, Value
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

from apps.common.errors import DomainConflictError
from apps.common.pagination import StandardResultsSetPagination
from apps.common.validation import validate_choice_query_param
from apps.finance.currencies.conversion import get_currency_conversion_service
from apps.finance.goals.serializers import (
    GOAL_CATEGORY_OPTIONS,
    GOAL_PRIORITY_OPTIONS,
    GOAL_STATUS_OPTIONS,
    GoalContributionSerializer,
    GoalDetailSerializer,
    GoalMetaSerializer,
    GoalSerializer,
    GoalSummarySerializer,
    GoalTopupCreateSerializer,
)
from apps.finance.goals.services import fund_goal
from apps.finance.models import (
    Goal,
    GoalCategory,
    GoalPriority,
    GoalStatus,
)
from apps.finance.permissions import IsObjectOwner


GOAL_STATUS_ALL = "all"
GOAL_STATUS_VALUES = set(GoalStatus.values) | {GOAL_STATUS_ALL}

GOAL_SORT_FIELDS = {
    "deadline": "deadline",
    "name": "name",
    "priority": "priority",
    "created_at": "created_at",
}

GOAL_SORT_DIRECTIONS = {
    "asc",
    "desc",
}

MAX_GOAL_SEARCH_LENGTH = 100


def get_goal_status_query_param(query_params):
    status_value = query_params.get("status")

    if status_value in (None, ""):
        return GoalStatus.ACTIVE

    if status_value == GOAL_STATUS_ALL:
        return GOAL_STATUS_ALL

    return validate_choice_query_param(
        query_params,
        "status",
        GoalStatus.values,
    )


def get_goal_ordering(query_params):
    sort_by = query_params.get("sortBy") or query_params.get("sort_by")

    if sort_by in (None, ""):
        return ["deadline", "name", "id"]

    sort_dir = query_params.get("sortDir") or query_params.get("sort_dir") or "asc"

    if sort_dir not in GOAL_SORT_DIRECTIONS:
        raise ValidationError(
            {
                "sortDir": [
                    "Направление сортировки должно быть asc или desc."
                ]
            }
        )

    if sort_by == "progress":
        field_name = "progress_order"
    else:
        if sort_by not in GOAL_SORT_FIELDS:
            raise ValidationError(
                {
                    "sortBy": [
                        (
                            "Недопустимое поле сортировки. "
                            "Поддерживаются: deadline, progress, name, priority."
                        )
                    ]
                }
            )

        field_name = GOAL_SORT_FIELDS[sort_by]

    if sort_dir == "desc":
        field_name = f"-{field_name}"

    return [field_name, "name", "id"]


@extend_schema_view(
    list=extend_schema(
        tags=["finance-goals"],
        summary="Получить список целей",
        description=(
            "Возвращает финансовые цели текущего пользователя с пагинацией, "
            "поиском по названию, фильтром по статусу и сортировкой. "
            "По умолчанию возвращаются активные цели."
        ),
        parameters=[
            OpenApiParameter("page", OpenApiTypes.INT, description="Номер страницы."),
            OpenApiParameter(
                "page_size",
                OpenApiTypes.INT,
                description="Размер страницы. По умолчанию 20, максимум 100.",
            ),
            OpenApiParameter(
                "status",
                OpenApiTypes.STR,
                description="Статус цели: active, completed, archived, cancelled или all.",
            ),
            OpenApiParameter(
                "search",
                OpenApiTypes.STR,
                description="Поиск по названию цели. Максимум 100 символов.",
            ),
            OpenApiParameter(
                "sortBy",
                OpenApiTypes.STR,
                description="Сортировка: deadline, progress, name или priority.",
            ),
            OpenApiParameter(
                "sortDir",
                OpenApiTypes.STR,
                description="Направление сортировки: asc или desc.",
            ),
            OpenApiParameter(
                "currency",
                OpenApiTypes.STR,
                description="Валюта отображения сумм. Если не передана, используется валюта из настроек пользователя.",
            ),
        ],
        responses={200: GoalSerializer(many=True)},
        examples=[
            OpenApiExample(
                "Список целей",
                value={
                    "count": 1,
                    "next": None,
                    "previous": None,
                    "results": [
                        {
                            "id": 1,
                            "name": "Ремонт",
                            "category": "housing",
                            "categoryKey": "housing",
                            "categoryLabel": "Жильё",
                            "priority": "medium",
                            "priorityLabel": "Средний",
                            "status": "active",
                            "statusLabel": "Активна",
                            "target_amount": "500000.00",
                            "targetRub": "500000.00",
                            "current_amount": "455000.00",
                            "currentRub": "455000.00",
                            "percent": "91.00",
                            "deadline": "2026-09-01",
                            "icon": "tools",
                            "color": "#4F46E5",
                            "topups_count": 3,
                            "topupsCount": 3,
                            "comment": "",
                        }
                    ],
                },
                response_only=True,
            )
        ],
    ),
    create=extend_schema(
        tags=["finance-goals"],
        summary="Создать цель",
        description=(
            "Создаёт финансовую цель текущего пользователя. "
            "Накопленная сумма не передаётся напрямую, она изменяется через topups."
        ),
        request=GoalSerializer,
        responses={201: GoalSerializer},
        examples=[
            OpenApiExample(
                "Создание цели",
                value={
                    "name": "Отпуск в Турции",
                    "targetRub": "250000.00",
                    "deadline": "2026-12-31",
                    "categoryKey": "travel",
                    "priority": "high",
                    "icon": "airplane",
                    "color": "#4F46E5",
                    "comment": "Семейный отпуск",
                },
                request_only=True,
            )
        ],
    ),
    retrieve=extend_schema(
        tags=["finance-goals"],
        summary="Получить цель с историей пополнений",
        description=(
            "Возвращает цель текущего пользователя и последние пополнения цели. "
            "Для отдельной пагинированной истории используйте /goals/{id}/topups/."
        ),
        responses={200: GoalDetailSerializer},
    ),
    update=extend_schema(
        tags=["finance-goals"],
        summary="Полностью обновить цель",
        request=GoalSerializer,
        responses={200: GoalSerializer},
    ),
    partial_update=extend_schema(
        tags=["finance-goals"],
        summary="Частично обновить цель",
        description=(
            "Частично обновляет цель. Поле current_amount напрямую не меняется, "
            "накопленная сумма изменяется через endpoint topups."
        ),
        request=GoalSerializer,
        responses={200: GoalSerializer},
    ),
    destroy=extend_schema(
        tags=["finance-goals"],
        summary="Удалить цель",
        description=(
            "Удаляет цель только если у неё нет пополнений. Если пополнения есть, "
            "возвращается 409 Conflict. Для скрытия используйте archive."
        ),
        responses={
            204: None,
            409: OpenApiTypes.OBJECT,
        },
    ),
)
class GoalViewSet(viewsets.ModelViewSet):
    serializer_class = GoalSerializer
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
            return Goal.objects.none()

        queryset = (
            Goal.objects
            .filter(user=self.request.user)
            .select_related("account")
            .annotate(
                topups_count=Count("contributions"),
                progress_order=ExpressionWrapper(
                    F("current_amount") * Value(100.0) / F("target_amount"),
                    output_field=FloatField(),
                ),
            )
        )

        if self.action != "list":
            return queryset.order_by("status", "deadline", "name", "id")

        query_params = self.request.query_params
        status_value = get_goal_status_query_param(query_params)
        search = query_params.get("search")
        ordering = get_goal_ordering(query_params)

        if status_value != GOAL_STATUS_ALL:
            queryset = queryset.filter(status=status_value)

        if search:
            search_value = search.strip()

            if len(search_value) > MAX_GOAL_SEARCH_LENGTH:
                raise ValidationError(
                    {
                        "search": [
                            (
                                "Параметр search не может быть длиннее "
                                f"{MAX_GOAL_SEARCH_LENGTH} символов."
                            )
                        ]
                    }
                )

            if search_value:
                queryset = queryset.filter(
                    Q(name__icontains=search_value)
                    | Q(comment__icontains=search_value)
                )

        return queryset.order_by(*ordering)

    def retrieve(self, request, *args, **kwargs):
        goal = self.get_object()
        history_queryset = self.get_goal_contributions_queryset(goal=goal)[:10]

        serializer = GoalDetailSerializer(
            {
                "goal": goal,
                "history": history_queryset,
            },
            context=self.get_serializer_context(),
        )
        return Response(serializer.data)

    def perform_create(self, serializer):
        serializer.save()

    def perform_destroy(self, instance):
        topups_count = instance.contributions.count()

        if topups_count > 0:
            raise DomainConflictError(
                code="goal_has_topups",
                message="Цель нельзя удалить, так как у неё есть пополнения.",
                detail={
                    "topups_count": topups_count,
                },
            )

        instance.delete()

    @extend_schema(
        tags=["finance-goals"],
        summary="Получить сводку по целям",
        description=(
            "Возвращает общий прогресс только по активным целям, количество "
            "активных и завершённых целей."
        ),
        responses={200: GoalSummarySerializer},
        examples=[
            OpenApiExample(
                "Сводка целей",
                value={
                    "total_current": "2084000.00",
                    "totalCurrentRub": "2084000.00",
                    "total_target": "5450000.00",
                    "totalTargetRub": "5450000.00",
                    "active_count": 4,
                    "completed_count": 1,
                },
                response_only=True,
            )
        ],
    )
    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        converter = self.get_currency_converter()
        active_goals = (
            Goal.objects
            .filter(user=request.user, status=GoalStatus.ACTIVE)
            .select_related("account")
        )

        total_current = Decimal("0.00")
        total_target = Decimal("0.00")

        for goal in active_goals:
            source_currency = (
                goal.account.currency
                if goal.account_id and goal.account
                else converter.primary_currency
            )
            total_current += converter.convert_to_display(
                goal.current_amount,
                source_currency=source_currency,
                quantize=False,
            ).amount
            total_target += converter.convert_to_display(
                goal.target_amount,
                source_currency=source_currency,
                quantize=False,
            ).amount

        total_current = total_current.quantize(Decimal("0.01"))
        total_target = total_target.quantize(Decimal("0.01"))
        active_count = active_goals.count()
        completed_count = Goal.objects.filter(
            user=request.user,
            status=GoalStatus.COMPLETED,
        ).count()

        serializer = GoalSummarySerializer(
            {
                "total_current": total_current,
                "totalCurrentRub": total_current,
                "totalCurrent": {
                    "amount": float(total_current),
                    "currency": converter.display_currency,
                },
                "total_target": total_target,
                "totalTargetRub": total_target,
                "totalTarget": {
                    "amount": float(total_target),
                    "currency": converter.display_currency,
                },
                "active_count": active_count,
                "completed_count": completed_count,
                "currency": converter.display_currency,
                "currencyContext": converter.context_payload(),
            }
        )
        return Response(serializer.data)

    @extend_schema(
        tags=["finance-goals"],
        summary="Получить справочники для формы цели",
        description="Возвращает категории, приоритеты и статусы целей.",
        responses={200: GoalMetaSerializer},
        examples=[
            OpenApiExample(
                "Справочники целей",
                value={
                    "categories": GOAL_CATEGORY_OPTIONS,
                    "priorities": GOAL_PRIORITY_OPTIONS,
                    "statuses": GOAL_STATUS_OPTIONS,
                },
                response_only=True,
            )
        ],
    )
    @action(detail=False, methods=["get"], url_path="meta")
    def meta(self, request):
        serializer = GoalMetaSerializer(
            {
                "categories": GOAL_CATEGORY_OPTIONS,
                "priorities": GOAL_PRIORITY_OPTIONS,
                "statuses": GOAL_STATUS_OPTIONS,
            }
        )
        return Response(serializer.data)

    @extend_schema(
        tags=["finance-goals"],
        summary="Архивировать цель",
        description="Переводит цель в статус archived без удаления истории.",
        responses={200: GoalSerializer},
    )
    @action(detail=True, methods=["patch"], url_path="archive")
    def archive(self, request, pk=None):
        return self.set_goal_status(GoalStatus.ARCHIVED)

    @extend_schema(
        tags=["finance-goals"],
        summary="Восстановить цель",
        description="Возвращает цель в статус active.",
        responses={200: GoalSerializer},
    )
    @action(detail=True, methods=["patch"], url_path="restore")
    def restore(self, request, pk=None):
        return self.set_goal_status(GoalStatus.ACTIVE)

    @extend_schema(
        tags=["finance-goals"],
        summary="Завершить цель",
        description="Переводит цель в статус completed.",
        responses={200: GoalSerializer},
    )
    @action(detail=True, methods=["patch"], url_path="complete")
    def complete(self, request, pk=None):
        return self.set_goal_status(GoalStatus.COMPLETED)

    @extend_schema(
        tags=["finance-goals"],
        summary="Отменить цель",
        description="Переводит цель в статус cancelled.",
        responses={200: GoalSerializer},
    )
    @action(detail=True, methods=["patch"], url_path="cancel")
    def cancel(self, request, pk=None):
        return self.set_goal_status(GoalStatus.CANCELLED)

    @extend_schema(
        methods=["GET"],
        tags=["finance-goals"],
        summary="Получить историю пополнений цели",
        description="Возвращает пагинированную историю пополнений выбранной цели.",
        responses={200: GoalContributionSerializer(many=True)},
    )
    @extend_schema(
        methods=["POST"],
        tags=["finance-goals"],
        summary="Пополнить цель",
        description=(
            "Пополняет активную цель, создаёт запись в истории пополнений, "
            "создаёт связанную расходную операцию и уменьшает баланс счёта-источника."
        ),
        request=GoalTopupCreateSerializer,
        responses={
            201: OpenApiTypes.OBJECT,
            400: OpenApiTypes.OBJECT,
            409: OpenApiTypes.OBJECT,
        },
        examples=[
            OpenApiExample(
                "Пополнение цели",
                value={
                    "amountRub": "10000.00",
                    "date": "2026-05-17",
                    "accountId": 1,
                    "comment": "Ежемесячное пополнение",
                },
                request_only=True,
            )
        ],
    )
    @action(detail=True, methods=["get", "post"], url_path="topups")
    def topups(self, request, pk=None):
        goal = self.get_object()

        if request.method.lower() == "get":
            return self.get_goal_topups_response(goal=goal)

        serializer_context = self.get_serializer_context()
        serializer_context["goal"] = goal

        serializer = GoalTopupCreateSerializer(
            data=request.data,
            context=serializer_context,
        )
        serializer.is_valid(raise_exception=True)

        result = fund_goal(
            goal=goal,
            user=request.user,
            amount=serializer.validated_data["amountRub"],
            contribution_date=serializer.validated_data["date"],
            account=serializer.validated_data["accountId"],
            comment=serializer.validated_data.get("comment", ""),
        )

        response_data = {
            "goal": GoalSerializer(
                result.goal,
                context=self.get_serializer_context(),
            ).data,
            "topup": GoalContributionSerializer(
                result.contribution,
                context=self.get_serializer_context(),
            ).data,
            "operationId": result.transaction.pk,
        }
        return Response(response_data, status=status.HTTP_201_CREATED)

    def set_goal_status(self, status_value: str):
        goal = self.get_object()

        if (
            status_value == GoalStatus.ACTIVE
            and goal.deadline is not None
            and goal.deadline < timezone.localdate()
        ):
            raise ValidationError(
                {
                    "deadline": [
                        (
                            "Нельзя восстановить активную цель с прошедшим "
                            "сроком. Сначала измените срок цели."
                        )
                    ]
                }
            )

        goal.status = status_value
        goal.save(update_fields=["status", "updated_at"])

        serializer = self.get_serializer(goal)
        return Response(serializer.data)

    def get_goal_topups_response(self, *, goal: Goal):
        queryset = self.get_goal_contributions_queryset(goal=goal)

        page = self.paginate_queryset(queryset)

        if page is not None:
            serializer = GoalContributionSerializer(
                page,
                many=True,
                context=self.get_serializer_context(),
            )
            return self.get_paginated_response(serializer.data)

        serializer = GoalContributionSerializer(
            queryset,
            many=True,
            context=self.get_serializer_context(),
        )
        return Response(serializer.data)

    def get_goal_contributions_queryset(self, *, goal: Goal):
        return (
            goal.contributions
            .filter(user=self.request.user)
            .select_related("account", "transaction", "goal__account")
            .order_by("-contribution_date", "-created_at", "-id")
        )
