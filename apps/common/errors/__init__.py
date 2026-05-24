from apps.common.errors.domain import (
    DomainAPIException,
    DomainAuthenticationError,
    DomainBusinessRuleError,
    DomainConflictError,
    DomainMethodNotAllowedError,
    DomainNotFoundError,
    DomainPermissionDeniedError,
    DomainServerError,
    DomainUnprocessableEntityError,
    DomainValidationError,
    ErrorPayload,
    extract_error_code,
    map_exception_to_domain_error,
    normalize_error_detail,
)
from apps.common.errors.handlers import (
    ConflictError,
    UnprocessableEntityError,
    custom_exception_handler,
)


__all__ = [
    "ConflictError",
    "DomainAPIException",
    "DomainAuthenticationError",
    "DomainBusinessRuleError",
    "DomainConflictError",
    "DomainMethodNotAllowedError",
    "DomainNotFoundError",
    "DomainPermissionDeniedError",
    "DomainServerError",
    "DomainUnprocessableEntityError",
    "DomainValidationError",
    "ErrorPayload",
    "UnprocessableEntityError",
    "custom_exception_handler",
    "extract_error_code",
    "map_exception_to_domain_error",
    "normalize_error_detail",
]
