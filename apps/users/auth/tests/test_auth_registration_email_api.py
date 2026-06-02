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


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    EMAIL_VERIFICATION_SEND_ASYNC=False,
    FRONTEND_EMAIL_VERIFY_URL="http://app.budgetwise.localhost:5173/auth/verify-email",
    EMAIL_VERIFICATION_ENABLED=False,
)
class RegistrationAndEmailVerificationAPITests(APITestCase):
    def setUp(self):
        cache.clear()

        self.register_url = reverse("auth:register")
        self.verify_email_url = reverse("auth:verify-email")

        self.password = "StrongRegisterPassword123!"

    def test_register_success_creates_active_user_without_email_confirmation(self):
        response = self.client.post(
            self.register_url,
            {
                "email": "register-user@example.com",
                "password": self.password,
                "password_confirm": self.password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.assertIn("id", response.data)
        self.assertEqual(response.data["email"], "register-user@example.com")
        self.assertEqual(response.data["username"], "register-user")
        self.assertTrue(response.data["is_active"])
        self.assertEqual(
            response.data["detail"],
            "Пользователь зарегистрирован. Теперь можно войти в аккаунт.",
        )

        user = User.objects.get(email="register-user@example.com")
        self.assertTrue(user.is_active)
        self.assertTrue(user.check_password(self.password))

        self.assertEqual(len(mail.outbox), 0)

    @override_settings(EMAIL_VERIFICATION_ENABLED=True)
    def test_register_with_email_verification_creates_active_unverified_user_and_sends_email(self):
        response = self.client.post(
            self.register_url,
            {
                "email": "register-with-confirmation@example.com",
                "password": self.password,
                "password_confirm": self.password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.assertIn("id", response.data)
        self.assertEqual(
            response.data["email"],
            "register-with-confirmation@example.com",
        )
        self.assertEqual(
            response.data["username"],
            "register-with-confirmation",
        )
        self.assertTrue(response.data["is_active"])
        self.assertFalse(response.data["isEmailVerified"])
        self.assertTrue(response.data["emailVerificationRequired"])
        self.assertEqual(
            response.data["detail"],
            "Пользователь зарегистрирован. Для защиты аккаунта подтвердите email.",
        )

        user = User.objects.get(email="register-with-confirmation@example.com")
        self.assertTrue(user.is_active)
        self.assertFalse(user.email_verified)
        self.assertTrue(user.check_password(self.password))

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].to,
            ["register-with-confirmation@example.com"],
        )
        self.assertIn("Подтверждение email", mail.outbox[0].subject)
        self.assertIn(
            "http://app.budgetwise.localhost:5173/auth/verify-email?token=",
            mail.outbox[0].body,
        )

    def test_register_normalizes_email_to_lowercase(self):
        response = self.client.post(
            self.register_url,
            {
                "email": "REGISTER-UPPER@EXAMPLE.COM",
                "password": self.password,
                "password_confirm": self.password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["email"], "register-upper@example.com")

        self.assertTrue(
            User.objects.filter(email="register-upper@example.com").exists()
        )

    def test_register_generates_unique_username_from_email(self):
        User.objects.create_user(
            username="duplicate",
            email="old-user@example.com",
            password=self.password,
        )

        response = self.client.post(
            self.register_url,
            {
                "email": "duplicate@example.com",
                "password": self.password,
                "password_confirm": self.password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["username"], "duplicate_1")

    def test_register_with_existing_email_returns_400(self):
        User.objects.create_user(
            username="existing_user",
            email="existing@example.com",
            password=self.password,
        )

        response = self.client.post(
            self.register_url,
            {
                "email": "existing@example.com",
                "password": self.password,
                "password_confirm": self.password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])

        error = response.data["error"]
        self.assertEqual(error["status_code"], status.HTTP_400_BAD_REQUEST)
        self.assertEqual(error["code"], "unique")
        self.assertIn("email", error["field_errors"])

    def test_register_with_existing_email_case_insensitive_returns_400(self):
        User.objects.create_user(
            username="existing_case_user",
            email="existing-case@example.com",
            password=self.password,
        )

        response = self.client.post(
            self.register_url,
            {
                "email": "EXISTING-CASE@EXAMPLE.COM",
                "password": self.password,
                "password_confirm": self.password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        error = response.data["error"]
        self.assertEqual(error["code"], "unique")
        self.assertIn("email", error["field_errors"])

    def test_register_with_password_mismatch_returns_400(self):
        response = self.client.post(
            self.register_url,
            {
                "email": "password-mismatch@example.com",
                "password": self.password,
                "password_confirm": "AnotherStrongPassword123!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])

        error = response.data["error"]
        self.assertEqual(error["status_code"], status.HTTP_400_BAD_REQUEST)
        self.assertEqual(error["code"], "password_mismatch")
        self.assertIn("password_confirm", error["field_errors"])

    def test_register_without_required_fields_returns_400(self):
        response = self.client.post(
            self.register_url,
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])

        error = response.data["error"]
        self.assertEqual(error["status_code"], status.HTTP_400_BAD_REQUEST)
        self.assertEqual(error["code"], "required")
        self.assertIn("email", error["field_errors"])
        self.assertIn("password", error["field_errors"])
        self.assertIn("password_confirm", error["field_errors"])

    def test_verify_email_success_activates_user(self):
        user = User.objects.create_user(
            username="verify_user",
            email="verify-user@example.com",
            password=self.password,
            is_active=True,
            email_verified=False,
        )
        token = build_email_confirmation_token(user)

        response = self.client.post(
            self.verify_email_url,
            {
                "token": token,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], user.id)
        self.assertEqual(response.data["email"], user.email)
        self.assertTrue(response.data["is_active"])
        self.assertTrue(response.data["isEmailVerified"])
        self.assertFalse(response.data["emailVerificationRequired"])
        self.assertEqual(response.data["detail"], "Email подтверждён.")

        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertTrue(user.email_verified)
        self.assertIsNotNone(user.email_verified_at)

    def test_verify_email_with_invalid_token_returns_400(self):
        response = self.client.post(
            self.verify_email_url,
            {
                "token": "wrong-token",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])

        error = response.data["error"]
        self.assertEqual(error["status_code"], status.HTTP_400_BAD_REQUEST)
        self.assertEqual(error["code"], "invalid_token")
        self.assertIn("token", error["field_errors"])

    def test_verify_email_with_expired_token_returns_400(self):
        with patch(
            "apps.users.auth.serializers.load_email_confirmation_token",
            side_effect=SignatureExpired("expired"),
        ):
            response = self.client.post(
                self.verify_email_url,
                {
                    "token": "expired-token",
                },
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])

        error = response.data["error"]
        self.assertEqual(error["status_code"], status.HTTP_400_BAD_REQUEST)
        self.assertEqual(error["code"], "token_expired")
        self.assertIn("token", error["field_errors"])

    def test_verify_email_with_already_verified_user_returns_200(self):
        user = User.objects.create_user(
            username="already_active_user",
            email="already-active@example.com",
            password=self.password,
            is_active=True,
        )
        token = build_email_confirmation_token(user)

        response = self.client.post(
            self.verify_email_url,
            {
                "token": token,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["detail"], "Email уже подтверждён.")
        self.assertTrue(response.data["isEmailVerified"])

    def test_verify_email_without_token_returns_400(self):
        response = self.client.post(
            self.verify_email_url,
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])

        error = response.data["error"]
        self.assertEqual(error["status_code"], status.HTTP_400_BAD_REQUEST)
        self.assertEqual(error["code"], "required")
        self.assertIn("token", error["field_errors"])
