from datetime import datetime, time

from django.db.models import Q
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
from apps.common.validation import validate_choice_query_param
from apps.finance.models import (
    Notification,
    NotificationChannel,
    NotificationDeliveryStatus,
    NotificationEntityKind,
    NotificationType,
)
from apps.finance.notification_serializers import (
    NOTIFICATION_CHANNEL_OPTIONS,
    NOTIFICATION_DELIVERY_STATUS_OPTIONS,
    NOTIFICATION_ENTITY_KIND_OPTIONS,
    NOTIFICATION_ICON_TONE_OPTIONS,
    NOTIFICATION_STATUS_OPTIONS,
    NOTIFICATION_TYPE_OPTIONS,
    NotificationBulkIdsSerializer,
    NotificationBulkResultSerializer,
    NotificationMetaSerializer,
    NotificationSerializer,
    NotificationSettingsSerializer,
    NotificationSummarySerializer,
)
from apps.finance.notifications import get_or_create_notification_settings
from apps.finance.permissions import IsObjectOwner


NOTIFICATION_STATUS_ALL = "all"
NOTIFICATION_STATUS_UNREAD = "unread"
NOTIFICATION_STATUS_READ = "read"
NOTIFICATION_STATUS_ARCHIVED = "archived"

NOTIFICATION_STATUS_VALUES = {
    NOTIFICATION_STATUS_ALL,
    NOTIFICATION_STATUS_UNREAD,
    NOTIFICATION_STATUS_READ,
    NOTIFICATION_STATUS_ARCHIVED,
}

MAX_NOTIFICATION_SEARCH_LENGTH = 100


def parse_multi_value_query_param(query_params, name: str, allowed_values: set[str]) -> list[str]:
    values = []

    for raw_value in query_params.getlist(name):
        values.extend(
            value.strip()
            for value in raw_value.split(",")
            if value.strip()
        )

    alias_name = f"{name}[]"
    for raw_value in query_params.getlist(alias_name):
        values.extend(
            value.strip()
            for value in raw_value.split(",")
            if value.strip()
        )

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


def get_date_query_param(query_params, *names):
    raw_value = None

    for name in names:
        raw_value = query_params.get(name)

        if raw_value:
            break

    if not raw_value:
        return None

    try:
        return datetime.strptime(raw_value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValidationError(
            {
                names[0]: [
                    "Дата должна быть указана в формате YYYY-MM-DD."
                ]
            }
        ) from exc


@extend_schema_view(
    list=extend_schema(
        tags=["finance-notifications"],
        summary="Получить список уведомлений",
        description=(
            "Возвращает уведомления текущего пользователя с фильтрами по статусу, "
            "типам, каналам, связанной сущности, периоду и поиску. "
            "По умолчанию возвращаются непрочитанные и прочитанные уведомления "
            "без архива."
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
                description="Статус: all, unread, read или archived.",
            ),
            OpenApiParameter(
                "search",
                OpenApiTypes.STR,
                description="Поиск по заголовку, тексту или тегу сущности.",
            ),
            OpenApiParameter(
                "types",
                OpenApiTypes.STR,
                description="Типы уведомлений через запятую: operation, goal, budget, system, security.",
            ),
            OpenApiParameter(
                "channels",
                OpenApiTypes.STR,
                description="Каналы через запятую: in_app, email, push, sms.",
            ),
            OpenApiParameter(
                "entity",
                OpenApiTypes.STR,
                description="Связанная сущность: transaction, goal или budget.",
            ),
            OpenApiParameter(
                "dateFrom",
                OpenApiTypes.DATE,
                description="Начало периода в формате YYYY-MM-DD.",
            ),
            OpenApiParameter(
                "dateTo",
                OpenApiTypes.DATE,
                description="Конец периода в формате YYYY-MM-DD.",
            ),
        ],
        responses={200: NotificationSerializer(many=True)},
    ),
    retrieve=extend_schema(
        tags=["finance-notifications"],
        summary="Получить уведомление",
        responses={200: NotificationSerializer},
    ),
)
class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated, IsObjectOwner]
    pagination_class = StandardResultsSetPagination
    lookup_value_regex = r"\d+"

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return Notification.objects.none()

        queryset = Notification.objects.filter(user=self.request.user)

        if self.action != "list":
            return queryset.order_by("-created_at", "-id")

        query_params = self.request.query_params
        status_value = query_params.get("status")

        if status_value in (None, ""):
            status_value = NOTIFICATION_STATUS_ALL
        else:
            status_value = validate_choice_query_param(
                query_params,
                "status",
                NOTIFICATION_STATUS_VALUES,
            )

        notification_types = parse_multi_value_query_param(
            query_params,
            "types",
            set(NotificationType.values),
        )
        channels = parse_multi_value_query_param(
            query_params,
            "channels",
            set(NotificationChannel.values),
        )
        entity = query_params.get("entity") or ""
        search = query_params.get("search")
        date_from = get_date_query_param(query_params, "dateFrom", "date_from")
        date_to = get_date_query_param(query_params, "dateTo", "date_to")

        if status_value == NOTIFICATION_STATUS_ALL:
            queryset = queryset.filter(is_archived=False)

        if status_value == NOTIFICATION_STATUS_UNREAD:
            queryset = queryset.filter(is_archived=False, is_read=False)

        if status_value == NOTIFICATION_STATUS_READ:
            queryset = queryset.filter(is_archived=False, is_read=True)

        if status_value == NOTIFICATION_STATUS_ARCHIVED:
            queryset = queryset.filter(is_archived=True)

        if notification_types:
            queryset = queryset.filter(type__in=notification_types)

        if channels:
            queryset = queryset.filter(channel__in=channels)

        if entity:
            if entity not in NotificationEntityKind.values:
                raise ValidationError(
                    {
                        "entity": [
                            "Связанная сущность должна быть transaction, goal или budget."
                        ]
                    }
                )

            queryset = queryset.filter(entity_kind=entity)

        if date_from and date_to and date_to < date_from:
            raise ValidationError(
                {
                    "dateTo": [
                        "Дата окончания периода не может быть раньше даты начала."
                    ]
                }
            )

        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)

        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)

        if search:
            search_value = search.strip()

            if len(search_value) > MAX_NOTIFICATION_SEARCH_LENGTH:
                raise ValidationError(
                    {
                        "search": [
                            (
                                "Параметр search не может быть длиннее "
                                f"{MAX_NOTIFICATION_SEARCH_LENGTH} символов."
                            )
                        ]
                    }
                )

            if search_value:
                queryset = queryset.filter(
                    Q(title__icontains=search_value)
                    | Q(body__icontains=search_value)
                    | Q(entity_tag__icontains=search_value)
                    | Q(entity_label__icontains=search_value)
                )

        return queryset.order_by("-created_at", "-id")

    @extend_schema(
        tags=["finance-notifications"],
        summary="Отметить уведомление как прочитанное",
        responses={200: NotificationSerializer},
    )
    @action(detail=True, methods=["patch"], url_path="read")
    def read(self, request, pk=None):
        notification = self.get_object()

        if not notification.is_read:
            notification.is_read = True
            notification.read_at = timezone.now()
            notification.save(update_fields=["is_read", "read_at", "updated_at"])

        serializer = self.get_serializer(notification)
        return Response(serializer.data)

    @extend_schema(
        tags=["finance-notifications"],
        summary="Отметить уведомление как непрочитанное",
        responses={200: NotificationSerializer},
    )
    @action(detail=True, methods=["patch"], url_path="unread")
    def unread(self, request, pk=None):
        notification = self.get_object()

        if notification.is_read:
            notification.is_read = False
            notification.read_at = None
            notification.save(update_fields=["is_read", "read_at", "updated_at"])

        serializer = self.get_serializer(notification)
        return Response(serializer.data)

    @extend_schema(
        tags=["finance-notifications"],
        summary="Архивировать уведомление",
        description="Скрывает уведомление из основного списка без удаления данных.",
        responses={200: NotificationSerializer},
    )
    @action(detail=True, methods=["patch"], url_path="archive")
    def archive(self, request, pk=None):
        notification = self.get_object()

        if not notification.is_archived:
            notification.is_archived = True
            notification.archived_at = timezone.now()
            notification.save(update_fields=["is_archived", "archived_at", "updated_at"])

        serializer = self.get_serializer(notification)
        return Response(serializer.data)

    @extend_schema(
        tags=["finance-notifications"],
        summary="Восстановить уведомление из архива",
        responses={200: NotificationSerializer},
    )
    @action(detail=True, methods=["patch"], url_path="restore")
    def restore(self, request, pk=None):
        notification = self.get_object()

        if notification.is_archived:
            notification.is_archived = False
            notification.archived_at = None
            notification.save(update_fields=["is_archived", "archived_at", "updated_at"])

        serializer = self.get_serializer(notification)
        return Response(serializer.data)

    @extend_schema(
        tags=["finance-notifications"],
        summary="Отметить все уведомления как прочитанные",
        description="Отмечает все неархивные непрочитанные уведомления пользователя как прочитанные.",
        responses={200: NotificationBulkResultSerializer},
    )
    @action(detail=False, methods=["post"], url_path="mark-all-read")
    def mark_all_read(self, request):
        now = timezone.now()
        queryset = Notification.objects.filter(
            user=request.user,
            is_archived=False,
            is_read=False,
        )
        updated_count = queryset.update(
            is_read=True,
            read_at=now,
            updated_at=now,
        )

        serializer = NotificationBulkResultSerializer(
            {
                "updated_count": updated_count,
                "updatedCount": updated_count,
            }
        )
        return Response(serializer.data)

    @extend_schema(
        tags=["finance-notifications"],
        summary="Архивировать выбранные уведомления",
        request=NotificationBulkIdsSerializer,
        responses={200: NotificationBulkResultSerializer},
        examples=[
            OpenApiExample(
                "Выбранные уведомления",
                value={
                    "ids": [1, 2, 3],
                },
                request_only=True,
            )
        ],
    )
    @action(detail=False, methods=["post"], url_path="archive-selected")
    def archive_selected(self, request):
        serializer = NotificationBulkIdsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        now = timezone.now()
        updated_count = Notification.objects.filter(
            user=request.user,
            pk__in=serializer.validated_data["ids"],
            is_archived=False,
        ).update(
            is_archived=True,
            archived_at=now,
            updated_at=now,
        )

        response_serializer = NotificationBulkResultSerializer(
            {
                "updated_count": updated_count,
                "updatedCount": updated_count,
            }
        )
        return Response(response_serializer.data)


    @extend_schema(
        methods=["GET"],
        tags=["finance-notifications"],
        summary="Получить настройки уведомлений",
        description=(
            "Возвращает настройки каналов, типов уведомлений и тихих часов "
            "текущего пользователя."
        ),
        responses={200: NotificationSettingsSerializer},
    )
    @extend_schema(
        methods=["PATCH"],
        tags=["finance-notifications"],
        summary="Обновить настройки уведомлений",
        description=(
            "Обновляет настройки каналов, типов уведомлений и тихих часов. "
            "Поддерживаются snake_case и camelCase поля."
        ),
        request=NotificationSettingsSerializer,
        responses={200: NotificationSettingsSerializer},
        examples=[
            OpenApiExample(
                "Настройки уведомлений",
                value={
                    "emailEnabled": True,
                    "pushEnabled": True,
                    "smsEnabled": False,
                    "inAppEnabled": True,
                    "operationEnabled": True,
                    "goalEnabled": True,
                    "budgetEnabled": True,
                    "systemEnabled": True,
                    "securityEnabled": True,
                    "marketingEnabled": False,
                    "quietHoursEnabled": True,
                    "quietHoursStart": "22:00",
                    "quietHoursEnd": "08:00",
                    "quietHoursDays": ["mon", "tue", "wed", "thu", "fri"],
                },
                request_only=True,
            )
        ],
    )
    @action(detail=False, methods=["get", "patch"], url_path="settings")
    def notification_settings(self, request):
        notification_settings = get_or_create_notification_settings(
            user=request.user,
        )

        if request.method.lower() == "get":
            serializer = NotificationSettingsSerializer(
                notification_settings,
                context=self.get_serializer_context(),
            )
            return Response(serializer.data)

        serializer = NotificationSettingsSerializer(
            notification_settings,
            data=request.data,
            partial=True,
            context=self.get_serializer_context(),
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data)

    @extend_schema(
        tags=["finance-notifications"],
        summary="Получить сводку уведомлений",
        responses={200: NotificationSummarySerializer},
        examples=[
            OpenApiExample(
                "Сводка уведомлений",
                value={
                    "unread_count": 3,
                    "unreadCount": 3,
                    "today_count": 8,
                    "todayCount": 8,
                    "delivery_errors_count": 1,
                    "deliveryErrorsCount": 1,
                    "archived_count": 2,
                    "archivedCount": 2,
                    "total_count": 10,
                    "totalCount": 10,
                },
                response_only=True,
            )
        ],
    )
    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        now = timezone.localtime()
        today_start = timezone.make_aware(
            datetime.combine(now.date(), time.min),
            timezone.get_current_timezone(),
        )
        today_end = timezone.make_aware(
            datetime.combine(now.date(), time.max),
            timezone.get_current_timezone(),
        )

        user_notifications = Notification.objects.filter(user=request.user)

        unread_count = user_notifications.filter(
            is_archived=False,
            is_read=False,
        ).count()
        today_count = user_notifications.filter(
            created_at__gte=today_start,
            created_at__lte=today_end,
        ).count()
        delivery_errors_count = user_notifications.filter(
            delivery_status=NotificationDeliveryStatus.FAILED,
        ).count()
        archived_count = user_notifications.filter(is_archived=True).count()
        total_count = user_notifications.count()

        serializer = NotificationSummarySerializer(
            {
                "unread_count": unread_count,
                "unreadCount": unread_count,
                "today_count": today_count,
                "todayCount": today_count,
                "delivery_errors_count": delivery_errors_count,
                "deliveryErrorsCount": delivery_errors_count,
                "archived_count": archived_count,
                "archivedCount": archived_count,
                "total_count": total_count,
                "totalCount": total_count,
            }
        )
        return Response(serializer.data)

    @extend_schema(
        tags=["finance-notifications"],
        summary="Получить справочники уведомлений",
        description="Возвращает типы, каналы, статусы, статусы доставки, связанные сущности и тоны иконок.",
        responses={200: NotificationMetaSerializer},
    )
    @action(detail=False, methods=["get"], url_path="meta")
    def meta(self, request):
        serializer = NotificationMetaSerializer(
            {
                "channels": NOTIFICATION_CHANNEL_OPTIONS,
                "types": NOTIFICATION_TYPE_OPTIONS,
                "statuses": NOTIFICATION_STATUS_OPTIONS,
                "deliveryStatuses": NOTIFICATION_DELIVERY_STATUS_OPTIONS,
                "entityKinds": NOTIFICATION_ENTITY_KIND_OPTIONS,
                "iconTones": NOTIFICATION_ICON_TONE_OPTIONS,
            }
        )
        return Response(serializer.data)
