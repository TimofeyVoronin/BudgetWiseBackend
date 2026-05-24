from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable

from django.db import IntegrityError, transaction as db_transaction
from django.db.models import QuerySet
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from apps.finance.accounts.accounting import (
    create_transaction_with_balance_update,
    delete_transaction_with_balance_update,
    update_transaction_with_balance_update,
)
from apps.finance.accounts.serializers import AccountSerializer
from apps.finance.budgets.serializers import BudgetSerializer
from apps.finance.categories.serializers import CategorySerializer
from apps.finance.currencies.serializers import CurrencyListRowSerializer
from apps.finance.currencies.services import (
    CATALOG_BY_CODE,
    get_currency_usage_count,
    normalize_currency_code,
    normalize_currency_symbol,
    normalize_currency_text,
)
from apps.finance.dashboard.services import (
    DEFAULT_DASHBOARD_CURRENCY,
    DEFAULT_DASHBOARD_PERIOD,
    build_dashboard_accounts_summary,
    build_dashboard_balance_summary,
    build_dashboard_expense_dynamics,
    build_dashboard_period_currency_bar,
)
from apps.finance.financial_calendar.services import (
    build_financial_calendar_month,
    get_financial_calendar_meta,
)
from apps.finance.models import (
    Account,
    Budget,
    Category,
    Currency,
    Notification,
    OfflineSyncOperation,
    OfflineSyncOperationStatus,
    OfflineSyncTombstone,
    PlannedTransaction,
    Receipt,
    RecurringTransaction,
    Tag,
    Transaction,
    TransactionTemplate,
    UserCurrency,
)
from apps.finance.sync.domains import (
    build_offline_domain_registry,
    get_excluded_resources,
    get_read_only_resources,
    get_read_only_snapshots,
    get_writable_resources,
)
from apps.finance.sync.versioning import (
    build_record_sync_metadata,
    build_versioning_payload,
    normalize_sync_datetime,
)
from apps.finance.notifications.serializers import NotificationSerializer
from apps.finance.planned_transactions.serializers import PlannedTransactionSerializer
from apps.finance.receipts.serializers import ReceiptBriefSerializer
from apps.finance.recurring_transactions.serializers import RecurringTransactionSerializer
from apps.finance.tags.serializers import TagSerializer
from apps.finance.tags.services import get_accessible_tags
from apps.finance.transaction_templates.serializers import TransactionTemplateSerializer
from apps.finance.transactions.serializers import TransactionSerializer


SYNC_SCHEMA_VERSION = 1
SYNC_MAX_BATCH_SIZE = 100

SYNC_ACTION_CREATE = "create"
SYNC_ACTION_UPDATE = "update"
SYNC_ACTION_DELETE = "delete"

SYNC_STATUS_APPLIED = OfflineSyncOperationStatus.APPLIED
SYNC_STATUS_DUPLICATE = OfflineSyncOperationStatus.DUPLICATE
SYNC_STATUS_FAILED = OfflineSyncOperationStatus.FAILED
SYNC_STATUS_CONFLICT = OfflineSyncOperationStatus.CONFLICT
SYNC_STATUS_SKIPPED = OfflineSyncOperationStatus.SKIPPED

SUPPORTED_ACTIONS = [SYNC_ACTION_CREATE, SYNC_ACTION_UPDATE, SYNC_ACTION_DELETE]
READ_ONLY_SNAPSHOTS = get_read_only_snapshots()

SYNC_CONFLICT_STRATEGY_SERVER_WINS = "server_wins"
SYNC_CONFLICT_STRATEGY_CLIENT_WINS = "client_wins"
SYNC_CONFLICT_STRATEGY_MERGE = "merge"
SYNC_CONFLICT_STRATEGIES = [
    SYNC_CONFLICT_STRATEGY_SERVER_WINS,
    SYNC_CONFLICT_STRATEGY_CLIENT_WINS,
    SYNC_CONFLICT_STRATEGY_MERGE,
]


@dataclass(frozen=True)
class SyncResourceConfig:
    name: str
    model: type
    serializer_class: type[serializers.Serializer]
    queryset_builder: Callable[[Any], QuerySet]
    writable: bool = True
    create_handler: Callable[[serializers.Serializer], Any] | None = None
    update_handler: Callable[[serializers.Serializer], Any] | None = None
    delete_handler: Callable[[Any], None] | None = None


def _qs_accounts(user):
    return (
        Account.objects
        .filter(user=user)
        .order_by("id")
    )


def _qs_categories(user):
    return (
        Category.objects
        .filter(user=user)
        .select_related("parent")
        .order_by("id")
    )


def _qs_transactions(user):
    return (
        Transaction.objects
        .filter(user=user)
        .select_related("account", "category", "receipt", "receipt_item")
        .prefetch_related("tags__group", "line_items")
        .order_by("id")
    )


def _qs_tags(user):
    return get_accessible_tags(user).order_by("id")


def _qs_budgets(user):
    return (
        Budget.objects
        .filter(user=user)
        .select_related("category")
        .order_by("id")
    )


def _qs_currencies(user):
    return (
        UserCurrency.objects
        .filter(user=user)
        .select_related("currency")
        .order_by("id")
    )


def _qs_transaction_templates(user):
    return (
        TransactionTemplate.objects
        .filter(user=user)
        .select_related("account", "category")
        .prefetch_related("tags__group")
        .order_by("id")
    )


def _qs_recurring_transactions(user):
    return (
        RecurringTransaction.objects
        .filter(user=user)
        .select_related("account", "category")
        .order_by("id")
    )


def _qs_planned_transactions(user):
    return (
        PlannedTransaction.objects
        .filter(user=user)
        .select_related("account", "category", "converted_transaction")
        .order_by("id")
    )


def _qs_receipts(user):
    return (
        Receipt.objects
        .filter(user=user)
        .prefetch_related("items", "transactions")
        .order_by("id")
    )


def _qs_notifications(user):
    return (
        Notification.objects
        .filter(user=user)
        .order_by("id")
    )


def _delete_transaction(instance):
    delete_transaction_with_balance_update(instance)


def _save_transaction_create(serializer):
    return create_transaction_with_balance_update(serializer)


def _save_transaction_update(serializer):
    return update_transaction_with_balance_update(serializer)


def _delete_instance(instance):
    instance.delete()


RESOURCE_CONFIGS: dict[str, SyncResourceConfig] = {
    "accounts": SyncResourceConfig(
        name="accounts",
        model=Account,
        serializer_class=AccountSerializer,
        queryset_builder=_qs_accounts,
        delete_handler=_delete_instance,
    ),
    "categories": SyncResourceConfig(
        name="categories",
        model=Category,
        serializer_class=CategorySerializer,
        queryset_builder=_qs_categories,
        delete_handler=_delete_instance,
    ),
    "transactions": SyncResourceConfig(
        name="transactions",
        model=Transaction,
        serializer_class=TransactionSerializer,
        queryset_builder=_qs_transactions,
        create_handler=_save_transaction_create,
        update_handler=_save_transaction_update,
        delete_handler=_delete_transaction,
    ),
    "tags": SyncResourceConfig(
        name="tags",
        model=Tag,
        serializer_class=TagSerializer,
        queryset_builder=_qs_tags,
        delete_handler=_delete_instance,
    ),
    "budgets": SyncResourceConfig(
        name="budgets",
        model=Budget,
        serializer_class=BudgetSerializer,
        queryset_builder=_qs_budgets,
        delete_handler=_delete_instance,
    ),
    "currencies": SyncResourceConfig(
        name="currencies",
        model=UserCurrency,
        serializer_class=CurrencyListRowSerializer,
        queryset_builder=_qs_currencies,
        writable=True,
    ),
    "transactionTemplates": SyncResourceConfig(
        name="transactionTemplates",
        model=TransactionTemplate,
        serializer_class=TransactionTemplateSerializer,
        queryset_builder=_qs_transaction_templates,
        delete_handler=_delete_instance,
    ),
    "recurringTransactions": SyncResourceConfig(
        name="recurringTransactions",
        model=RecurringTransaction,
        serializer_class=RecurringTransactionSerializer,
        queryset_builder=_qs_recurring_transactions,
        delete_handler=_delete_instance,
    ),
    "plannedTransactions": SyncResourceConfig(
        name="plannedTransactions",
        model=PlannedTransaction,
        serializer_class=PlannedTransactionSerializer,
        queryset_builder=_qs_planned_transactions,
        delete_handler=_delete_instance,
    ),
    "receipts": SyncResourceConfig(
        name="receipts",
        model=Receipt,
        serializer_class=ReceiptBriefSerializer,
        queryset_builder=_qs_receipts,
        writable=False,
    ),
    "notifications": SyncResourceConfig(
        name="notifications",
        model=Notification,
        serializer_class=NotificationSerializer,
        queryset_builder=_qs_notifications,
        writable=False,
    ),
}

SUPPORTED_RESOURCES = list(RESOURCE_CONFIGS.keys())


def get_server_time():
    return timezone.now()


def build_sync_meta() -> dict[str, Any]:
    domain_registry = build_offline_domain_registry()

    return {
        "schemaVersion": SYNC_SCHEMA_VERSION,
        "serverTime": get_server_time(),
        "supportedResources": SUPPORTED_RESOURCES,
        "writableResources": get_writable_resources(),
        "readOnlyResources": get_read_only_resources(),
        "readOnlySnapshots": READ_ONLY_SNAPSHOTS,
        "excludedResources": get_excluded_resources(),
        "domainAreas": domain_registry["domainAreas"],
        "outOfScope": domain_registry["outOfScope"],
        "supportedActions": SUPPORTED_ACTIONS,
        "conflictStrategies": SYNC_CONFLICT_STRATEGIES,
        "versioning": build_versioning_payload(),
        "maxBatchSize": SYNC_MAX_BATCH_SIZE,
    }


def build_sync_domains_payload() -> dict[str, Any]:
    server_time = get_server_time()
    domain_registry = build_offline_domain_registry()

    return {
        "schemaVersion": SYNC_SCHEMA_VERSION,
        "serverTime": server_time,
        "supportedResources": SUPPORTED_RESOURCES,
        "writableResources": get_writable_resources(),
        "readOnlyResources": get_read_only_resources(),
        "readOnlySnapshots": READ_ONLY_SNAPSHOTS,
        "excludedResources": get_excluded_resources(),
        **domain_registry,
    }


def build_sync_versioning_contract() -> dict[str, Any]:
    return {
        "schemaVersion": SYNC_SCHEMA_VERSION,
        "serverTime": get_server_time(),
        **build_versioning_payload(),
    }


def normalize_resource_names(resources: list[str] | None) -> list[str]:
    if not resources:
        return SUPPORTED_RESOURCES.copy()

    result: list[str] = []
    for resource in resources:
        if resource in READ_ONLY_SNAPSHOTS:
            continue
        if resource not in RESOURCE_CONFIGS:
            raise ValidationError({"resources": [f"Ресурс {resource} не поддерживается."]})
        if resource not in result:
            result.append(resource)
    return result


def normalize_snapshot_names(resources: list[str] | None) -> list[str]:
    if not resources:
        return []

    result: list[str] = []
    for resource in resources:
        if resource in READ_ONLY_SNAPSHOTS and resource not in result:
            result.append(resource)
    return result


def parse_resources_query(raw_value: str | None) -> list[str] | None:
    if not raw_value:
        return None
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def serialize_resource(resource: str, *, user, request, since=None) -> list[dict]:
    config = RESOURCE_CONFIGS[resource]
    queryset = config.queryset_builder(user)

    if since is not None and hasattr(config.model, "updated_at"):
        queryset = queryset.filter(updated_at__gt=since)

    instances = list(queryset)
    serializer = config.serializer_class(
        instances,
        many=True,
        context={"request": request},
    )

    records: list[dict] = []
    for instance, serialized in zip(instances, serializer.data, strict=False):
        data = dict(serialized)
        server_version = getattr(instance, "updated_at", None)
        data["_sync"] = build_record_sync_metadata(
            resource=config.name,
            server_id=getattr(instance, "pk", None),
            server_version=server_version,
        )
        records.append(data)
    return records


def serialize_single_resource(config: SyncResourceConfig, instance, *, request) -> dict:
    serializer = config.serializer_class(instance, context={"request": request})
    data = dict(serializer.data)
    server_version = getattr(instance, "updated_at", None)
    data["_sync"] = build_record_sync_metadata(
        resource=config.name,
        server_id=getattr(instance, "pk", None),
        server_version=server_version,
    )
    return data


def build_deleted_items(resource: str, *, user, since=None) -> list[dict]:
    queryset = OfflineSyncTombstone.objects.filter(user=user, resource=resource)
    if since is not None:
        queryset = queryset.filter(deleted_at__gt=since)

    return [
        {
            "id": str(item.object_id),
            "deletedAt": item.deleted_at,
            "_sync": build_record_sync_metadata(
                resource=resource,
                server_id=item.object_id,
                server_version=item.deleted_at,
                deleted=True,
            ),
        }
        for item in queryset.order_by("deleted_at", "id")
    ]


def build_bootstrap_payload(*, user, request, resources: list[str] | None, snapshot_context: dict[str, Any]) -> dict:
    server_time = get_server_time()
    resource_names = normalize_resource_names(resources)
    snapshots = build_requested_snapshots(
        user=user,
        resources=resources,
        snapshot_context=snapshot_context,
    )

    return {
        "serverTime": server_time,
        "syncToken": server_time,
        "resources": {
            resource: serialize_resource(resource, user=user, request=request)
            for resource in resource_names
        },
        "snapshots": snapshots,
    }


def build_pull_payload(*, user, request, since, resources: list[str] | None, snapshot_context: dict[str, Any]) -> dict:
    server_time = get_server_time()
    resource_names = normalize_resource_names(resources)
    changes: dict[str, dict[str, list[dict]]] = {}

    for resource in resource_names:
        changes[resource] = {
            "upserted": serialize_resource(resource, user=user, request=request, since=since),
            "deleted": build_deleted_items(resource, user=user, since=since),
        }

    return {
        "serverTime": server_time,
        "syncToken": server_time,
        "changes": changes,
        "snapshots": build_requested_snapshots(
            user=user,
            resources=resources,
            snapshot_context=snapshot_context,
        ),
    }


def build_requested_snapshots(*, user, resources: list[str] | None, snapshot_context: dict[str, Any]) -> dict[str, Any]:
    snapshots: dict[str, Any] = {}
    snapshot_names = normalize_snapshot_names(resources)

    if "dashboard" in snapshot_names:
        snapshots["dashboard"] = build_dashboard_snapshot(user=user, context=snapshot_context)

    if "financialCalendar" in snapshot_names:
        snapshots["financialCalendar"] = build_financial_calendar_snapshot(user=user, context=snapshot_context)

    return snapshots


def build_dashboard_snapshot(*, user, context: dict[str, Any]) -> dict:
    period = context.get("period") or DEFAULT_DASHBOARD_PERIOD
    currency = (context.get("currency") or DEFAULT_DASHBOARD_CURRENCY).upper()
    month = context.get("month") or date.today().replace(day=1)

    return {
        "periodCurrency": build_dashboard_period_currency_bar(user=user),
        "balanceSummary": build_dashboard_balance_summary(
            user=user,
            period_type=period,
            currency=currency,
        ),
        "accountsSummary": build_dashboard_accounts_summary(
            user=user,
            period_type=period,
            currency=currency,
        ),
        "expenseDynamics": build_dashboard_expense_dynamics(
            user=user,
            month=month,
            currency=currency,
        ),
    }


def build_financial_calendar_snapshot(*, user, context: dict[str, Any]) -> dict:
    today = date.today()
    year = int(context.get("calendarYear") or today.year)
    month = int(context.get("calendarMonth") or today.month)

    return {
        "month": build_financial_calendar_month(
            user=user,
            year=year,
            month=month,
            account_ids=context.get("accountIds") or None,
            event_types=context.get("eventTypes") or None,
            date_from=context.get("dateFrom") or None,
            date_to=context.get("dateTo") or None,
            timezone_value=context.get("timezone") or None,
        ),
        "meta": get_financial_calendar_meta(user),
    }


def apply_push_operations(*, user, request, client_id: str, device_id: str, operations: list[dict]) -> dict:
    server_time = get_server_time()
    results = []

    for operation in operations:
        results.append(
            apply_single_operation(
                user=user,
                request=request,
                client_id=client_id,
                device_id=device_id,
                operation=operation,
            )
        )

    return {
        "serverTime": server_time,
        "syncToken": server_time,
        "results": results,
    }


def apply_single_operation(*, user, request, client_id: str, device_id: str, operation: dict) -> dict:
    client_mutation_id = operation["clientMutationId"]
    resource = operation["resource"]
    action = operation["action"]
    request_hash = build_operation_hash(operation)

    existing = OfflineSyncOperation.objects.filter(
        user=user,
        client_id=client_id,
        device_id=device_id,
        client_mutation_id=client_mutation_id,
    ).first()

    if existing:
        saved_response = dict(existing.response_data or {})
        if existing.request_hash and existing.request_hash != request_hash:
            return build_result(
                operation,
                status=SYNC_STATUS_FAILED,
                error={
                    "code": "duplicate_mutation_payload_mismatch",
                    "message": "Операция с таким clientMutationId уже была обработана с другим payload.",
                    "fieldErrors": {},
                },
            )
        saved_response["status"] = SYNC_STATUS_DUPLICATE
        return saved_response

    integrity_error = validate_operation_integrity(operation)
    if integrity_error is not None:
        persist_operation_result(
            user=user,
            client_id=client_id,
            device_id=device_id,
            operation=operation,
            request_hash=request_hash,
            result=integrity_error,
        )
        return integrity_error

    duplicate_create_result = find_duplicate_create_by_client_id(
        user=user,
        client_id=client_id,
        device_id=device_id,
        operation=operation,
    )
    if duplicate_create_result is not None:
        return duplicate_create_result

    result = execute_operation(user=user, request=request, operation=operation)
    persist_operation_result(
        user=user,
        client_id=client_id,
        device_id=device_id,
        operation=operation,
        request_hash=request_hash,
        result=result,
    )
    return result



def validate_operation_integrity(operation: dict) -> dict | None:
    resource = operation["resource"]
    action = operation["action"]
    payload = operation.get("payload") or {}

    if resource in READ_ONLY_SNAPSHOTS:
        return build_result(
            operation,
            status=SYNC_STATUS_FAILED,
            error={
                "code": "read_only_snapshot_resource",
                "message": f"Snapshot {resource} доступен только через bootstrap/pull и не принимается в push.",
                "fieldErrors": {"resource": ["Read-only snapshot нельзя отправлять как изменяемый ресурс."]},
            },
        )

    if resource not in RESOURCE_CONFIGS:
        return build_result(
            operation,
            status=SYNC_STATUS_FAILED,
            error={
                "code": "unsupported_resource",
                "message": f"Ресурс {resource} не поддерживается.",
                "fieldErrors": {"resource": ["Неподдерживаемый ресурс синхронизации."]},
            },
        )

    if action == SYNC_ACTION_CREATE:
        if operation.get("serverId"):
            return build_result(
                operation,
                status=SYNC_STATUS_FAILED,
                error={
                    "code": "corrupted_operation",
                    "message": "Для create-операции нельзя передавать serverId.",
                    "fieldErrors": {"serverId": ["Для create-операции serverId должен отсутствовать."]},
                },
            )

        if not operation.get("clientId"):
            return build_result(
                operation,
                status=SYNC_STATUS_FAILED,
                error={
                    "code": "client_id_required",
                    "message": "Для create-операции нужно передать clientId локальной записи.",
                    "fieldErrors": {"clientId": ["clientId обязателен для create-операций."]},
                },
            )

        if not payload:
            return build_result(
                operation,
                status=SYNC_STATUS_FAILED,
                error={
                    "code": "empty_payload",
                    "message": "Create-операция должна содержать payload.",
                    "fieldErrors": {"payload": ["payload обязателен для create-операций."]},
                },
            )

    if action == SYNC_ACTION_UPDATE:
        if not operation.get("serverId"):
            return build_result(
                operation,
                status=SYNC_STATUS_FAILED,
                error={
                    "code": "server_id_required",
                    "message": "Для update-операции нужно передать serverId.",
                    "fieldErrors": {"serverId": ["serverId обязателен для update-операций."]},
                },
            )

        if not payload:
            return build_result(
                operation,
                status=SYNC_STATUS_FAILED,
                error={
                    "code": "empty_payload",
                    "message": "Update-операция должна содержать payload с изменениями.",
                    "fieldErrors": {"payload": ["payload обязателен для update-операций."]},
                },
            )

    if action == SYNC_ACTION_DELETE and not operation.get("serverId"):
        return build_result(
            operation,
            status=SYNC_STATUS_FAILED,
            error={
                "code": "server_id_required",
                "message": "Для delete-операции нужно передать serverId.",
                "fieldErrors": {"serverId": ["serverId обязателен для delete-операций."]},
            },
        )

    if action in {SYNC_ACTION_UPDATE, SYNC_ACTION_DELETE}:
        payload_id = payload.get("id")
        server_id = operation.get("serverId")
        if payload_id is not None and str(payload_id) != str(server_id):
            return build_result(
                operation,
                status=SYNC_STATUS_FAILED,
                error={
                    "code": "server_id_payload_mismatch",
                    "message": "serverId операции не совпадает с id внутри payload.",
                    "fieldErrors": {"payload.id": ["payload.id должен совпадать с serverId."]},
                },
            )

    return None


def find_duplicate_create_by_client_id(*, user, client_id: str, device_id: str, operation: dict) -> dict | None:
    if operation["action"] != SYNC_ACTION_CREATE:
        return None

    client_object_id = operation.get("clientId")
    if not client_object_id:
        return None

    existing = (
        OfflineSyncOperation.objects
        .filter(
            user=user,
            client_id=client_id,
            device_id=device_id,
            resource=operation["resource"],
            action=SYNC_ACTION_CREATE,
            status=SYNC_STATUS_APPLIED,
            response_data__clientId=client_object_id,
        )
        .exclude(client_mutation_id=operation["clientMutationId"])
        .order_by("created_at", "id")
        .first()
    )

    if not existing:
        return None

    saved_response = dict(existing.response_data or {})
    return build_result(
        operation,
        status=SYNC_STATUS_DUPLICATE,
        server_id=saved_response.get("serverId") or existing.object_id,
        version=saved_response.get("version"),
        data=saved_response.get("data"),
    )

def execute_operation(*, user, request, operation: dict) -> dict:
    resource = operation["resource"]
    action = operation["action"]

    if resource not in RESOURCE_CONFIGS:
        return build_result(
            operation,
            status=SYNC_STATUS_FAILED,
            error={
                "code": "unsupported_resource",
                "message": f"Ресурс {resource} не поддерживается.",
                "fieldErrors": {},
            },
        )

    config = RESOURCE_CONFIGS[resource]

    if resource == "currencies":
        return execute_currency_operation(user=user, request=request, operation=operation)

    if not config.writable:
        return build_result(
            operation,
            status=SYNC_STATUS_FAILED,
            error={
                "code": "read_only_resource",
                "message": f"Ресурс {resource} недоступен для push-синхронизации.",
                "fieldErrors": {},
            },
        )

    try:
        with db_transaction.atomic():
            if action == SYNC_ACTION_CREATE:
                return execute_create(config=config, user=user, request=request, operation=operation)
            if action == SYNC_ACTION_UPDATE:
                return execute_update(config=config, user=user, request=request, operation=operation)
            if action == SYNC_ACTION_DELETE:
                return execute_delete(config=config, user=user, request=request, operation=operation)
    except serializers.ValidationError as exc:
        return build_result(
            operation,
            status=SYNC_STATUS_FAILED,
            error={
                "code": "validation_failed",
                "message": "Некорректные данные синхронизируемой операции.",
                "fieldErrors": exc.detail,
            },
        )
    except ValidationError as exc:
        return build_result(
            operation,
            status=SYNC_STATUS_FAILED,
            error={
                "code": "validation_failed",
                "message": "Некорректные данные синхронизируемой операции.",
                "fieldErrors": exc.detail,
            },
        )
    except Exception as exc:  # pragma: no cover - safety net for batch sync
        return build_result(
            operation,
            status=SYNC_STATUS_FAILED,
            error={
                "code": "sync_operation_failed",
                "message": str(exc),
                "fieldErrors": {},
            },
        )

    return build_result(
        operation,
        status=SYNC_STATUS_FAILED,
        error={
            "code": "unsupported_action",
            "message": f"Действие {action} не поддерживается.",
            "fieldErrors": {},
        },
    )



def execute_currency_operation(*, user, request, operation: dict) -> dict:
    action = operation["action"]
    config = RESOURCE_CONFIGS["currencies"]

    try:
        with db_transaction.atomic():
            if action == SYNC_ACTION_CREATE:
                instance = create_synced_currency(user=user, payload=operation.get("payload") or {})
            elif action == SYNC_ACTION_UPDATE:
                instance = get_sync_instance(config, user=user, operation=operation)
                conflict_result = detect_conflict(config=config, instance=instance, operation=operation, request=request)
                if conflict_result is not None:
                    return conflict_result
                update_synced_currency(instance=instance, payload=operation.get("payload") or {})
                instance.refresh_from_db()
            elif action == SYNC_ACTION_DELETE:
                instance = get_sync_instance(config, user=user, operation=operation)
                conflict_result = detect_conflict(config=config, instance=instance, operation=operation, request=request)
                if conflict_result is not None:
                    return conflict_result
                delete_synced_currency(instance=instance)
                OfflineSyncTombstone.objects.update_or_create(
                    user=user,
                    resource="currencies",
                    object_id=instance.pk,
                    defaults={"deleted_at": get_server_time()},
                )
                return build_result(
                    operation,
                    status=SYNC_STATUS_APPLIED,
                    server_id=instance.pk,
                    version=get_server_time(),
                    data={"deleted": True, "id": str(instance.pk)},
                )
            else:
                return build_result(
                    operation,
                    status=SYNC_STATUS_FAILED,
                    error={
                        "code": "unsupported_action",
                        "message": f"Действие {action} не поддерживается.",
                        "fieldErrors": {},
                    },
                )
    except serializers.ValidationError as exc:
        return build_result(
            operation,
            status=SYNC_STATUS_FAILED,
            error={
                "code": "validation_failed",
                "message": "Некорректные данные валюты для синхронизации.",
                "fieldErrors": exc.detail,
            },
        )
    except Exception as exc:  # pragma: no cover - defensive sync boundary
        return build_result(
            operation,
            status=SYNC_STATUS_FAILED,
            error={
                "code": "sync_operation_failed",
                "message": str(exc),
                "fieldErrors": {},
            },
        )

    data = serialize_single_resource(config, instance, request=request)
    return build_result(
        operation,
        status=SYNC_STATUS_APPLIED,
        server_id=instance.pk,
        version=instance.updated_at,
        data=data,
    )


def create_synced_currency(*, user, payload: dict) -> UserCurrency:
    code = normalize_currency_code(payload.get("code"))
    if not code:
        raise serializers.ValidationError({"code": ["Код валюты обязателен."]})

    catalog_item = CATALOG_BY_CODE.get(code)
    if catalog_item:
        currency, _ = Currency.objects.update_or_create(
            code=code,
            defaults={
                "name": catalog_item["name"],
                "symbol": catalog_item["symbol"],
                "flag_icon": catalog_item["flagIcon"],
                "decimal_places": catalog_item["decimalPlaces"],
                "is_system": True,
                "is_popular": bool(catalog_item.get("popular", False)),
            },
        )
        user_currency, _ = UserCurrency.objects.update_or_create(
            user=user,
            currency=currency,
            defaults={
                "is_visible": bool(payload.get("isVisible", payload.get("is_visible", True))),
                "is_custom": False,
                "rate_to_primary": Decimal(str(payload.get("rateToPrimary", payload.get("rate_to_primary", catalog_item.get("rateToPrimary", "1.00000000"))))),
            },
        )
    else:
        name = normalize_currency_text(payload.get("name"))
        symbol = normalize_currency_symbol(payload.get("symbol"))
        if not name:
            raise serializers.ValidationError({"name": ["Название валюты обязательно."]})
        if not symbol:
            raise serializers.ValidationError({"symbol": ["Символ валюты обязателен."]})
        currency, _ = Currency.objects.get_or_create(
            code=code,
            defaults={
                "name": name,
                "symbol": symbol,
                "flag_icon": code.lower(),
                "decimal_places": 2,
                "is_system": False,
                "is_popular": False,
            },
        )
        user_currency, _ = UserCurrency.objects.update_or_create(
            user=user,
            currency=currency,
            defaults={
                "custom_name": name,
                "custom_symbol": symbol,
                "is_visible": bool(payload.get("isVisible", payload.get("is_visible", True))),
                "is_custom": True,
                "rate_to_primary": Decimal(str(payload.get("rateToPrimary", payload.get("rate_to_primary", "1.00000000")))),
            },
        )

    if payload.get("isPrimary") is True or payload.get("is_primary") is True:
        set_primary_currency(user_currency)

    return user_currency


def update_synced_currency(*, instance: UserCurrency, payload: dict) -> None:
    update_fields = []

    if payload.get("isPrimary") is True or payload.get("is_primary") is True:
        set_primary_currency(instance)
        return

    visibility_sent = "isVisible" in payload or "is_visible" in payload
    if visibility_sent:
        is_visible = bool(payload.get("isVisible", payload.get("is_visible")))
        if instance.is_primary and not is_visible:
            raise serializers.ValidationError({"isVisible": ["Основную валюту нельзя скрыть."]})
        instance.is_visible = is_visible
        update_fields.append("is_visible")

    if "rateToPrimary" in payload or "rate_to_primary" in payload:
        instance.rate_to_primary = Decimal(str(payload.get("rateToPrimary", payload.get("rate_to_primary"))))
        update_fields.append("rate_to_primary")

    if "name" in payload or "symbol" in payload:
        if not instance.is_custom:
            raise serializers.ValidationError({"general": ["Системную валюту нельзя редактировать."]})
        if "name" in payload:
            instance.custom_name = normalize_currency_text(payload.get("name"))
            update_fields.append("custom_name")
        if "symbol" in payload:
            instance.custom_symbol = normalize_currency_symbol(payload.get("symbol"))
            update_fields.append("custom_symbol")

    if update_fields:
        update_fields.append("updated_at")
        instance.save(update_fields=update_fields)


def set_primary_currency(instance: UserCurrency) -> None:
    UserCurrency.objects.filter(user=instance.user, is_primary=True).exclude(pk=instance.pk).update(is_primary=False)
    instance.is_primary = True
    instance.is_visible = True
    instance.rate_to_primary = Decimal("1.00000000")
    instance.save(update_fields=["is_primary", "is_visible", "rate_to_primary", "updated_at"])


def delete_synced_currency(*, instance: UserCurrency) -> None:
    if instance.is_primary:
        raise serializers.ValidationError({"general": ["Основную валюту нельзя удалить."]})
    if get_currency_usage_count(instance.user, instance.code) > 0:
        raise serializers.ValidationError({"general": ["Валюта используется в данных пользователя. Её можно скрыть, но нельзя удалить."]})
    if not instance.is_custom:
        raise serializers.ValidationError({"general": ["Системную валюту нельзя удалить. Её можно скрыть в интерфейсе."]})
    instance.delete()


def execute_create(*, config: SyncResourceConfig, user, request, operation: dict) -> dict:
    serializer = config.serializer_class(
        data=operation.get("payload") or {},
        context={"request": request},
    )
    serializer.is_valid(raise_exception=True)

    if config.create_handler:
        instance = config.create_handler(serializer)
    else:
        instance = serializer.save(user=user)

    data = serialize_single_resource(config, instance, request=request)
    return build_result(
        operation,
        status=SYNC_STATUS_APPLIED,
        server_id=instance.pk,
        version=getattr(instance, "updated_at", get_server_time()),
        data=data,
    )


def execute_update(*, config: SyncResourceConfig, user, request, operation: dict) -> dict:
    instance = get_sync_instance(config, user=user, operation=operation)
    conflict_result = detect_conflict(config=config, instance=instance, operation=operation, request=request)
    if conflict_result is not None:
        return conflict_result

    serializer = config.serializer_class(
        instance,
        data=operation.get("payload") or {},
        partial=True,
        context={"request": request},
    )
    serializer.is_valid(raise_exception=True)

    if config.update_handler:
        updated_instance = config.update_handler(serializer)
    else:
        updated_instance = serializer.save()

    data = serialize_single_resource(config, updated_instance, request=request)
    return build_result(
        operation,
        status=SYNC_STATUS_APPLIED,
        server_id=updated_instance.pk,
        version=getattr(updated_instance, "updated_at", get_server_time()),
        data=data,
    )


def execute_delete(*, config: SyncResourceConfig, user, request, operation: dict) -> dict:
    instance = get_sync_instance(config, user=user, operation=operation)
    conflict_result = detect_conflict(config=config, instance=instance, operation=operation, request=request)
    if conflict_result is not None:
        return conflict_result

    object_id = instance.pk
    if config.delete_handler:
        config.delete_handler(instance)
    else:
        instance.delete()

    OfflineSyncTombstone.objects.update_or_create(
        user=user,
        resource=config.name,
        object_id=object_id,
        defaults={"deleted_at": get_server_time()},
    )

    return build_result(
        operation,
        status=SYNC_STATUS_APPLIED,
        server_id=object_id,
        version=get_server_time(),
        data={"deleted": True, "id": str(object_id)},
    )


def get_sync_instance(config: SyncResourceConfig, *, user, operation: dict):
    server_id = operation.get("serverId") or operation.get("payload", {}).get("id")
    if not server_id:
        raise serializers.ValidationError({"serverId": ["Для update/delete нужно передать serverId."]})

    try:
        return config.queryset_builder(user).get(pk=server_id)
    except config.model.DoesNotExist as exc:
        raise serializers.ValidationError({"serverId": ["Синхронизируемый объект не найден."]}) from exc


def detect_conflict(*, config: SyncResourceConfig, instance, operation: dict, request) -> dict | None:
    base_version = operation.get("baseVersion")
    updated_at = getattr(instance, "updated_at", None)

    if base_version and updated_at and updated_at > base_version:
        return build_result(
            operation,
            status=SYNC_STATUS_CONFLICT,
            server_id=instance.pk,
            version=updated_at,
            data=build_conflict_data(
                config=config,
                instance=instance,
                operation=operation,
                request=request,
            ),
            error={
                "code": "sync_conflict",
                "message": "Объект был изменён на сервере после последней синхронизации.",
                "fieldErrors": {},
            },
        )

    return None


def build_conflict_data(*, config: SyncResourceConfig, instance, operation: dict, request) -> dict:
    payload = operation.get("payload") or {}
    server_data = serialize_single_resource(config, instance, request=request)

    return {
        "clientData": payload,
        "serverData": server_data,
        "baseVersion": operation.get("baseVersion"),
        "serverVersion": getattr(instance, "updated_at", None),
        "conflictFields": build_conflict_fields(client_data=payload, server_data=server_data),
        "availableStrategies": SYNC_CONFLICT_STRATEGIES,
    }


def build_conflict_fields(*, client_data: dict, server_data: dict) -> list[dict]:
    conflict_fields: list[dict] = []

    for field_name, client_value in client_data.items():
        if field_name in {"id", "created_at", "updated_at"}:
            continue

        server_field_name = resolve_server_field_name(field_name, server_data)
        server_value = server_data.get(server_field_name) if server_field_name else None

        if make_json_safe(client_value) != make_json_safe(server_value):
            conflict_fields.append(
                {
                    "field": field_name,
                    "serverField": server_field_name or field_name,
                    "clientValue": make_json_safe(client_value),
                    "serverValue": make_json_safe(server_value),
                }
            )

    return conflict_fields


def resolve_server_field_name(field_name: str, server_data: dict) -> str | None:
    if field_name in server_data:
        return field_name

    aliases = {
        "operation_date": "operation_date",
        "date": "date",
        "isVisible": "isVisible",
        "is_visible": "isVisible",
        "isPrimary": "isPrimary",
        "is_primary": "isPrimary",
        "rateToPrimary": "rateToPrimary",
        "rate_to_primary": "rateToPrimary",
        "line_items": "line_items",
        "lineItems": "line_items",
    }

    alias = aliases.get(field_name)
    if alias in server_data:
        return alias

    return None


def resolve_conflict(*, user, request, resource: str, server_id: int, strategy: str, payload: dict | None = None) -> dict:
    if resource not in RESOURCE_CONFIGS:
        raise serializers.ValidationError({"resource": [f"Ресурс {resource} не поддерживается."]})

    if resource in READ_ONLY_SNAPSHOTS:
        raise serializers.ValidationError({"resource": ["Read-only snapshots нельзя разрешать как конфликты данных."]})

    if strategy not in SYNC_CONFLICT_STRATEGIES:
        raise serializers.ValidationError({"strategy": ["Неподдерживаемая стратегия разрешения конфликта."]})

    config = RESOURCE_CONFIGS[resource]
    if not config.writable:
        raise serializers.ValidationError({"resource": [f"Ресурс {resource} недоступен для изменения."]})

    try:
        instance = config.queryset_builder(user).get(pk=server_id)
    except config.model.DoesNotExist as exc:
        raise serializers.ValidationError({"serverId": ["Синхронизируемый объект не найден."]}) from exc

    payload = payload or {}

    if strategy == SYNC_CONFLICT_STRATEGY_SERVER_WINS:
        data = serialize_single_resource(config, instance, request=request)
        return build_conflict_resolve_result(
            resource=resource,
            server_id=instance.pk,
            strategy=strategy,
            version=getattr(instance, "updated_at", get_server_time()),
            data=data,
        )

    if not payload:
        raise serializers.ValidationError({"payload": ["Для client_wins и merge нужно передать payload с итоговыми значениями."]})

    with db_transaction.atomic():
        if resource == "currencies":
            update_synced_currency(instance=instance, payload=payload)
            instance.refresh_from_db()
            updated_instance = instance
        else:
            serializer = config.serializer_class(
                instance,
                data=payload,
                partial=True,
                context={"request": request},
            )
            serializer.is_valid(raise_exception=True)

            if config.update_handler:
                updated_instance = config.update_handler(serializer)
            else:
                updated_instance = serializer.save()

    data = serialize_single_resource(config, updated_instance, request=request)
    return build_conflict_resolve_result(
        resource=resource,
        server_id=updated_instance.pk,
        strategy=strategy,
        version=getattr(updated_instance, "updated_at", get_server_time()),
        data=data,
    )


def build_conflict_resolve_result(*, resource: str, server_id: int, strategy: str, version, data: dict) -> dict:
    return {
        "status": "resolved",
        "resource": resource,
        "serverId": server_id,
        "strategy": strategy,
        "version": version,
        "data": data,
    }

def persist_operation_result(*, user, client_id: str, device_id: str, operation: dict, request_hash: str, result: dict) -> None:
    safe_result = make_json_safe(result)

    try:
        OfflineSyncOperation.objects.create(
            user=user,
            client_id=client_id,
            device_id=device_id,
            client_mutation_id=operation["clientMutationId"],
            resource=operation["resource"],
            action=operation["action"],
            status=result.get("status", SYNC_STATUS_FAILED),
            object_id=result.get("serverId"),
            request_hash=request_hash,
            response_data=safe_result,
            error_data=safe_result.get("error") or {},
        )
    except IntegrityError:
        # A retry may race with another identical request. The next call will return the stored result.
        pass


def make_json_safe(value):
    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, date):
        return value.isoformat()

    if isinstance(value, Decimal):
        return str(value)

    if isinstance(value, dict):
        return {str(key): make_json_safe(item) for key, item in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [make_json_safe(item) for item in value]

    return value


def build_result(operation: dict, *, status: str, server_id=None, version=None, data=None, error=None) -> dict:
    result = {
        "clientMutationId": operation.get("clientMutationId"),
        "resource": operation.get("resource"),
        "action": operation.get("action"),
        "status": status,
        "clientId": operation.get("clientId"),
        "serverId": server_id,
        "version": version,
        "serverVersion": normalize_sync_datetime(version),
    }

    if data is not None:
        result["data"] = data

    if error is not None:
        result["error"] = error

    return result


def build_operation_hash(operation: dict) -> str:
    payload = json.dumps(operation, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
