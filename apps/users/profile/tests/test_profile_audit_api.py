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


class UserProfileAuditAPITests(APITestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp(prefix="budgetwise-profile-audit-tests-")
        self.media_override = override_settings(
            MEDIA_ROOT=self.media_root,
            MEDIA_URL="/media/",
            USER_PROFILE_AVATAR_MAX_SIZE_BYTES=5 * 1024 * 1024,
            AVATAR_STORAGE_PROVIDER="local",
        )
        self.media_override.enable()

        self.client = APIClient()
        self.profile_url = reverse("profile-me")
        self.avatar_url = reverse("profile-me-avatar")
        self.current_user_url = reverse("users:current-user")
        self.user = User.objects.create_user(
            username="profile_audit_user",
            email="profile-audit@example.com",
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

    def test_patch_profile_creates_audit_events_for_changed_fields(self):
        self.authenticate()

        response = self.client.patch(
            self.profile_url,
            {
                "firstName": "Тимофей",
                "lastName": "Воронин",
                "middleName": "Викторович",
                "phone": "+7 (999) 111-22-33",
                "city": "Москва",
                "bio": "Python Backend Developer",
            },
            format="json",
            HTTP_USER_AGENT="AuditTest/1.0",
            HTTP_X_FORWARDED_FOR="203.0.113.10, 10.0.0.1",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        logs = list(UserProfileAuditLog.objects.filter(user=self.user).order_by("id"))
        actions = [log.action for log in logs]
        self.assertEqual(
            actions,
            [
                UserProfileAuditAction.PROFILE_UPDATED,
                UserProfileAuditAction.NAME_CHANGED,
                UserProfileAuditAction.PHONE_CHANGED,
                UserProfileAuditAction.CITY_CHANGED,
                UserProfileAuditAction.BIO_CHANGED,
            ],
        )

        profile_log = logs[0]
        self.assertEqual(
            profile_log.changed_fields,
            ["firstName", "lastName", "middleName", "phone", "city", "bio"],
        )
        self.assertEqual(profile_log.old_values["firstName"], "Иван")
        self.assertEqual(profile_log.new_values["firstName"], "Тимофей")
        self.assertEqual(profile_log.old_values["city"], "Красноярск")
        self.assertEqual(profile_log.new_values["city"], "Москва")
        self.assertEqual(profile_log.metadata["source"], "profile_api")
        self.assertEqual(profile_log.ip_address, "203.0.113.10")
        self.assertEqual(profile_log.user_agent, "AuditTest/1.0")

        name_log = UserProfileAuditLog.objects.get(
            user=self.user,
            action=UserProfileAuditAction.NAME_CHANGED,
        )
        self.assertEqual(name_log.changed_fields, ["firstName", "lastName", "middleName"])

    def test_put_profile_without_changes_does_not_create_audit_events(self):
        self.authenticate()

        response = self.client.put(
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

    def test_current_user_patch_also_writes_profile_audit(self):
        self.authenticate()

        response = self.client.patch(
            self.current_user_url,
            {"city": "Санкт-Петербург"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        audit_log = UserProfileAuditLog.objects.get(
            user=self.user,
            action=UserProfileAuditAction.CITY_CHANGED,
        )
        self.assertEqual(audit_log.old_values, {"city": "Красноярск"})
        self.assertEqual(audit_log.new_values, {"city": "Санкт-Петербург"})

    def test_avatar_upload_writes_audit_event(self):
        self.authenticate()

        response = self.client.post(
            self.avatar_url,
            {"avatar": make_avatar_file()},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        audit_log = UserProfileAuditLog.objects.get(
            user=self.user,
            action=UserProfileAuditAction.AVATAR_UPLOADED,
        )
        self.assertEqual(audit_log.changed_fields, ["avatar"])
        self.assertIsNone(audit_log.old_values["avatar"])
        self.assertTrue(audit_log.new_values["avatar"].startswith(f"avatars/user_{self.user.id}/"))
        self.assertEqual(audit_log.metadata["source"], "profile_avatar_api")

    def test_avatar_replacement_writes_old_and_new_file_names(self):
        self.authenticate()

        first_response = self.client.post(
            self.avatar_url,
            {"avatar": make_avatar_file("first.jpg")},
            format="multipart",
        )
        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        old_avatar_name = self.user.avatar.name
        self.assertTrue(os.path.exists(self.user.avatar.path))

        second_response = self.client.post(
            self.avatar_url,
            {"avatar": make_avatar_file("second.png", content_type="image/png")},
            format="multipart",
        )

        self.assertEqual(second_response.status_code, status.HTTP_200_OK)
        replacement_log = UserProfileAuditLog.objects.filter(
            user=self.user,
            action=UserProfileAuditAction.AVATAR_UPLOADED,
        ).latest("id")
        self.assertEqual(replacement_log.old_values["avatar"], old_avatar_name)
        self.assertNotEqual(replacement_log.new_values["avatar"], old_avatar_name)

    def test_avatar_delete_writes_audit_event(self):
        self.authenticate()

        upload_response = self.client.post(
            self.avatar_url,
            {"avatar": make_avatar_file()},
            format="multipart",
        )
        self.assertEqual(upload_response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        avatar_name = self.user.avatar.name

        delete_response = self.client.delete(self.avatar_url)

        self.assertEqual(delete_response.status_code, status.HTTP_200_OK)
        audit_log = UserProfileAuditLog.objects.get(
            user=self.user,
            action=UserProfileAuditAction.AVATAR_DELETED,
        )
        self.assertEqual(audit_log.changed_fields, ["avatar"])
        self.assertEqual(audit_log.old_values["avatar"], avatar_name)
        self.assertIsNone(audit_log.new_values["avatar"])

    def test_idempotent_avatar_delete_does_not_create_audit_event(self):
        self.authenticate()

        response = self.client.delete(self.avatar_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(UserProfileAuditLog.objects.filter(user=self.user).exists())
