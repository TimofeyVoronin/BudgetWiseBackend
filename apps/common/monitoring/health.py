from __future__ import annotations

from time import perf_counter
from typing import Any
from urllib.parse import urlparse

from django.conf import settings
from django.db import connection

from apps.common.monitoring.metrics import (
    record_celery_health_check,
    record_database_health_check,
    record_health_status,
    record_redis_health_check,
)

try:  # pragma: no cover - import guard for environments before dependencies are installed.
    import redis
except ImportError:  # pragma: no cover
    redis = None

try:  # pragma: no cover - import guard for environments before dependencies are installed.
    from celery import current_app as celery_current_app
except ImportError:  # pragma: no cover
    celery_current_app = None


CHECK_STATUS_OK = "ok"
CHECK_STATUS_ERROR = "error"
CHECK_STATUS_SKIPPED = "skipped"


def build_health_status() -> tuple[dict[str, Any], int]:
    checks = {
        "database": check_database(),
        "redis": check_redis(),
        "celery": check_celery(),
        "external_services": check_external_services(),
    }

    overall_status = get_overall_status(checks)
    http_status = 200 if overall_status == CHECK_STATUS_OK else 503

    record_health_status(is_ok=overall_status == CHECK_STATUS_OK)

    return {
        "status": overall_status,
        "checks": checks,
    }, http_status


def get_overall_status(checks: dict[str, dict[str, Any]]) -> str:
    for check in checks.values():
        if check.get("required") and check.get("status") != CHECK_STATUS_OK:
            return "degraded"

    return CHECK_STATUS_OK


def check_database() -> dict[str, Any]:
    started_at = perf_counter()

    try:
        connection.ensure_connection()

        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()

        duration_seconds = perf_counter() - started_at
        latency_ms = round(duration_seconds * 1000, 2)
        alias = connection.alias
        vendor = connection.vendor

        record_database_health_check(
            is_available=True,
            duration_seconds=duration_seconds,
            alias=alias,
            vendor=vendor,
        )

        return {
            "status": CHECK_STATUS_OK,
            "required": True,
            "latency_ms": latency_ms,
            "details": {
                "alias": alias,
                "vendor": vendor,
            },
        }
    except Exception as exc:
        duration_seconds = perf_counter() - started_at
        latency_ms = round(duration_seconds * 1000, 2)
        alias = getattr(connection, "alias", "default")
        vendor = getattr(connection, "vendor", "unknown")

        record_database_health_check(
            is_available=False,
            duration_seconds=duration_seconds,
            alias=alias,
            vendor=vendor,
        )

        return {
            "status": CHECK_STATUS_ERROR,
            "required": True,
            "latency_ms": latency_ms,
            "details": {
                "alias": alias,
                "vendor": vendor,
                "error": exc.__class__.__name__,
                "message": str(exc),
            },
        }


def check_redis() -> dict[str, Any]:
    required = bool(getattr(settings, "REDIS_HEALTH_REQUIRED", False))

    if not getattr(settings, "REDIS_HEALTH_ENABLED", False):
        return {
            "status": CHECK_STATUS_SKIPPED,
            "required": required,
            "latency_ms": None,
            "details": {
                "reason": "Redis health-check is disabled.",
            },
        }

    redis_url = getattr(settings, "REDIS_HEALTH_URL", "") or getattr(
        settings,
        "REDIS_URL",
        "",
    )
    if not redis_url:
        return {
            "status": CHECK_STATUS_SKIPPED,
            "required": required,
            "latency_ms": None,
            "details": {
                "reason": "Redis URL is not configured.",
            },
        }

    if redis is None:
        return {
            "status": CHECK_STATUS_ERROR,
            "required": required,
            "latency_ms": None,
            "details": {
                "error": "ImportError",
                "message": "Python package redis is not installed.",
            },
        }

    started_at = perf_counter()
    safe_url = mask_connection_url(redis_url)

    try:
        client = redis.Redis.from_url(
            redis_url,
            socket_connect_timeout=getattr(settings, "REDIS_HEALTH_TIMEOUT_SECONDS", 1.0),
            socket_timeout=getattr(settings, "REDIS_HEALTH_TIMEOUT_SECONDS", 1.0),
        )
        client.ping()
        duration_seconds = perf_counter() - started_at
        latency_ms = round(duration_seconds * 1000, 2)

        record_redis_health_check(
            is_available=True,
            duration_seconds=duration_seconds,
            url=safe_url,
        )

        return {
            "status": CHECK_STATUS_OK,
            "required": required,
            "latency_ms": latency_ms,
            "details": {
                "url": safe_url,
            },
        }
    except Exception as exc:
        duration_seconds = perf_counter() - started_at
        latency_ms = round(duration_seconds * 1000, 2)

        record_redis_health_check(
            is_available=False,
            duration_seconds=duration_seconds,
            url=safe_url,
        )

        return {
            "status": CHECK_STATUS_ERROR,
            "required": required,
            "latency_ms": latency_ms,
            "details": {
                "url": safe_url,
                "error": exc.__class__.__name__,
                "message": str(exc),
            },
        }


def check_celery() -> dict[str, Any]:
    required = bool(getattr(settings, "CELERY_HEALTH_REQUIRED", False))

    if not getattr(settings, "CELERY_HEALTH_ENABLED", False):
        return {
            "status": CHECK_STATUS_SKIPPED,
            "required": required,
            "latency_ms": None,
            "details": {
                "reason": "Celery health-check is disabled.",
            },
        }

    started_at = perf_counter()
    broker_url = getattr(settings, "CELERY_BROKER_URL", "")
    safe_broker_url = mask_connection_url(broker_url)

    if celery_current_app is None:
        return {
            "status": CHECK_STATUS_ERROR,
            "required": required,
            "latency_ms": None,
            "details": {
                "brokerUrl": safe_broker_url,
                "error": "ImportError",
                "message": "Python package celery is not installed.",
            },
        }

    try:
        responses = celery_current_app.control.ping(
            timeout=getattr(settings, "CELERY_HEALTH_TIMEOUT_SECONDS", 1.0),
        )
        duration_seconds = perf_counter() - started_at
        latency_ms = round(duration_seconds * 1000, 2)
        worker_count = len(responses)

        record_celery_health_check(
            is_available=worker_count > 0,
            duration_seconds=duration_seconds,
            worker_count=worker_count,
        )

        if worker_count < 1:
            return {
                "status": CHECK_STATUS_ERROR,
                "required": required,
                "latency_ms": latency_ms,
                "details": {
                    "brokerUrl": safe_broker_url,
                    "workersOnline": 0,
                    "message": "Celery worker did not respond to ping.",
                },
            }

        return {
            "status": CHECK_STATUS_OK,
            "required": required,
            "latency_ms": latency_ms,
            "details": {
                "brokerUrl": safe_broker_url,
                "workersOnline": worker_count,
                "workers": [list(item.keys())[0] for item in responses if item],
            },
        }
    except Exception as exc:
        duration_seconds = perf_counter() - started_at
        latency_ms = round(duration_seconds * 1000, 2)

        record_celery_health_check(
            is_available=False,
            duration_seconds=duration_seconds,
            worker_count=0,
        )

        return {
            "status": CHECK_STATUS_ERROR,
            "required": required,
            "latency_ms": latency_ms,
            "details": {
                "brokerUrl": safe_broker_url,
                "error": exc.__class__.__name__,
                "message": str(exc),
            },
        }


def check_external_services() -> dict[str, Any]:
    return {
        "status": CHECK_STATUS_SKIPPED,
        "required": False,
        "latency_ms": None,
        "details": {
            "reason": "External services are not configured yet.",
        },
    }


def mask_connection_url(url: str) -> str:
    if not url:
        return ""

    parsed = urlparse(url)
    if not parsed.password:
        return url

    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"

    username = parsed.username or ""
    netloc = f"{username}:***@{host}" if username else host

    return parsed._replace(netloc=netloc).geturl()
