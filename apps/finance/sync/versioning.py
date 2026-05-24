from __future__ import annotations

import hashlib
from datetime import date, datetime
from typing import Any

from django.utils import timezone

from apps.finance.sync.domains import get_read_only_snapshots, get_writable_resources


SYNC_VERSIONING_STRATEGY = "timestamp_based"
SYNC_SERVER_VERSION_FIELD = "updated_at"
SYNC_TOKEN_FORMAT = "iso8601_datetime"
SYNC_ENTITY_VERSION_FORMAT = "{resource}:{serverId}:{serverVersion}"
SYNC_ETAG_FORMAT = "W/\"sha256:{hash}\""


def normalize_sync_datetime(value: Any) -> str | None:
    if value in (None, ""):
        return None

    if isinstance(value, datetime):
        if timezone.is_naive(value):
            value = timezone.make_aware(value, timezone.get_current_timezone())
        return value.isoformat()

    if isinstance(value, date):
        return value.isoformat()

    return str(value)


def build_sync_version(*, resource: str, server_id: Any, server_version: Any) -> str | None:
    normalized_version = normalize_sync_datetime(server_version)
    if server_id in (None, "") or not normalized_version:
        return None
    return f"{resource}:{server_id}:{normalized_version}"


def build_sync_etag(*, resource: str, server_id: Any, server_version: Any) -> str | None:
    sync_version = build_sync_version(
        resource=resource,
        server_id=server_id,
        server_version=server_version,
    )
    if not sync_version:
        return None

    digest = hashlib.sha256(sync_version.encode("utf-8")).hexdigest()
    return f'W/"sha256:{digest}"'


def build_record_sync_metadata(*, resource: str, server_id: Any, server_version: Any, deleted: bool = False) -> dict[str, Any]:
    normalized_version = normalize_sync_datetime(server_version)
    return {
        "resource": resource,
        "serverId": str(server_id) if server_id is not None else None,
        "serverVersion": normalized_version,
        "revision": build_sync_version(
            resource=resource,
            server_id=server_id,
            server_version=server_version,
        ),
        "etag": build_sync_etag(
            resource=resource,
            server_id=server_id,
            server_version=server_version,
        ),
        "deleted": deleted,
    }


def build_versioning_payload() -> dict[str, Any]:
    return {
        "strategy": SYNC_VERSIONING_STRATEGY,
        "serverVersionField": SYNC_SERVER_VERSION_FIELD,
        "syncTokenFormat": SYNC_TOKEN_FORMAT,
        "entityVersionFormat": SYNC_ENTITY_VERSION_FORMAT,
        "etagFormat": SYNC_ETAG_FORMAT,
        "clientRecordFields": {
            "clientId": "Локальный UUID записи в IndexedDB до получения serverId.",
            "serverId": "ID записи на сервере после успешной синхронизации.",
            "syncState": "pending | synced | failed | conflict | deleted.",
            "baseVersion": "serverVersion, от которой клиент делал оффлайн-изменение.",
            "serverVersion": "Последняя известная серверная версия записи.",
            "clientUpdatedAt": "Время последнего изменения записи на клиенте.",
        },
        "operationFields": {
            "clientMutationId": "Уникальный ID попытки изменения. Используется для идемпотентности.",
            "baseSyncToken": "Последний syncToken, известный клиенту перед push.",
            "baseVersion": "Версия конкретной записи, от которой клиент сделал update/delete.",
            "clientUpdatedAt": "Время изменения на клиенте, не используется как источник истины для конфликтов.",
        },
        "conflictDetection": {
            "rule": "Если текущий serverVersion объекта больше baseVersion из операции, сервер возвращает status=conflict.",
            "requiredForActions": ["update", "delete"],
            "createConflictRule": "create проверяется через clientMutationId и локальный clientId.",
            "manualResolutionEndpoint": "/api/v1/finance/sync/conflicts/resolve/",
            "strategies": ["server_wins", "client_wins", "merge"],
        },
        "tombstones": {
            "resource": "OfflineSyncTombstone",
            "deletedVersionField": "deletedAt",
            "rule": "Удаления возвращаются в pull как changes.<resource>.deleted и хранятся отдельно от удалённой записи.",
        },
        "vectorClocks": {
            "supported": False,
            "reason": (
                "В MVP используется timestamp-based versioning. Векторные часы не применяются, "
                "так как приложение не требует многоузлового merge без серверного источника истины."
            ),
        },
        "writableResources": get_writable_resources(),
        "readOnlySnapshots": get_read_only_snapshots(),
    }
