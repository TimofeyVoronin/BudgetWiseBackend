from __future__ import annotations

from time import perf_counter
from typing import Any

from prometheus_client import Counter, Gauge, Histogram


HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total number of HTTP requests.",
    ["method", "path", "status_code"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ["method", "path", "status_code"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)

HTTP_REQUESTS_IN_PROGRESS = Gauge(
    "http_requests_in_progress",
    "Number of HTTP requests currently in progress.",
    ["method"],
)

API_ERRORS_TOTAL = Counter(
    "api_errors_total",
    "Total number of API errors.",
    ["status_code", "code", "method", "path"],
)

API_SERVER_ERRORS_TOTAL = Counter(
    "api_server_errors_total",
    "Total number of API server errors.",
    ["path", "code"],
)

API_VALIDATION_ERRORS_TOTAL = Counter(
    "api_validation_errors_total",
    "Total number of API validation errors.",
    ["path", "field", "code"],
)

API_AUTH_ERRORS_TOTAL = Counter(
    "api_auth_errors_total",
    "Total number of API authentication and authorization errors.",
    ["status_code", "code", "path"],
)

API_REQUEST_SIZE_BYTES = Histogram(
    "api_request_size_bytes",
    "HTTP request size in bytes.",
    ["method", "path"],
    buckets=(100, 500, 1000, 5000, 10000, 50000, 100000, 500000, 1000000),
)

API_RESPONSE_SIZE_BYTES = Histogram(
    "api_response_size_bytes",
    "HTTP response size in bytes.",
    ["method", "path", "status_code"],
    buckets=(100, 500, 1000, 5000, 10000, 50000, 100000, 500000, 1000000),
)

DATABASE_UP = Gauge(
    "database_up",
    "Database availability status. 1 means available, 0 means unavailable.",
    ["alias", "vendor"],
)

DATABASE_CHECK_DURATION_SECONDS = Histogram(
    "database_check_duration_seconds",
    "Database health-check duration in seconds.",
    ["alias", "vendor"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)

REDIS_UP = Gauge(
    "redis_up",
    "Redis availability status. 1 means available, 0 means unavailable.",
    ["url"],
)

REDIS_CHECK_DURATION_SECONDS = Histogram(
    "redis_check_duration_seconds",
    "Redis health-check duration in seconds.",
    ["url"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)

CELERY_UP = Gauge(
    "celery_up",
    "Celery availability status. 1 means at least one worker answered ping.",
)

CELERY_WORKERS_ONLINE = Gauge(
    "celery_workers_online",
    "Number of Celery workers that answered health-check ping.",
)

CELERY_CHECK_DURATION_SECONDS = Histogram(
    "celery_check_duration_seconds",
    "Celery health-check duration in seconds.",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)

HEALTH_STATUS = Gauge(
    "health_status",
    "Overall backend health status. 1 means ok, 0 means degraded.",
)


class PrometheusMetricsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if should_skip_metrics_collection(request.path):
            return self.get_response(request)

        method = request.method
        started_at = perf_counter()
        status_code = "500"
        response = None

        HTTP_REQUESTS_IN_PROGRESS.labels(method=method).inc()
        observe_request_size(request)

        try:
            response = self.get_response(request)
            status_code = str(response.status_code)
            return response
        finally:
            duration_seconds = perf_counter() - started_at
            path = get_request_metric_path(request)

            HTTP_REQUESTS_IN_PROGRESS.labels(method=method).dec()

            HTTP_REQUESTS_TOTAL.labels(
                method=method,
                path=path,
                status_code=status_code,
            ).inc()

            HTTP_REQUEST_DURATION_SECONDS.labels(
                method=method,
                path=path,
                status_code=status_code,
            ).observe(duration_seconds)

            if response is not None:
                observe_response_size(
                    response=response,
                    method=method,
                    path=path,
                    status_code=status_code,
                )
                record_error_response(
                    response=response,
                    method=method,
                    path=path,
                    status_code=status_code,
                )


def should_skip_metrics_collection(path: str) -> bool:
    return path == "/metrics/"


def get_request_metric_path(request) -> str:
    resolver_match = getattr(request, "resolver_match", None)

    if resolver_match and getattr(resolver_match, "route", None):
        route = resolver_match.route

        if not route.startswith("/"):
            route = f"/{route}"

        return route

    return request.path


def observe_request_size(request) -> None:
    path = get_request_metric_path(request)
    method = request.method
    content_length = request.META.get("CONTENT_LENGTH")

    if not content_length:
        return

    try:
        request_size = int(content_length)
    except ValueError:
        return

    API_REQUEST_SIZE_BYTES.labels(
        method=method,
        path=path,
    ).observe(request_size)


def observe_response_size(response, method: str, path: str, status_code: str) -> None:
    content_length = response.get("Content-Length")

    if content_length:
        try:
            response_size = int(content_length)
        except ValueError:
            return

        API_RESPONSE_SIZE_BYTES.labels(
            method=method,
            path=path,
            status_code=status_code,
        ).observe(response_size)
        return

    content = getattr(response, "content", None)

    if content is None:
        return

    API_RESPONSE_SIZE_BYTES.labels(
        method=method,
        path=path,
        status_code=status_code,
    ).observe(len(content))


def record_error_response(
    response,
    method: str,
    path: str,
    status_code: str,
) -> None:
    try:
        status_code_int = int(status_code)
    except ValueError:
        return

    if status_code_int < 400:
        return

    error_data = extract_error_data(response)
    error_code = error_data.get("code") or default_error_code(status_code_int)

    API_ERRORS_TOTAL.labels(
        status_code=status_code,
        code=error_code,
        method=method,
        path=path,
    ).inc()

    if status_code_int >= 500:
        API_SERVER_ERRORS_TOTAL.labels(
            path=path,
            code=error_code,
        ).inc()

    if status_code_int == 400:
        field_errors = error_data.get("field_errors")

        if isinstance(field_errors, dict):
            for field_name in field_errors:
                API_VALIDATION_ERRORS_TOTAL.labels(
                    path=path,
                    field=field_name,
                    code=error_code,
                ).inc()

    if status_code_int in (401, 403):
        API_AUTH_ERRORS_TOTAL.labels(
            status_code=status_code,
            code=error_code,
            path=path,
        ).inc()


def extract_error_data(response) -> dict[str, Any]:
    response_data = getattr(response, "data", None)

    if not isinstance(response_data, dict):
        return {}

    error_data = response_data.get("error")

    if not isinstance(error_data, dict):
        return {}

    return error_data


def default_error_code(status_code: int) -> str:
    mapping = {
        400: "validation_error",
        401: "not_authenticated",
        403: "permission_denied",
        404: "not_found",
        405: "method_not_allowed",
        409: "conflict",
        500: "server_error",
    }

    return mapping.get(status_code, "api_error")


def record_database_health_check(
    *,
    is_available: bool,
    duration_seconds: float,
    alias: str,
    vendor: str,
) -> None:
    DATABASE_UP.labels(
        alias=alias,
        vendor=vendor,
    ).set(1 if is_available else 0)

    DATABASE_CHECK_DURATION_SECONDS.labels(
        alias=alias,
        vendor=vendor,
    ).observe(duration_seconds)


def record_health_status(*, is_ok: bool) -> None:
    HEALTH_STATUS.set(1 if is_ok else 0)

def record_redis_health_check(
    *,
    is_available: bool,
    duration_seconds: float,
    url: str,
) -> None:
    REDIS_UP.labels(url=url).set(1 if is_available else 0)
    REDIS_CHECK_DURATION_SECONDS.labels(url=url).observe(duration_seconds)


def record_celery_health_check(
    *,
    is_available: bool,
    duration_seconds: float,
    worker_count: int,
) -> None:
    CELERY_UP.set(1 if is_available else 0)
    CELERY_WORKERS_ONLINE.set(worker_count)
    CELERY_CHECK_DURATION_SECONDS.observe(duration_seconds)
