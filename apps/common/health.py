from __future__ import annotations

from time import perf_counter
from typing import Any

from django.db import connection


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

        latency_ms = round((perf_counter() - started_at) * 1000, 2)

        return {
            "status": CHECK_STATUS_OK,
            "required": True,
            "latency_ms": latency_ms,
            "details": {
                "alias": connection.alias,
                "vendor": connection.vendor,
            },
        }
    except Exception as exc:
        latency_ms = round((perf_counter() - started_at) * 1000, 2)

        return {
            "status": CHECK_STATUS_ERROR,
            "required": True,
            "latency_ms": latency_ms,
            "details": {
                "alias": getattr(connection, "alias", "default"),
                "vendor": getattr(connection, "vendor", "unknown"),
                "error": exc.__class__.__name__,
                "message": str(exc),
            },
        }


def check_redis() -> dict[str, Any]:
    return {
        "status": CHECK_STATUS_SKIPPED,
        "required": False,
        "latency_ms": None,
        "details": {
            "reason": "Redis is not configured yet.",
        },
    }


def check_celery() -> dict[str, Any]:
    return {
        "status": CHECK_STATUS_SKIPPED,
        "required": False,
        "latency_ms": None,
        "details": {
            "reason": "Celery health-check is not configured yet.",
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