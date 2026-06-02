from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.auth.email_confirmation import build_email_confirmation_token
from apps.users.models import UserProfileAuditAction, UserProfileAuditLog


User = get_user_model()


@override_settings(
    EMAIL_VERIFICATION_ENABLED=True,
    EMAIL_VERIFICATION_SEND_ASYNC=False,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    FRONTEND_EMAIL_VERIFY_URL="http://localhost:5173/verify-email",
)
class EmailVerificationSoftModeAPITests(APITestCase):
    def setUp(self):
        if hasattr(mail, "outbox"):
            mail.outbox.clear()

        self.password = "SoftModePassword123!"
        self.user = User.objects.create_user(
            username="soft_mode_user",
            email="soft-mode@example.com",
            password=self.password,
            email_verified=False,
            phone_verified=False,
        )
        self.client.force_authenticate(user=self.user)

        self.login_url = reverse("auth:login")
        self.resend_url = reverse("auth:verify-email-resend")
        self.verify_url = reverse("auth:verify-email")
        self.change_password_url = reverse("auth:change-password")
        self.change_email_url = reverse("auth:change-email")
        self.forgot_password_url = reverse("auth:forgot-password-check")

    def test_login_is_allowed_for_unverified_email_and_returns_flags(self):
        self.client.force_authenticate(user=None)

        response = self.client.post(
            self.login_url,
            {
                "email": self.user.email,
                "password": self.password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertFalse(response.data["user"]["isEmailVerified"])
        self.assertTrue(response.data["user"]["emailVerificationRequired"])
        self.assertFalse(response.data["user"]["hasVerifiedContact"])

    def test_resend_email_verification_sends_email_for_unverified_user(self):
        response = self.client.post(self.resend_url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["detail"], "Письмо подтверждения email отправлено.")
        self.assertFalse(response.data["queued"])
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])
        self.assertIn("http://localhost:5173/verify-email?token=", mail.outbox[0].body)

    def test_resend_email_verification_uses_cooldown(self):
        self.client.post(self.resend_url, {}, format="json")

        response = self.client.post(self.resend_url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"]["code"], "email_verification_recently_sent")

    def test_change_password_requires_verified_contact(self):
        response = self.client.post(
            self.change_password_url,
            {
                "currentPassword": self.password,
                "newPassword": "NewSoftModePassword123!",
                "newPasswordConfirm": "NewSoftModePassword123!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"]["code"], "email_not_verified")

    def test_change_password_allowed_after_email_verification(self):
        self.user.email_verified = True
        self.user.email_verified_at = timezone.now()
        self.user.save(update_fields=["email_verified", "email_verified_at"])

        response = self.client.post(
            self.change_password_url,
            {
                "currentPassword": self.password,
                "newPassword": "NewSoftModePassword123!",
                "newPasswordConfirm": "NewSoftModePassword123!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewSoftModePassword123!"))

    def test_change_email_requires_verified_contact(self):
        response = self.client.post(
            self.change_email_url,
            {
                "newEmail": "soft-mode-new@example.com",
                "currentPassword": self.password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"]["code"], "email_not_verified")

    def test_change_email_allowed_after_email_verification_and_resets_verification(self):
        self.user.email_verified = True
        self.user.email_verified_at = timezone.now()
        self.user.save(update_fields=["email_verified", "email_verified_at"])

        response = self.client.post(
            self.change_email_url,
            {
                "newEmail": "soft-mode-new@example.com",
                "currentPassword": self.password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], "soft-mode-new@example.com")
        self.assertFalse(response.data["isEmailVerified"])
        self.assertTrue(response.data["emailVerificationRequired"])
        self.assertEqual(len(mail.outbox), 1)

        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "soft-mode-new@example.com")
        self.assertFalse(self.user.email_verified)
        self.assertIsNone(self.user.email_verified_at)
        self.assertTrue(
            UserProfileAuditLog.objects.filter(
                user=self.user,
                action=UserProfileAuditAction.EMAIL_CHANGED,
            ).exists()
        )

    def test_forgot_password_requires_verified_contact_for_existing_user(self):
        self.client.force_authenticate(user=None)

        response = self.client.post(
            self.forgot_password_url,
            {"email": self.user.email},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"]["code"], "email_not_verified")

    def test_verify_email_marks_email_as_verified(self):
        token = build_email_confirmation_token(self.user)
        self.client.force_authenticate(user=None)

        response = self.client.post(
            self.verify_url,
            {"token": token},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["isEmailVerified"])
        self.assertFalse(response.data["emailVerificationRequired"])

        self.user.refresh_from_db()
        self.assertTrue(self.user.email_verified)
        self.assertIsNotNone(self.user.email_verified_at)
