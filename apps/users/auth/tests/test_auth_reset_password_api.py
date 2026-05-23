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
