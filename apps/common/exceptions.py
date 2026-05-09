import logging
import uuid
from typing import Any

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from apps.common.domain_errors import (
    DomainAPIException,
    DomainConflictError,
    DomainNotFoundError,
    DomainPermissionDeniedError,
    DomainServerError,
    DomainUnprocessableEntityError,
    map_exception_to_domain_error,
    normalize_error_detail,
)


logger = logging.getLogger("apps")


class ConflictError(DomainConflictError):
    """
    Backward-compatible conflict error.

    Allows old usage:
        raise ConflictError({"detail": "...", "code": "..."})

    And new usage:
        raise ConflictError(code="...", message="...")
    """

    def __init__(
        self,
        detail: Any | None = None,
        *,
        code: str | None = None,
        message: str | None = None,
        field_errors: dict[str, Any] | None = None,
        trace_id: str | None = None,
        status_code: int | None = None,
    ) -> None:
        extra_detail = None

        if isinstance(detail, dict):
            code = code or detail.get("code")
            message = message or detail.get("message") or detail.get("detail")
            extra_detail = {
                key: value
                for key, value in detail.items()
                if key not in {"code", "message", "detail"}
            } or None
        elif detail is not None:
            message = message or str(detail)

        super().__init__(
            code=code,
            message=message,
            field_errors=field_errors,
            detail=extra_detail,
            trace_id=trace_id,
            status_code=status_code,
        )


class UnprocessableEntityError(DomainUnprocessableEntityError):
    """
    Backward-compatible alias for 422 domain error.
    """


def custom_exception_handler(exc, context):
    request = context.get("request")

    domain_error = _get_domain_error(exc)

    if domain_error is not None:
        response = _build_domain_error_response(domain_error, request)
        _log_error(exc, request, response.data["error"])
        return response

    response = drf_exception_handler(exc, context)

    if response is not None:
        response.data = _build_error_body_from_drf_response(response, request)
        _log_error(exc, request, response.data["error"])
        return response

    trace_id = _generate_trace_id()

    logger.exception(
        "Unhandled API exception. trace_id=%s method=%s path=%s user_id=%s",
        trace_id,
        _get_request_method(request),
        _get_request_path(request),
        _get_user_id(request),
        exc_info=exc,
    )

    server_error = DomainServerError(trace_id=trace_id)

    return _build_domain_error_response(server_error, request)


def _get_domain_error(exc) -> DomainAPIException | None:
    domain_error = map_exception_to_domain_error(exc)

    if domain_error is not None:
        return domain_error

    if isinstance(exc, Http404):
        return DomainNotFoundError(
            detail=str(exc) or None,
        )

    if isinstance(exc, DjangoPermissionDenied):
        return DomainPermissionDeniedError(
            detail=str(exc) or None,
        )

    return None


def _build_domain_error_response(
    domain_error: DomainAPIException,
    request,
) -> Response:
    payload = domain_error.to_payload()

    trace_id = _get_trace_id_for_response(
        request=request,
        status_code=domain_error.status_code,
        current_trace_id=payload.get("trace_id"),
    )

    payload["trace_id"] = trace_id

    return Response(
        {
            "success": False,
            "error": payload,
        },
        status=domain_error.status_code,
    )


def _build_error_body_from_drf_response(response, request) -> dict[str, Any]:
    status_code = response.status_code
    response_data = normalize_error_detail(response.data)

    code = _get_default_code_by_status(status_code)
    message = _get_default_message_by_status(status_code)

    field_errors = None
    detail = response_data

    if status_code == status.HTTP_400_BAD_REQUEST and isinstance(response_data, dict):
        field_errors = response_data
        detail = None

    trace_id = _get_trace_id_for_response(
        request=request,
        status_code=status_code,
        current_trace_id=None,
    )

    return {
        "success": False,
        "error": {
            "status_code": status_code,
            "code": code,
            "message": message,
            "field_errors": field_errors,
            "detail": detail,
            "trace_id": trace_id,
        },
    }


def _get_trace_id_for_response(
    request,
    status_code: int,
    current_trace_id: str | None,
) -> str | None:
    if current_trace_id:
        return current_trace_id

    request_trace_id = _get_request_trace_id(request)

    if request_trace_id:
        return request_trace_id

    if status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
        return _generate_trace_id()

    return None


def _get_request_trace_id(request) -> str | None:
    if request is None:
        return None

    return (
        request.headers.get("X-Request-ID")
        or request.headers.get("X-Correlation-ID")
        or getattr(request, "trace_id", None)
    )


def _generate_trace_id() -> str:
    return str(uuid.uuid4())


def _log_error(exc, request, error_payload: dict[str, Any]) -> None:
    status_code = error_payload.get("status_code")
    trace_id = error_payload.get("trace_id")
    code = error_payload.get("code")

    if status_code is None:
        return

    if status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
        logger.exception(
            "API server error. status_code=%s code=%s trace_id=%s method=%s path=%s user_id=%s",
            status_code,
            code,
            trace_id,
            _get_request_method(request),
            _get_request_path(request),
            _get_user_id(request),
            exc_info=exc,
        )
        return

    if status_code >= status.HTTP_400_BAD_REQUEST:
        logger.warning(
            "API client error. status_code=%s code=%s trace_id=%s method=%s path=%s user_id=%s",
            status_code,
            code,
            trace_id,
            _get_request_method(request),
            _get_request_path(request),
            _get_user_id(request),
        )


def _get_request_method(request) -> str | None:
    if request is None:
        return None

    return request.method


def _get_request_path(request) -> str | None:
    if request is None:
        return None

    return request.path


def _get_user_id(request) -> int | None:
    if request is None:
        return None

    user = getattr(request, "user", None)

    if user is None or not user.is_authenticated:
        return None

    return user.id


def _get_default_code_by_status(status_code: int) -> str:
    mapping = {
        status.HTTP_400_BAD_REQUEST: "validation_error",
        status.HTTP_401_UNAUTHORIZED: "not_authenticated",
        status.HTTP_403_FORBIDDEN: "permission_denied",
        status.HTTP_404_NOT_FOUND: "not_found",
        status.HTTP_405_METHOD_NOT_ALLOWED: "method_not_allowed",
        status.HTTP_409_CONFLICT: "conflict",
        status.HTTP_500_INTERNAL_SERVER_ERROR: "server_error",
    }

    return mapping.get(status_code, "api_error")


def _get_default_message_by_status(status_code: int) -> str:
    mapping = {
        status.HTTP_400_BAD_REQUEST: "Некорректные данные запроса.",
        status.HTTP_401_UNAUTHORIZED: "Пользователь не авторизован.",
        status.HTTP_403_FORBIDDEN: "Недостаточно прав для выполнения действия.",
        status.HTTP_404_NOT_FOUND: "Объект не найден.",
        status.HTTP_405_METHOD_NOT_ALLOWED: "HTTP-метод не разрешён для этого endpoint.",
        status.HTTP_409_CONFLICT: "Конфликт состояния данных.",
        status.HTTP_500_INTERNAL_SERVER_ERROR: "Внутренняя ошибка сервера.",
    }

    return mapping.get(status_code, "Ошибка API.")