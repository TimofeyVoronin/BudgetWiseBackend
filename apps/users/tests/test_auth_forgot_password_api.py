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

from apps.users.email_confirmation import build_email_confirmation_token
from apps.users.models import PasswordResetToken
from apps.users.serializers import PASSWORD_RESET_REQUEST_ACCEPTED_MESSAGE
from apps.users.password_reset import issue_password_reset_token
from apps.users.serializers import PASSWORD_RESET_SUCCESS_MESSAGE


User = get_user_model()


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    FRONTEND_PASSWORD_RESET_URL="http://app.budgetwise.localhost:5173/auth/reset-password",
    REST_FRAMEWORK={
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": {
            **settings.REST_FRAMEWORK.get("DEFAULT_THROTTLE_RATES", {}),
            "login": settings.REST_FRAMEWORK.get("DEFAULT_THROTTLE_RATES", {}).get(
                "login",
                "5/min",
            ),
            "forgot_password_ip": "10/min",
            "forgot_password_email": "3/hour",
        },
    },
)
class ForgotPasswordAPITests(APITestCase):
    def setUp(self):
        cache.clear()

        if hasattr(mail, "outbox"):
            mail.outbox.clear()

        self.forgot_password_url = reverse("auth:forgot-password-check")
        self.password = "ForgotPassword123!"

    def test_forgot_password_existing_email_returns_generic_response_and_sends_email(self):
        user = User.objects.create_user(
            username="forgot_user",
            email="forgot-user@example.com",
            password=self.password,
            is_active=True,
        )

        response = self.client.post(
            self.forgot_password_url,
            {
                "email": user.email,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data,
            {
                "detail": PASSWORD_RESET_REQUEST_ACCEPTED_MESSAGE,
            },
        )

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [user.email])
        self.assertIn("Восстановление пароля", mail.outbox[0].subject)
        self.assertIn(
            "http://app.budgetwise.localhost:5173/auth/reset-password?token=",
            mail.outbox[0].body,
        )

        reset_token = PasswordResetToken.objects.get(user=user)

        self.assertEqual(len(reset_token.token_hash), 64)
        self.assertIsNone(reset_token.used_at)
        self.assertTrue(reset_token.can_be_used)

    def test_forgot_password_non_existent_email_returns_same_response_without_email(self):
        response = self.client.post(
            self.forgot_password_url,
            {
                "email": "not-found@example.com",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data,
            {
                "detail": PASSWORD_RESET_REQUEST_ACCEPTED_MESSAGE,
            },
        )

        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(PasswordResetToken.objects.count(), 0)

    def test_forgot_password_inactive_user_returns_same_response_without_email(self):
        User.objects.create_user(
            username="forgot_inactive_user",
            email="forgot-inactive@example.com",
            password=self.password,
            is_active=False,
        )

        response = self.client.post(
            self.forgot_password_url,
            {
                "email": "forgot-inactive@example.com",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data,
            {
                "detail": PASSWORD_RESET_REQUEST_ACCEPTED_MESSAGE,
            },
        )

        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(PasswordResetToken.objects.count(), 0)

    def test_forgot_password_does_not_disclose_account_existence(self):
        user = User.objects.create_user(
            username="forgot_disclosure_user",
            email="forgot-disclosure@example.com",
            password=self.password,
            is_active=True,
        )

        existing_response = self.client.post(
            self.forgot_password_url,
            {
                "email": user.email,
            },
            format="json",
        )

        non_existing_response = self.client.post(
            self.forgot_password_url,
            {
                "email": "forgot-disclosure-not-found@example.com",
            },
            format="json",
        )

        self.assertEqual(existing_response.status_code, status.HTTP_200_OK)
        self.assertEqual(non_existing_response.status_code, status.HTTP_200_OK)
        self.assertEqual(existing_response.data, non_existing_response.data)

    def test_forgot_password_invalid_email_format_returns_400(self):
        response = self.client.post(
            self.forgot_password_url,
            {
                "email": "wrong-email",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])

        error = response.data["error"]

        self.assertEqual(error["status_code"], status.HTTP_400_BAD_REQUEST)
        self.assertEqual(error["code"], "invalid")
        self.assertIn("email", error["field_errors"])

        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(PasswordResetToken.objects.count(), 0)

    def test_forgot_password_email_sending_error_still_returns_generic_response(self):
        user = User.objects.create_user(
            username="forgot_email_error_user",
            email="forgot-email-error@example.com",
            password=self.password,
            is_active=True,
        )

        with patch(
            "apps.users.auth_serializers.send_password_reset_email",
            side_effect=Exception("Email sending failed"),
        ):
            response = self.client.post(
                self.forgot_password_url,
                {
                    "email": user.email,
                },
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data,
            {
                "detail": PASSWORD_RESET_REQUEST_ACCEPTED_MESSAGE,
            },
        )

        self.assertEqual(len(mail.outbox), 0)

    def test_forgot_password_email_rate_limit_returns_429(self):
        user = User.objects.create_user(
            username="forgot_limit_user",
            email="forgot-limit@example.com",
            password=self.password,
            is_active=True,
        )

        for _ in range(3):
            response = self.client.post(
                self.forgot_password_url,
                {
                    "email": user.email,
                },
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.post(
            self.forgot_password_url,
            {
                "email": user.email,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertFalse(response.data["success"])

        error = response.data["error"]

        self.assertEqual(error["status_code"], status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(error["code"], "throttled")
