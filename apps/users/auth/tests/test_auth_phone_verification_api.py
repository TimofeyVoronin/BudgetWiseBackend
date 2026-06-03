from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import PhoneVerificationCode, UserProfileAuditAction, UserProfileAuditLog


User = get_user_model()


@override_settings(
    EMAIL_VERIFICATION_ENABLED=True,
    PHONE_VERIFICATION_ENABLED=True,
    PHONE_VERIFICATION_SEND_ASYNC=False,
    PHONE_VERIFICATION_CODE_TTL_SECONDS=15 * 60,
    PHONE_VERIFICATION_RESEND_COOLDOWN_SECONDS=60,
    PHONE_VERIFICATION_MAX_ATTEMPTS=5,
    PHONE_DEFAULT_REGION="RU",
)
class PhoneVerificationAPITests(APITestCase):
    def setUp(self):
        self.password = "PhoneVerification123!"
        self.user = User.objects.create_user(
            username="phone_user",
            email="phone-user@example.com",
            password=self.password,
            email_verified=False,
            phone_verified=False,
        )
        self.client.force_authenticate(user=self.user)
        self.send_url = reverse("auth:phone-verification-send")
        self.confirm_url = reverse("auth:phone-verification-confirm")
        self.change_password_url = reverse("auth:change-password")

    @patch("apps.users.auth.phone_verification.generate_phone_verification_code", return_value="123456")
    def test_send_phone_verification_adds_first_phone_and_writes_console_code(self, mocked_code):
        response = self.client.post(
            self.send_url,
            {"phone": "8 (999) 000-00-00"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["phoneDisplay"], "+79990000000")
        self.assertFalse(response.data["queued"])
        self.assertFalse(response.data["isPhoneVerified"])

        self.user.refresh_from_db()
        self.assertEqual(self.user.phone, "+79990000000")
        self.assertFalse(self.user.phone_verified)
        self.assertEqual(PhoneVerificationCode.objects.count(), 1)
        mocked_code.assert_called_once()

    @patch("apps.users.auth.phone_verification.generate_phone_verification_code", return_value="123456")
    def test_confirm_phone_verification_marks_phone_verified(self, mocked_code):
        self.client.post(
            self.send_url,
            {"phone": "+7 999 000 00 00"},
            format="json",
        )

        response = self.client.post(
            self.confirm_url,
            {"phone": "+79990000000", "code": "123456"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["phoneDisplay"], "+79990000000")
        self.assertTrue(response.data["isPhoneVerified"])
        self.assertTrue(response.data["hasVerifiedContact"])

        self.user.refresh_from_db()
        self.assertEqual(self.user.phone, "+79990000000")
        self.assertTrue(self.user.phone_verified)
        self.assertIsNotNone(self.user.phone_verified_at)
        self.assertTrue(PhoneVerificationCode.objects.get().is_confirmed)

    @patch("apps.users.auth.phone_verification.generate_phone_verification_code", return_value="123456")
    def test_phone_verification_uses_resend_cooldown(self, mocked_code):
        self.client.post(
            self.send_url,
            {"phone": "+79990000000"},
            format="json",
        )

        response = self.client.post(
            self.send_url,
            {"phone": "+79990000000"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"]["code"], "phone_verification_recently_sent")

    def test_send_phone_verification_rejects_existing_phone_change_without_verified_contact(self):
        self.user.phone = "+79990000000"
        self.user.email_verified = False
        self.user.phone_verified = False
        self.user.save(update_fields=["phone", "email_verified", "phone_verified"])

        response = self.client.post(
            self.send_url,
            {"phone": "+79991111111"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"]["code"], "email_not_verified")

    @patch("apps.users.auth.phone_verification.generate_phone_verification_code", return_value="123456")
    def test_send_phone_verification_allows_existing_phone_change_with_verified_email(self, mocked_code):
        self.user.phone = "+79990000000"
        self.user.email_verified = True
        self.user.phone_verified = False
        self.user.save(update_fields=["phone", "email_verified", "phone_verified"])

        response = self.client.post(
            self.send_url,
            {"phone": "+79991111111"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["phoneDisplay"], "+79991111111")

        self.user.refresh_from_db()
        self.assertEqual(self.user.phone, "+79991111111")
        self.assertFalse(self.user.phone_verified)
        self.assertTrue(
            UserProfileAuditLog.objects.filter(
                user=self.user,
                action=UserProfileAuditAction.PHONE_CHANGED,
            ).exists()
        )

    def test_send_phone_verification_rejects_duplicate_phone(self):
        User.objects.create_user(
            username="phone_duplicate",
            email="phone-duplicate@example.com",
            password="PhoneVerification123!",
            phone="+79990000000",
        )

        response = self.client.post(
            self.send_url,
            {"phone": "89990000000"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"]["code"], "unique")

    @patch("apps.users.auth.phone_verification.generate_phone_verification_code", return_value="123456")
    def test_confirm_phone_verification_rejects_wrong_code(self, mocked_code):
        self.client.post(
            self.send_url,
            {"phone": "+79990000000"},
            format="json",
        )

        response = self.client.post(
            self.confirm_url,
            {"phone": "+79990000000", "code": "654321"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"]["code"], "phone_verification_invalid_code")

        verification_code = PhoneVerificationCode.objects.get()
        self.assertEqual(verification_code.attempts_count, 1)

    def test_change_password_allowed_after_phone_verification(self):
        self.user.phone = "+79990000000"
        self.user.email_verified = False
        self.user.phone_verified = True
        self.user.save(update_fields=["phone", "email_verified", "phone_verified"])

        response = self.client.post(
            self.change_password_url,
            {
                "currentPassword": self.password,
                "newPassword": "NewPhoneVerification123!",
                "newPasswordConfirm": "NewPhoneVerification123!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewPhoneVerification123!"))
