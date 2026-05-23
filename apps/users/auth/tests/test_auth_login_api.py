from unittest.mock import patch
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

from django.core import mail
from django.core.signing import SignatureExpired
from django.test import override_settings
from django.conf import settings

from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.auth.email_confirmation import build_email_confirmation_token
from apps.users.models import PasswordResetToken
from apps.users.auth.serializers import PASSWORD_RESET_REQUEST_ACCEPTED_MESSAGE
from apps.users.auth.password_reset import issue_password_reset_token
from apps.users.auth.serializers import PASSWORD_RESET_SUCCESS_MESSAGE


User = get_user_model()


class LoginAPITests(APITestCase):
    def setUp(self):
        cache.clear()

        self.login_url = reverse("auth:login")
        self.refresh_url = reverse("auth:token-refresh")

        self.user_password = "user-password-123"
        self.user = User.objects.create_user(
            username="login_user",
            email="login-user@example.com",
            password=self.user_password,
            first_name="Login",
            last_name="User",
        )

        self.blocked_password = "blocked-password-123"
        self.blocked_user = User.objects.create_user(
            username="blocked_user",
            email="blocked-user@example.com",
            password=self.blocked_password,
            is_active=False,
        )

    def test_login_success_returns_tokens_and_user_data(self):
        response = self.client.post(
            self.login_url,
            {
                "email": self.user.email,
                "password": self.user_password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertIn("user", response.data)

        self.assertEqual(response.data["user"]["id"], self.user.id)
        self.assertEqual(response.data["user"]["username"], self.user.username)
        self.assertEqual(response.data["user"]["email"], self.user.email)
        self.assertEqual(response.data["user"]["first_name"], self.user.first_name)
        self.assertEqual(response.data["user"]["last_name"], self.user.last_name)
        self.assertEqual(response.data["user"]["role"], "user")
        self.assertTrue(response.data["user"]["is_active"])

        self.assertNotIn("password", response.data["user"])

        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.last_login)

    def test_login_success_is_case_insensitive_for_email(self):
        response = self.client.post(
            self.login_url,
            {
                "email": self.user.email.upper(),
                "password": self.user_password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_login_with_incorrect_password_returns_401(self):
        response = self.client.post(
            self.login_url,
            {
                "email": self.user.email,
                "password": "wrong-password",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(response.data["success"])

        error = response.data["error"]
        self.assertEqual(error["status_code"], status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(error["code"], "authentication_failed")
        self.assertEqual(error["detail"], "Неверный email или пароль.")

    def test_login_with_non_existent_user_returns_401(self):
        response = self.client.post(
            self.login_url,
            {
                "email": "not-found@example.com",
                "password": self.user_password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(response.data["success"])

        error = response.data["error"]
        self.assertEqual(error["status_code"], status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(error["code"], "authentication_failed")
        self.assertEqual(error["detail"], "Неверный email или пароль.")

    def test_login_with_inactive_user_returns_403(self):
        response = self.client.post(
            self.login_url,
            {
                "email": self.blocked_user.email,
                "password": self.blocked_password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(response.data["success"])

        error = response.data["error"]
        self.assertEqual(error["status_code"], status.HTTP_403_FORBIDDEN)
        self.assertEqual(error["code"], "permission_denied")
        self.assertEqual(error["detail"], "Учётная запись неактивна.")

    def test_login_without_required_fields_returns_400(self):
        response = self.client.post(
            self.login_url,
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])

        error = response.data["error"]
        self.assertEqual(error["status_code"], status.HTTP_400_BAD_REQUEST)
        self.assertEqual(error["code"], "required")

        field_errors = error.get("field_errors") or error.get("detail")
        self.assertIn("email", field_errors)
        self.assertIn("password", field_errors)

    def test_token_refresh_returns_new_access_token(self):
        login_response = self.client.post(
            self.login_url,
            {
                "email": self.user.email,
                "password": self.user_password,
            },
            format="json",
        )

        self.assertEqual(login_response.status_code, status.HTTP_200_OK)

        refresh_token = login_response.data["refresh"]

        response = self.client.post(
            self.refresh_url,
            {
                "refresh": refresh_token,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)

        # При ROTATE_REFRESH_TOKENS=True Simple JWT возвращает новый refresh token.
        self.assertIn("refresh", response.data)

    def test_login_rate_limit_returns_429_after_too_many_attempts(self):
        for _ in range(5):
            response = self.client.post(
                self.login_url,
                {
                    "email": self.user.email,
                    "password": "wrong-password",
                },
                format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        response = self.client.post(
            self.login_url,
            {
                "email": self.user.email,
                "password": "wrong-password",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertFalse(response.data["success"])

        error = response.data["error"]
        self.assertEqual(error["status_code"], status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(error["code"], "throttled")
