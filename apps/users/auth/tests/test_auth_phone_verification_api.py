import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.auth.phone_verification import PhoneVerificationProviderError, send_phone_verification_code
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


class _FakeSmsAeroResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


@override_settings(
    PHONE_VERIFICATION_PROVIDER="smsaero",
    SMSAERO_EMAIL="sms@example.com",
    SMSAERO_API_KEY="test-api-key",
    SMSAERO_SIGN="SMS Aero",
    SMSAERO_BASE_URL="https://gate.smsaero.ru/v2",
    SMSAERO_TIMEOUT_SECONDS=5,
    SMSAERO_TEST_MODE=False,
    PHONE_VERIFICATION_SMS_TEXT_TEMPLATE="Код BudgetWise: {code}",
)
class SmsAeroPhoneVerificationProviderTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="smsaero_user",
            email="smsaero-user@example.com",
            password="PhoneVerification123!",
            phone="+79990000000",
        )
        self.verification_code = PhoneVerificationCode.objects.create(
            user=self.user,
            phone="+79990000000",
            code_hash="not-used-in-provider-test",
            expires_at=timezone.now() + timedelta(minutes=15),
        )

    @patch("apps.users.auth.phone_verification.urlopen")
    def test_smsaero_provider_sends_json_request(self, mocked_urlopen):
        mocked_urlopen.return_value = _FakeSmsAeroResponse(
            {
                "success": True,
                "data": {
                    "id": 12345,
                    "from": "SMS Aero",
                    "number": "79990000000",
                    "status": 0,
                },
            }
        )

        result = send_phone_verification_code(
            verification_code=self.verification_code,
            code="123456",
        )

        self.assertTrue(result["sent"])
        self.assertEqual(result["provider"], "smsaero")
        self.assertEqual(result["sms_id"], 12345)

        request = mocked_urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://gate.smsaero.ru/v2/sms/send")
        self.assertEqual(request.get_method(), "POST")
        self.assertIn("Basic ", request.headers["Authorization"])

        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["number"], 79990000000)
        self.assertEqual(payload["sign"], "SMS Aero")
        self.assertEqual(payload["text"], "Код BudgetWise: 123456")

    @override_settings(SMSAERO_TEST_MODE=True)
    @patch("apps.users.auth.phone_verification.urlopen")
    def test_smsaero_provider_uses_test_endpoint_when_enabled(self, mocked_urlopen):
        mocked_urlopen.return_value = _FakeSmsAeroResponse({"success": True, "data": {"id": 1}})

        send_phone_verification_code(
            verification_code=self.verification_code,
            code="123456",
        )

        request = mocked_urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://gate.smsaero.ru/v2/sms/testsend")

    @patch("apps.users.auth.phone_verification.urlopen")
    def test_smsaero_provider_raises_error_on_unsuccessful_response(self, mocked_urlopen):
        mocked_urlopen.return_value = _FakeSmsAeroResponse(
            {
                "success": False,
                "message": "Bad auth",
            }
        )

        with self.assertRaises(PhoneVerificationProviderError) as exc:
            send_phone_verification_code(
                verification_code=self.verification_code,
                code="123456",
            )

        self.assertIn("Bad auth", str(exc.exception))

    @override_settings(SMSAERO_EMAIL="", SMSAERO_API_KEY="")
    def test_smsaero_provider_requires_credentials(self):
        with self.assertRaises(PhoneVerificationProviderError) as exc:
            send_phone_verification_code(
                verification_code=self.verification_code,
                code="123456",
            )

        self.assertIn("SMSAERO_EMAIL", str(exc.exception))
