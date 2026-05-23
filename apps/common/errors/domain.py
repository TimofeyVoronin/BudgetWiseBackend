from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models.deletion import ProtectedError
from rest_framework import status
from rest_framework.exceptions import (
    APIException,
    AuthenticationFailed,
    ErrorDetail,
    MethodNotAllowed,
    NotAuthenticated,
    NotFound,
    PermissionDenied,
    ValidationError as DRFValidationError,
)


@dataclass(frozen=True)
class ErrorPayload:
    status_code: int
    code: str
    message: str
    field_errors: dict[str, Any] | None = None
    detail: Any | None = None
    trace_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status_code": self.status_code,
            "code": self.code,
            "message": self.message,
            "field_errors": self.field_errors,
            "detail": self.detail,
            "trace_id": self.trace_id,
        }


class DomainAPIException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "domain_error"
    default_message = "Ошибка обработки запроса."

    def __init__(
        self,
        *,
        code: str | None = None,
        message: str | None = None,
        field_errors: dict[str, Any] | None = None,
        detail: Any | None = None,
        trace_id: str | None = None,
        status_code: int | None = None,
    ) -> None:
        if status_code is not None:
            self.status_code = status_code

        self.code = code or self.default_code
        self.message = message or self.default_message
        self.field_errors = field_errors
        self.extra_detail = detail
        self.trace_id = trace_id

        super().__init__(detail=self.to_payload())

    def to_payload(self) -> dict[str, Any]:
        return ErrorPayload(
            status_code=self.status_code,
            code=self.code,
            message=self.message,
            field_errors=self.field_errors,
            detail=self.extra_detail,
            trace_id=self.trace_id,
        ).as_dict()


class DomainValidationError(DomainAPIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "validation_error"
    default_message = "Некорректные данные запроса."


class DomainAuthenticationError(DomainAPIException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_code = "not_authenticated"
    default_message = "Пользователь не авторизован."


class DomainPermissionDeniedError(DomainAPIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "permission_denied"
    default_message = "Недостаточно прав для выполнения действия."


class DomainNotFoundError(DomainAPIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_code = "not_found"
    default_message = "Объект не найден."


class DomainMethodNotAllowedError(DomainAPIException):
    status_code = status.HTTP_405_METHOD_NOT_ALLOWED
    default_code = "method_not_allowed"
    default_message = "HTTP-метод не разрешён для этого endpoint."


class DomainConflictError(DomainAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "conflict"
    default_message = "Конфликт состояния данных."


class DomainBusinessRuleError(DomainAPIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "business_rule_error"
    default_message = "Действие запрещено бизнес-правилом."


class DomainUnprocessableEntityError(DomainAPIException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_code = "unprocessable_entity"
    default_message = "Запрос корректен синтаксически, но не может быть обработан."


class DomainServerError(DomainAPIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_code = "server_error"
    default_message = "Внутренняя ошибка сервера."


def map_exception_to_domain_error(exc: Exception) -> DomainAPIException | None:
    if isinstance(exc, DomainAPIException):
        return exc

    if isinstance(exc, DRFValidationError):
        detail = normalize_error_detail(exc.detail)
        code = extract_error_code(exc.get_codes(), fallback="validation_error")

        if isinstance(detail, dict):
            return DomainValidationError(
                code=code,
                field_errors=detail,
            )

        return DomainValidationError(
            code=code,
            detail=detail,
        )

    if isinstance(exc, (NotAuthenticated, AuthenticationFailed)):
        return DomainAuthenticationError(
            code=extract_error_code(
                exc.get_codes(),
                fallback="not_authenticated",
            ),
            detail=normalize_error_detail(exc.detail),
        )

    if isinstance(exc, PermissionDenied):
        return DomainPermissionDeniedError(
            code=extract_error_code(
                exc.get_codes(),
                fallback="permission_denied",
            ),
            detail=normalize_error_detail(exc.detail),
        )

    if isinstance(exc, NotFound):
        return DomainNotFoundError(
            code=extract_error_code(
                exc.get_codes(),
                fallback="not_found",
            ),
            detail=normalize_error_detail(exc.detail),
        )

    if isinstance(exc, MethodNotAllowed):
        return DomainMethodNotAllowedError(
            code=extract_error_code(
                exc.get_codes(),
                fallback="method_not_allowed",
            ),
            detail=normalize_error_detail(exc.detail),
        )

    if isinstance(exc, ProtectedError):
        return DomainConflictError(
            code="protected_object",
            message="Объект нельзя удалить, так как с ним связаны другие данные.",
            detail={
                "protected_objects_count": len(exc.protected_objects),
            },
        )

    if isinstance(exc, IntegrityError):
        return DomainConflictError(
            code="integrity_error",
            message="Нарушено ограничение целостности данных.",
            detail=str(exc),
        )

    if isinstance(exc, DjangoValidationError):
        return DomainValidationError(
            code="validation_error",
            field_errors=normalize_django_validation_error(exc),
        )

    return None


def normalize_error_detail(detail: Any) -> Any:
    if isinstance(detail, ErrorDetail):
        return str(detail)

    if isinstance(detail, dict):
        return {
            key: normalize_error_detail(value)
            for key, value in detail.items()
        }

    if isinstance(detail, list):
        return [
            normalize_error_detail(item)
            for item in detail
        ]

    return detail


def normalize_django_validation_error(exc: DjangoValidationError) -> dict[str, Any]:
    if hasattr(exc, "message_dict"):
        return exc.message_dict

    if hasattr(exc, "messages"):
        return {
            "non_field_errors": exc.messages,
        }

    return {
        "non_field_errors": [str(exc)],
    }


def extract_error_code(codes: Any, fallback: str) -> str:
    if isinstance(codes, str):
        return codes

    if isinstance(codes, dict):
        for value in codes.values():
            code = extract_error_code(value, fallback=fallback)

            if code:
                return code

    if isinstance(codes, list):
        for value in codes:
            code = extract_error_code(value, fallback=fallback)

            if code:
                return code

    return fallback