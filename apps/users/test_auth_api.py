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


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    FRONTEND_EMAIL_VERIFY_URL="http://app.budgetwise.localhost:5173/auth/verify-email",
)
@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    FRONTEND_EMAIL_VERIFY_URL="http://app.budgetwise.localhost:5173/auth/verify-email",
    REGISTRATION_REQUIRE_EMAIL_CONFIRMATION=False,
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

    @override_settings(REGISTRATION_REQUIRE_EMAIL_CONFIRMATION=True)
    def test_register_with_email_confirmation_creates_inactive_user_and_sends_email(self):
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
        self.assertFalse(response.data["is_active"])
        self.assertEqual(
            response.data["detail"],
            "Пользователь зарегистрирован. Для активации аккаунта подтвердите email.",
        )

        user = User.objects.get(email="register-with-confirmation@example.com")
        self.assertFalse(user.is_active)
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
            is_active=False,
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
        self.assertEqual(
            response.data["detail"],
            "Email подтверждён. Аккаунт активирован.",
        )

        user.refresh_from_db()
        self.assertTrue(user.is_active)

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
            "apps.users.serializers.load_email_confirmation_token",
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

    def test_verify_email_with_already_active_user_returns_400(self):
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

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])

        error = response.data["error"]
        self.assertEqual(error["status_code"], status.HTTP_400_BAD_REQUEST)
        self.assertEqual(error["code"], "token_already_used")
        self.assertIn("token", error["field_errors"])

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
            "apps.users.serializers.send_password_reset_email",
            side_effect=RuntimeError("SMTP error"),
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


class ResetPasswordAPITests(APITestCase):
    def setUp(self):
        cache.clear()

        self.reset_password_url = reverse("auth:reset-password")
        self.login_url = reverse("auth:login")

        self.old_password = "OldPassword123!"
        self.new_password = "NewPassword123!"

        self.user = User.objects.create_user(
            username="reset_password_user",
            email="reset-password-user@example.com",
            password=self.old_password,
            is_active=True,
        )

    def test_reset_password_with_valid_token_changes_password_and_marks_token_used(self):
        token = issue_password_reset_token(self.user)

        response = self.client.post(
            self.reset_password_url,
            {
                "token": token,
                "password": self.new_password,
                "password_confirm": self.new_password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data,
            {
                "detail": PASSWORD_RESET_SUCCESS_MESSAGE,
            },
        )

        self.user.refresh_from_db()
        self.assertFalse(self.user.check_password(self.old_password))
        self.assertTrue(self.user.check_password(self.new_password))

        token_record = PasswordResetToken.objects.get(user=self.user)
        self.assertIsNotNone(token_record.used_at)
        self.assertFalse(token_record.can_be_used)

    def test_reset_password_old_password_no_longer_works_and_new_password_works(self):
        token = issue_password_reset_token(self.user)

        reset_response = self.client.post(
            self.reset_password_url,
            {
                "token": token,
                "password": self.new_password,
                "password_confirm": self.new_password,
            },
            format="json",
        )

        self.assertEqual(reset_response.status_code, status.HTTP_200_OK)

        old_login_response = self.client.post(
            self.login_url,
            {
                "email": self.user.email,
                "password": self.old_password,
            },
            format="json",
        )

        self.assertEqual(old_login_response.status_code, status.HTTP_401_UNAUTHORIZED)

        new_login_response = self.client.post(
            self.login_url,
            {
                "email": self.user.email,
                "password": self.new_password,
            },
            format="json",
        )

        self.assertEqual(new_login_response.status_code, status.HTTP_200_OK)
        self.assertIn("access", new_login_response.data)
        self.assertIn("refresh", new_login_response.data)

    def test_reset_password_reused_token_returns_410_and_does_not_change_password_again(self):
        token = issue_password_reset_token(self.user)

        first_response = self.client.post(
            self.reset_password_url,
            {
                "token": token,
                "password": self.new_password,
                "password_confirm": self.new_password,
            },
            format="json",
        )

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)

        second_response = self.client.post(
            self.reset_password_url,
            {
                "token": token,
                "password": "AnotherPassword123!",
                "password_confirm": "AnotherPassword123!",
            },
            format="json",
        )

        self.assertEqual(second_response.status_code, status.HTTP_410_GONE)
        self.assertFalse(second_response.data["success"])

        error = second_response.data["error"]

        self.assertEqual(error["status_code"], status.HTTP_410_GONE)
        self.assertEqual(error["code"], "token_already_used")
        self.assertEqual(error["detail"], "Ссылка восстановления пароля уже использована.")

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.new_password))
        self.assertFalse(self.user.check_password("AnotherPassword123!"))

    def test_reset_password_with_expired_token_returns_410(self):
        token = issue_password_reset_token(self.user)

        PasswordResetToken.objects.filter(user=self.user).update(
            expires_at=timezone.now() - timedelta(minutes=1),
        )

        response = self.client.post(
            self.reset_password_url,
            {
                "token": token,
                "password": self.new_password,
                "password_confirm": self.new_password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_410_GONE)
        self.assertFalse(response.data["success"])

        error = response.data["error"]

        self.assertEqual(error["status_code"], status.HTTP_410_GONE)
        self.assertEqual(error["code"], "token_expired")
        self.assertEqual(
            error["detail"],
            "Срок действия ссылки восстановления пароля истёк.",
        )

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.old_password))

    def test_reset_password_with_invalid_token_returns_404(self):
        response = self.client.post(
            self.reset_password_url,
            {
                "token": "wrong-token",
                "password": self.new_password,
                "password_confirm": self.new_password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(response.data["success"])

        error = response.data["error"]

        self.assertEqual(error["status_code"], status.HTTP_404_NOT_FOUND)
        self.assertEqual(error["code"], "invalid_token")
        self.assertEqual(
            error["detail"],
            "Недействительная ссылка восстановления пароля.",
        )

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.old_password))

    def test_reset_password_with_password_mismatch_returns_400(self):
        token = issue_password_reset_token(self.user)

        response = self.client.post(
            self.reset_password_url,
            {
                "token": token,
                "password": self.new_password,
                "password_confirm": "AnotherPassword123!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])

        error = response.data["error"]

        self.assertEqual(error["status_code"], status.HTTP_400_BAD_REQUEST)
        self.assertEqual(error["code"], "password_mismatch")
        self.assertIn("password_confirm", error["field_errors"])

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.old_password))

        token_record = PasswordResetToken.objects.get(user=self.user)
        self.assertIsNone(token_record.used_at)
        self.assertTrue(token_record.can_be_used)

    def test_reset_password_without_required_fields_returns_400(self):
        response = self.client.post(
            self.reset_password_url,
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])

        error = response.data["error"]

        self.assertEqual(error["status_code"], status.HTTP_400_BAD_REQUEST)
        self.assertEqual(error["code"], "required")
        self.assertIn("token", error["field_errors"])
        self.assertIn("password", error["field_errors"])
        self.assertIn("password_confirm", error["field_errors"])

    def test_reset_password_invalidates_other_active_tokens_for_same_user(self):
        first_token = issue_password_reset_token(self.user)
        second_token = issue_password_reset_token(self.user)

        self.assertEqual(
            PasswordResetToken.objects.filter(
                user=self.user,
                used_at__isnull=True,
            ).count(),
            2,
        )

        response = self.client.post(
            self.reset_password_url,
            {
                "token": first_token,
                "password": self.new_password,
                "password_confirm": self.new_password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(
            PasswordResetToken.objects.filter(
                user=self.user,
                used_at__isnull=True,
            ).count(),
            0,
        )

        second_response = self.client.post(
            self.reset_password_url,
            {
                "token": second_token,
                "password": "AnotherPassword123!",
                "password_confirm": "AnotherPassword123!",
            },
            format="json",
        )

        self.assertEqual(second_response.status_code, status.HTTP_410_GONE)
        self.assertEqual(
            second_response.data["error"]["code"],
            "token_already_used",
        )