import os
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.users.models import UserProfileAuditAction, UserProfileAuditLog


User = get_user_model()


def make_avatar_file(
    name: str = "avatar.jpg",
    content: bytes = b"fake image content",
    content_type: str = "image/jpeg",
) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content, content_type=content_type)


class UserProfileFlowAPITests(APITestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp(prefix="budgetwise-profile-flow-tests-")
        self.media_override = override_settings(
            MEDIA_ROOT=self.media_root,
            MEDIA_URL="/media/",
            USER_PROFILE_AVATAR_MAX_SIZE_BYTES=5 * 1024 * 1024,
            EMAIL_VERIFICATION_ENABLED=False,
        )
        self.media_override.enable()

        self.client = APIClient()
        self.profile_url = reverse("profile-me")
        self.avatar_url = reverse("profile-me-avatar")
        self.user = User.objects.create_user(
            username="profile_flow_user",
            email="profile-flow@example.com",
            password="profile-password-123",
            first_name="Иван",
            last_name="Иванов",
            middle_name="Иванович",
            phone="+79990000000",
            city="Красноярск",
            bio="Backend developer",
        )

    def tearDown(self):
        self.media_override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def authenticate(self):
        self.client.force_authenticate(user=self.user)

    def test_full_profile_flow_updates_avatar_deletes_avatar_and_writes_audit(self):
        self.authenticate()

        initial_response = self.client.get(self.profile_url)
        self.assertEqual(initial_response.status_code, status.HTTP_200_OK)
        self.assertEqual(initial_response.data["email"], "profile-flow@example.com")
        self.assertIsNone(initial_response.data["avatarUrl"])

        update_response = self.client.patch(
            self.profile_url,
            {
                "firstName": "Тимофей",
                "lastName": "Воронин",
                "middleName": "Викторович",
                "phone": "+7 (999) 111-22-33",
                "city": "Санкт-Петербург",
                "bio": "Backend Python Developer",
            },
            format="json",
            HTTP_USER_AGENT="ProfileFlowTest/1.0",
            HTTP_X_FORWARDED_FOR="203.0.113.42, 10.0.0.1",
        )

        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.data["fullName"], "Воронин Тимофей Викторович")
        self.assertEqual(update_response.data["phone"], "+79991112233")
        self.assertEqual(update_response.data["city"], "Санкт-Петербург")

        upload_response = self.client.post(
            self.avatar_url,
            {"avatar": make_avatar_file("avatar.webp", content_type="image/webp")},
            format="multipart",
        )
        self.assertEqual(upload_response.status_code, status.HTTP_200_OK)
        self.assertIn("/media/avatars/user_", upload_response.data["avatarUrl"])

        self.user.refresh_from_db()
        avatar_path = self.user.avatar.path
        self.assertTrue(os.path.exists(avatar_path))

        profile_with_avatar_response = self.client.get(self.profile_url)
        self.assertEqual(profile_with_avatar_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            profile_with_avatar_response.data["avatarUrl"],
            upload_response.data["avatarUrl"],
        )

        delete_response = self.client.delete(self.avatar_url)
        self.assertEqual(delete_response.status_code, status.HTTP_200_OK)
        self.assertEqual(delete_response.data, {"deleted": True, "avatarUrl": None})
        self.assertFalse(os.path.exists(avatar_path))

        actions = list(
            UserProfileAuditLog.objects.filter(user=self.user).values_list("action", flat=True)
        )
        self.assertIn(UserProfileAuditAction.PROFILE_UPDATED, actions)
        self.assertIn(UserProfileAuditAction.NAME_CHANGED, actions)
        self.assertIn(UserProfileAuditAction.PHONE_CHANGED, actions)
        self.assertIn(UserProfileAuditAction.CITY_CHANGED, actions)
        self.assertIn(UserProfileAuditAction.BIO_CHANGED, actions)
        self.assertIn(UserProfileAuditAction.AVATAR_UPLOADED, actions)
        self.assertIn(UserProfileAuditAction.AVATAR_DELETED, actions)

        profile_log = UserProfileAuditLog.objects.get(
            user=self.user,
            action=UserProfileAuditAction.PROFILE_UPDATED,
        )
        self.assertEqual(profile_log.ip_address, "203.0.113.42")
        self.assertEqual(profile_log.user_agent, "ProfileFlowTest/1.0")
        self.assertEqual(profile_log.metadata["source"], "profile_api")

    def test_put_profile_ignores_read_only_identity_fields_and_allows_empty_optional_fields(self):
        self.authenticate()

        response = self.client.put(
            self.profile_url,
            {
                "username": "hacker",
                "email": "hacker@example.com",
                "firstName": "",
                "lastName": "",
                "middleName": "",
                "phone": "",
                "city": "",
                "bio": "",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], "profile_flow_user")
        self.assertEqual(response.data["email"], "profile-flow@example.com")
        self.assertEqual(response.data["firstName"], "")
        self.assertEqual(response.data["lastName"], "")
        self.assertEqual(response.data["middleName"], "")
        self.assertEqual(response.data["phone"], "")
        self.assertEqual(response.data["city"], "")
        self.assertEqual(response.data["bio"], "")
        self.assertEqual(response.data["fullName"], "profile_flow_user")

        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "profile_flow_user")
        self.assertEqual(self.user.email, "profile-flow@example.com")
        self.assertEqual(self.user.first_name, "")
        self.assertEqual(self.user.last_name, "")
        self.assertEqual(self.user.middle_name, "")
        self.assertEqual(self.user.phone, "")
        self.assertEqual(self.user.city, "")
        self.assertEqual(self.user.bio, "")

    def test_profile_validation_returns_field_errors_for_public_fields(self):
        self.authenticate()

        response = self.client.patch(
            self.profile_url,
            {
                "firstName": "Тимофей123",
                "lastName": "Воронин!",
                "middleName": "Викторович@",
                "phone": "phone",
                "city": "Красноярск<script>",
                "bio": "x" * 501,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        field_errors = response.data["error"]["field_errors"]
        self.assertIn("firstName", field_errors)
        self.assertIn("lastName", field_errors)
        self.assertIn("middleName", field_errors)
        self.assertIn("phone", field_errors)
        self.assertIn("city", field_errors)
        self.assertIn("bio", field_errors)

    def test_avatar_upload_rejects_missing_file(self):
        self.authenticate()

        response = self.client.post(self.avatar_url, {}, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        self.assertIn("avatar", response.data["error"]["field_errors"])

    def test_avatar_upload_rejects_invalid_extension_even_with_allowed_content_type(self):
        self.authenticate()

        response = self.client.post(
            self.avatar_url,
            {
                "avatar": make_avatar_file(
                    "avatar.txt",
                    content=b"fake image content",
                    content_type="image/jpeg",
                )
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        self.assertIn("avatar", response.data["error"]["field_errors"])

    def test_audit_uses_remote_addr_when_forwarded_header_absent(self):
        self.authenticate()

        response = self.client.patch(
            self.profile_url,
            {"city": "Москва"},
            format="json",
            REMOTE_ADDR="198.51.100.10",
            HTTP_USER_AGENT="RemoteAddrTest/1.0",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        audit_log = UserProfileAuditLog.objects.get(
            user=self.user,
            action=UserProfileAuditAction.PROFILE_UPDATED,
        )
        self.assertEqual(audit_log.ip_address, "198.51.100.10")
        self.assertEqual(audit_log.user_agent, "RemoteAddrTest/1.0")

    def test_patch_without_actual_changes_does_not_create_audit_events(self):
        self.authenticate()

        response = self.client.patch(
            self.profile_url,
            {
                "firstName": "Иван",
                "lastName": "Иванов",
                "middleName": "Иванович",
                "phone": "+79990000000",
                "city": "Красноярск",
                "bio": "Backend developer",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(UserProfileAuditLog.objects.filter(user=self.user).exists())
