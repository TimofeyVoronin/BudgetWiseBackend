from __future__ import annotations

from datetime import date

from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiTypes,
    extend_schema,
)
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.finance.sync.serializers import (
    SyncBootstrapSerializer,
    SyncConflictResolveRequestSerializer,
    SyncConflictResolveResponseSerializer,
    SyncDomainsSerializer,
    SyncMetaSerializer,
    SyncPullSerializer,
    SyncPushRequestSerializer,
    SyncPushResponseSerializer,
)
from apps.finance.sync.services import (
    SYNC_MAX_BATCH_SIZE,
    apply_push_operations,
    build_bootstrap_payload,
    build_pull_payload,
    build_sync_domains_payload,
    build_sync_meta,
    parse_resources_query,
    resolve_conflict,
)


def parse_sync_datetime(value: str | None, *, field_name: str):
    if not value:
        return None

    parsed_value = parse_datetime(value)
    if parsed_value is None:
        raise ValidationError({field_name: ["Дата и время должны быть в ISO-формате."]})

    if timezone.is_naive(parsed_value):
        parsed_value = timezone.make_aware(parsed_value, timezone.get_current_timezone())

    return parsed_value


def parse_sync_date(value: str | None, *, field_name: str):
    if not value:
        return None

    parsed_value = parse_date(value)
    if parsed_value is None:
        raise ValidationError({field_name: ["Дата должна быть в ISO-формате YYYY-MM-DD."]})

    return parsed_value


def parse_int_query_param(query_params, name: str, default: int | None = None):
    raw_value = query_params.get(name)
    if raw_value in (None, ""):
        return default

    try:
        return int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValidationError({name: ["Значение должно быть целым числом."]}) from exc


def parse_list_query_param(query_params, *names: str) -> list[str]:
    values: list[str] = []
    for name in names:
        raw_value = query_params.get(name)
        if not raw_value:
            continue
        values.extend(item.strip() for item in raw_value.split(",") if item.strip())
    return values


def build_snapshot_context(request) -> dict:
    today = timezone.localdate()
    month_raw = request.query_params.get("month")
    month_date = None

    if month_raw:
        if len(month_raw) == 7:
            month_date = parse_date(f"{month_raw}-01")
        else:
            month_date = parse_sync_date(month_raw, field_name="month")

        if month_date is None:
            raise ValidationError({"month": ["Месяц должен быть в формате YYYY-MM."]})

    return {
        "period": request.query_params.get("period") or "month",
        "currency": request.query_params.get("currency") or "RUB",
        "month": month_date or today.replace(day=1),
        "calendarYear": parse_int_query_param(request.query_params, "calendarYear", today.year),
        "calendarMonth": parse_int_query_param(request.query_params, "calendarMonth", today.month),
        "accountIds": [int(item) for item in parse_list_query_param(request.query_params, "accountIds", "accounts")],
        "eventTypes": parse_list_query_param(request.query_params, "eventTypes"),
        "dateFrom": parse_sync_date(request.query_params.get("dateFrom"), field_name="dateFrom"),
        "dateTo": parse_sync_date(request.query_params.get("dateTo"), field_name="dateTo"),
        "timezone": request.query_params.get("timezone") or None,
    }


class SyncMetaView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["finance-sync"],
        operation_id="finance_sync_meta_retrieve",
        summary="Получить параметры оффлайн-синхронизации",
        description=(
            "Возвращает версию sync-схемы, поддерживаемые ресурсы, read-only snapshots "
            "и максимально допустимый размер batch-запроса."
        ),
        responses={200: SyncMetaSerializer},
        examples=[
            OpenApiExample(
                "Meta",
                value={
                    "schemaVersion": 1,
                    "serverTime": "2026-05-24T13:30:00+0300",
                    "supportedResources": ["accounts", "categories", "transactions"],
                    "readOnlySnapshots": ["dashboard", "financialCalendar"],
                    "supportedActions": ["create", "update", "delete"],
                    "maxBatchSize": 100,
                },
            )
        ],
    )
    def get(self, request):
        return Response(build_sync_meta())



class SyncDomainsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["finance-sync"],
        operation_id="finance_sync_domains_retrieve",
        summary="Получить offline-first доменные области",
        description=(
            "Возвращает список доменных областей, которые поддерживают offline-first работу, "
            "их ресурсы, зависимости, режим синхронизации и явно исключённые области. "
            "Endpoint нужен фронту как единый контракт для IndexedDB, кэширования и UI-состояний синхронизации."
        ),
        responses={200: SyncDomainsSerializer},
        examples=[
            OpenApiExample(
                "Доменные области",
                value={
                    "schemaVersion": 1,
                    "serverTime": "2026-05-24T13:30:00+0300",
                    "supportedResources": ["accounts", "categories", "transactions"],
                    "writableResources": ["accounts", "categories", "transactions"],
                    "readOnlyResources": ["receipts", "notifications"],
                    "readOnlySnapshots": ["dashboard", "financialCalendar"],
                    "excludedResources": ["goals", "reports"],
                    "domainAreas": [
                        {
                            "key": "core-finance",
                            "title": "Базовые финансовые данные",
                            "resources": ["accounts", "categories", "transactions", "tags"],
                            "snapshots": [],
                            "actions": ["create", "update", "delete"],
                            "syncMode": "read_write",
                            "priority": 10,
                            "dependencies": [],
                            "conflictPolicy": "versioned_conflict_detection",
                            "notes": ["transaction line_items синхронизируются внутри ресурса transactions."],
                        }
                    ],
                    "outOfScope": [],
                },
            )
        ],
    )
    def get(self, request):
        return Response(build_sync_domains_payload())


class SyncBootstrapView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["finance-sync"],
        operation_id="finance_sync_bootstrap_retrieve",
        summary="Получить начальный снимок данных для оффлайн-режима",
        description=(
            "Возвращает полный набор выбранных ресурсов для первичного наполнения IndexedDB "
            "и read-only snapshots для dashboard/financialCalendar. Цели и отчёты не включаются."
        ),
        parameters=[
            OpenApiParameter("resources", OpenApiTypes.STR, description="CSV-список ресурсов, например accounts,transactions,dashboard,financialCalendar."),
            OpenApiParameter("period", OpenApiTypes.STR, description="Период dashboard: week, month, year."),
            OpenApiParameter("currency", OpenApiTypes.STR, description="Валюта dashboard."),
            OpenApiParameter("month", OpenApiTypes.STR, description="Месяц динамики dashboard в формате YYYY-MM."),
            OpenApiParameter("calendarYear", OpenApiTypes.INT, description="Год финансового календаря."),
            OpenApiParameter("calendarMonth", OpenApiTypes.INT, description="Месяц финансового календаря 1-12."),
        ],
        responses={200: SyncBootstrapSerializer},
    )
    def get(self, request):
        resources = parse_resources_query(request.query_params.get("resources"))
        payload = build_bootstrap_payload(
            user=request.user,
            request=request,
            resources=resources,
            snapshot_context=build_snapshot_context(request),
        )
        return Response(payload)


class SyncPullView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["finance-sync"],
        operation_id="finance_sync_pull_retrieve",
        summary="Получить изменения после последней синхронизации",
        description=(
            "Возвращает upserted/deleted по выбранным ресурсам после параметра since. "
            "Dashboard и финансовый календарь возвращаются как свежие snapshots."
        ),
        parameters=[
            OpenApiParameter("since", OpenApiTypes.DATETIME, required=True, description="syncToken или ISO datetime последней синхронизации."),
            OpenApiParameter("resources", OpenApiTypes.STR, description="CSV-список ресурсов."),
        ],
        responses={200: SyncPullSerializer, 400: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        since = parse_sync_datetime(request.query_params.get("since"), field_name="since")
        if since is None:
            raise ValidationError({"since": ["Параметр since обязателен."]})

        resources = parse_resources_query(request.query_params.get("resources"))
        payload = build_pull_payload(
            user=request.user,
            request=request,
            since=since,
            resources=resources,
            snapshot_context=build_snapshot_context(request),
        )
        return Response(payload)


class SyncPushView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["finance-sync"],
        operation_id="finance_sync_push_create",
        summary="Отправить batch оффлайн-изменений на сервер",
        description=(
            "Принимает пачку create/update/delete операций, проверяет корректность batch-запроса, "
            "защищает от дублей по clientMutationId и локальному clientId, отклоняет повреждённые "
            "операции без падения всего запроса и возвращает результат по каждой операции."
        ),
        request=SyncPushRequestSerializer,
        responses={200: SyncPushResponseSerializer, 400: OpenApiTypes.OBJECT},
        examples=[
            OpenApiExample(
                "Создание операции из оффлайна",
                request_only=True,
                value={
                    "clientId": "web-pwa",
                    "deviceId": "browser-device-id",
                    "baseSyncToken": "2026-05-24T12:00:00+0300",
                    "operations": [
                        {
                            "clientMutationId": "uuid-1",
                            "resource": "transactions",
                            "action": "create",
                            "clientId": "local-transaction-1",
                            "clientUpdatedAt": "2026-05-24T13:00:00+0300",
                            "payload": {
                                "account": 1,
                                "category": 1,
                                "type": "expense",
                                "amount": "110.00",
                                "operation_date": "2026-05-24",
                                "description": "Оффлайн операция",
                            },
                        }
                    ],
                },
            )
        ],
    )
    def post(self, request):
        serializer = SyncPushRequestSerializer(
            data=request.data,
            context={"max_batch_size": SYNC_MAX_BATCH_SIZE},
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        payload = apply_push_operations(
            user=request.user,
            request=request,
            client_id=data["clientId"],
            device_id=data["deviceId"],
            operations=data["operations"],
        )
        return Response(payload, status=status.HTTP_200_OK)

class SyncConflictResolveView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["finance-sync"],
        operation_id="finance_sync_conflict_resolve_create",
        summary="Разрешить конфликт оффлайн-синхронизации",
        description=(
            "Применяет выбранную стратегию разрешения конфликта для серверной записи. "
            "server_wins оставляет серверную версию без изменений, client_wins применяет "
            "клиентский payload, merge применяет вручную собранный payload после выбора полей на фронте."
        ),
        request=SyncConflictResolveRequestSerializer,
        responses={200: SyncConflictResolveResponseSerializer, 400: OpenApiTypes.OBJECT},
        examples=[
            OpenApiExample(
                "Ручной merge операции",
                request_only=True,
                value={
                    "resource": "transactions",
                    "serverId": 12,
                    "strategy": "merge",
                    "payload": {
                        "description": "Итоговое описание после ручного merge",
                        "amount": "120.00",
                    },
                },
            ),
            OpenApiExample(
                "Ответ",
                response_only=True,
                value={
                    "status": "resolved",
                    "resource": "transactions",
                    "serverId": 12,
                    "strategy": "merge",
                    "version": "2026-05-24T13:45:00+0300",
                    "data": {"id": 12, "description": "Итоговое описание после ручного merge"},
                },
            ),
        ],
    )
    def post(self, request):
        serializer = SyncConflictResolveRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        payload = resolve_conflict(
            user=request.user,
            request=request,
            resource=data["resource"],
            server_id=data["serverId"],
            strategy=data["strategy"],
            payload=data.get("payload") or {},
        )
        return Response(payload, status=status.HTTP_200_OK)

