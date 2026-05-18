from django.test import TestCase
from rest_framework import status
from rest_framework.exceptions import (
    NotAuthenticated,
    NotFound,
    PermissionDenied,
    ValidationError,
)
from rest_framework.test import APIRequestFactory

from apps.common.domain_errors import DomainConflictError
from apps.common.exceptions import custom_exception_handler


class ErrorHandlingTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    def test_validation_error_has_unified_format(self):
        request = self.factory.get(
            "/api/v1/users/",
            data={
                "is_staff": "wrong",
            },
        )
        exc = ValidationError(
            {
                "is_staff": "Параметр должен быть boolean: true или false."
            }
        )

        response = custom_exception_handler(
            exc,
            {
                "request": request,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])

        error = response.data["error"]

        self.assertEqual(error["status_code"], 400)
        self.assertEqual(error["code"], "invalid")
        self.assertEqual(error["message"], "Некорректные данные запроса.")
        self.assertIn("is_staff", error["field_errors"])
        self.assertIsNone(error["detail"])
        self.assertIsNone(error["trace_id"])

    def test_not_authenticated_error_has_unified_format(self):
        request = self.factory.get("/api/v1/finance/categories/")
        exc = NotAuthenticated("Учетные данные не были предоставлены.")

        response = custom_exception_handler(
            exc,
            {
                "request": request,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(response.data["success"])

        error = response.data["error"]

        self.assertEqual(error["status_code"], 401)
        self.assertEqual(error["code"], "not_authenticated")
        self.assertEqual(error["message"], "Пользователь не авторизован.")
        self.assertIsNone(error["field_errors"])
        self.assertEqual(error["detail"], "Учетные данные не были предоставлены.")
        self.assertIsNone(error["trace_id"])

    def test_permission_denied_error_has_unified_format(self):
        request = self.factory.get("/api/v1/users/")
        exc = PermissionDenied("У вас недостаточно прав для выполнения данного действия.")

        response = custom_exception_handler(
            exc,
            {
                "request": request,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(response.data["success"])

        error = response.data["error"]

        self.assertEqual(error["status_code"], 403)
        self.assertEqual(error["code"], "permission_denied")
        self.assertEqual(error["message"], "Недостаточно прав для выполнения действия.")
        self.assertIsNone(error["field_errors"])
        self.assertEqual(
            error["detail"],
            "У вас недостаточно прав для выполнения данного действия.",
        )
        self.assertIsNone(error["trace_id"])

    def test_not_found_error_has_unified_format(self):
        request = self.factory.get("/api/v1/users/999999/")
        exc = NotFound("Страница не найдена.")

        response = custom_exception_handler(
            exc,
            {
                "request": request,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(response.data["success"])

        error = response.data["error"]

        self.assertEqual(error["status_code"], 404)
        self.assertEqual(error["code"], "not_found")
        self.assertEqual(error["message"], "Объект не найден.")
        self.assertIsNone(error["field_errors"])
        self.assertEqual(error["detail"], "Страница не найдена.")
        self.assertIsNone(error["trace_id"])

    def test_domain_conflict_error_has_unified_format(self):
        request = self.factory.delete("/api/v1/finance/categories/3/")
        exc = DomainConflictError(
            code="category_has_transactions",
            message="Категорию нельзя удалить, так как она используется в операциях.",
        )

        response = custom_exception_handler(
            exc,
            {
                "request": request,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertFalse(response.data["success"])

        error = response.data["error"]

        self.assertEqual(error["status_code"], 409)
        self.assertEqual(error["code"], "category_has_transactions")
        self.assertEqual(
            error["message"],
            "Категорию нельзя удалить, так как она используется в операциях.",
        )
        self.assertIsNone(error["field_errors"])
        self.assertIsNone(error["detail"])
        self.assertIsNone(error["trace_id"])

    def test_server_error_has_trace_id_and_unified_format(self):
        request = self.factory.get("/api/v1/test-server-error/")
        exc = RuntimeError("Unexpected test error")

        response = custom_exception_handler(
            exc,
            {
                "request": request,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertFalse(response.data["success"])

        error = response.data["error"]

        self.assertEqual(error["status_code"], 500)
        self.assertEqual(error["code"], "server_error")
        self.assertEqual(error["message"], "Внутренняя ошибка сервера.")
        self.assertIsNone(error["field_errors"])
        self.assertIsNone(error["detail"])
        self.assertIsNotNone(error["trace_id"])
        self.assertIsInstance(error["trace_id"], str)
        self.assertGreater(len(error["trace_id"]), 0)

    def test_request_trace_id_header_is_used_in_error_response(self):
        request = self.factory.get(
            "/api/v1/users/",
            data={
                "is_staff": "wrong",
            },
            HTTP_X_REQUEST_ID="test-trace-id-123",
        )
        exc = ValidationError(
            {
                "is_staff": "Параметр должен быть boolean: true или false."
            }
        )

        response = custom_exception_handler(
            exc,
            {
                "request": request,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        error = response.data["error"]

        self.assertEqual(error["trace_id"], "test-trace-id-123")

    def test_error_response_contains_required_keys(self):
        request = self.factory.get("/api/v1/finance/categories/")
        exc = NotAuthenticated("Учетные данные не были предоставлены.")

        response = custom_exception_handler(
            exc,
            {
                "request": request,
            },
        )

        self.assertIn("success", response.data)
        self.assertIn("error", response.data)

        error = response.data["error"]

        self.assertIn("status_code", error)
        self.assertIn("code", error)
        self.assertIn("message", error)
        self.assertIn("field_errors", error)
        self.assertIn("detail", error)
        self.assertIn("trace_id", error)