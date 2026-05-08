import logging

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models.deletion import ProtectedError
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


logger = logging.getLogger("apps")


class ConflictError(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Конфликт состояния данных."
    default_code = "conflict"


class UnprocessableEntityError(APIException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "Запрос корректен синтаксически, но не может быть обработан."
    default_code = "unprocessable_entity"


def custom_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)

    if response is None:
        response = _handle_non_drf_exception(exc)

    if response is None:
        logger.exception("Unhandled API exception", exc_info=exc)
        response = Response(
            {
                "detail": "Внутренняя ошибка сервера.",
                "code": "server_error",
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if _is_already_wrapped(response.data):
        return response

    response.data = {
        "success": False,
        "error": {
            "status_code": response.status_code,
            "detail": response.data,
        },
    }

    return response


def _handle_non_drf_exception(exc):
    if isinstance(exc, ProtectedError):
        return Response(
            {
                "detail": "Объект нельзя удалить, так как с ним связаны другие данные.",
                "code": "protected_object",
            },
            status=status.HTTP_409_CONFLICT,
        )

    if isinstance(exc, IntegrityError):
        return Response(
            {
                "detail": "Нарушено ограничение целостности данных.",
                "code": "integrity_error",
            },
            status=status.HTTP_409_CONFLICT,
        )

    if isinstance(exc, DjangoValidationError):
        return Response(
            {
                "detail": _normalize_django_validation_error(exc),
                "code": "validation_error",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    return None


def _normalize_django_validation_error(exc):
    if hasattr(exc, "message_dict"):
        return exc.message_dict

    if hasattr(exc, "messages"):
        return exc.messages

    return str(exc)


def _is_already_wrapped(data):
    return (
        isinstance(data, dict)
        and data.get("success") is False
        and "error" in data
    )