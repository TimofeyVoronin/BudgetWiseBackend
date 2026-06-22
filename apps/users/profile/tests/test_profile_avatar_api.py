import os
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase


User = get_user_model()


def make_avatar_file(
    name: str = "avatar.jpg",
    content: bytes = b"fake image content",
    content_type: str = "image/jpeg",
) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content, content_type=content_type)


class UserProfileAvatarAPITests(APITestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp(prefix="budgetwise-avatar-tests-")
        self.media_override = override_settings(
            MEDIA_ROOT=self.media_root,
            MEDIA_URL="/media/",
            USER_PROFILE_AVATAR_MAX_SIZE_BYTES=5 * 1024 * 1024,
            AVATAR_STORAGE_PROVIDER="local",
        )
        self.media_override.enable()

        self.client = APIClient()
        self.avatar_url = reverse("profile-me-avatar")
        self.profile_url = reverse("profile-me")
        self.user = User.objects.create_user(
            username="avatar_user",
            email="avatar-user@example.com",
            password="profile-password-123",
        )

    def tearDown(self):
        self.media_override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def test_avatar_upload_requires_authentication(self):
        response = self.client.post(
            self.avatar_url,
            {"avatar": make_avatar_file()},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(response.data["success"])

    def test_upload_avatar_saves_file_and_returns_url(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.avatar_url,
            {"avatar": make_avatar_file()},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("avatarUrl", response.data)
        self.assertIn("/media/avatars/user_", response.data["avatarUrl"])
        self.assertEqual(response.data["message"], "Аватар обновлён.")

        self.user.refresh_from_db()
        self.assertTrue(self.user.avatar.name.startswith(f"avatars/user_{self.user.id}/"))
        self.assertTrue(os.path.exists(self.user.avatar.path))

        profile_response = self.client.get(self.profile_url)
        self.assertEqual(profile_response.status_code, status.HTTP_200_OK)
        self.assertEqual(profile_response.data["avatarUrl"], response.data["avatarUrl"])

    def test_upload_avatar_replaces_and_deletes_old_file(self):
        self.client.force_authenticate(user=self.user)

        first_response = self.client.post(
            self.avatar_url,
            {"avatar": make_avatar_file("first.jpg")},
            format="multipart",
        )
        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        old_path = self.user.avatar.path
        self.assertTrue(os.path.exists(old_path))

        second_response = self.client.post(
            self.avatar_url,
            {"avatar": make_avatar_file("second.png", content_type="image/png")},
            format="multipart",
        )

        self.assertEqual(second_response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertFalse(os.path.exists(old_path))
        self.assertTrue(os.path.exists(self.user.avatar.path))
        self.assertIn("/media/avatars/user_", second_response.data["avatarUrl"])

    def test_delete_avatar_removes_file_and_clears_profile_url(self):
        self.client.force_authenticate(user=self.user)

        upload_response = self.client.post(
            self.avatar_url,
            {"avatar": make_avatar_file()},
            format="multipart",
        )
        self.assertEqual(upload_response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        avatar_path = self.user.avatar.path
        self.assertTrue(os.path.exists(avatar_path))

        delete_response = self.client.delete(self.avatar_url)

        self.assertEqual(delete_response.status_code, status.HTTP_200_OK)
        self.assertEqual(delete_response.data, {"deleted": True, "avatarUrl": None})
        self.assertFalse(os.path.exists(avatar_path))

        self.user.refresh_from_db()
        self.assertFalse(bool(self.user.avatar))

        profile_response = self.client.get(self.profile_url)
        self.assertIsNone(profile_response.data["avatarUrl"])

    def test_delete_avatar_is_idempotent(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.delete(self.avatar_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"deleted": True, "avatarUrl": None})

    def test_upload_avatar_rejects_unsupported_type(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.avatar_url,
            {
                "avatar": make_avatar_file(
                    "avatar.gif",
                    content=b"gif-data",
                    content_type="image/gif",
                )
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        field_errors = response.data["error"]["field_errors"]
        self.assertIn("avatar", field_errors)

    @override_settings(USER_PROFILE_AVATAR_MAX_SIZE_BYTES=10)
    def test_upload_avatar_rejects_too_large_file(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.avatar_url,
            {
                "avatar": make_avatar_file(
                    "avatar.jpg",
                    content=b"x" * 11,
                    content_type="image/jpeg",
                )
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        field_errors = response.data["error"]["field_errors"]
        self.assertIn("avatar", field_errors)


@override_settings(
    AVATAR_STORAGE_PROVIDER="cloudinary",
    CLOUDINARY_CLOUD_NAME="demo-cloud",
    CLOUDINARY_API_KEY="demo-key",
    CLOUDINARY_API_SECRET="demo-secret",
    CLOUDINARY_AVATAR_FOLDER="budgetwise/avatars",
    USER_PROFILE_AVATAR_MAX_SIZE_BYTES=5 * 1024 * 1024,
)
class UserProfileCloudinaryAvatarAPITests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.avatar_url = reverse("profile-me-avatar")
        self.profile_url = reverse("profile-me")
        self.user = User.objects.create_user(
            username="cloudinary_avatar_user",
            email="cloudinary-avatar@example.com",
            password="profile-password-123",
        )

    def authenticate(self):
        self.client.force_authenticate(user=self.user)

    def test_upload_avatar_to_cloudinary_stores_url_and_public_id(self):
        self.authenticate()

        with self.settings(AVATAR_STORAGE_PROVIDER="cloudinary"):
            from unittest.mock import patch

            with patch(
                "cloudinary.uploader.upload",
                return_value={
                    "secure_url": "https://res.cloudinary.com/demo/image/upload/v1/budgetwise/avatars/user_1_avatar.jpg",
                    "public_id": "budgetwise/avatars/user_1_avatar",
                },
            ) as upload_mock:
                response = self.client.post(
                    self.avatar_url,
                    {"avatar": make_avatar_file("avatar.jpg")},
                    format="multipart",
                )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["avatarUrl"],
            "https://res.cloudinary.com/demo/image/upload/v1/budgetwise/avatars/user_1_avatar.jpg",
        )
        upload_mock.assert_called_once()

        self.user.refresh_from_db()
        self.assertFalse(bool(self.user.avatar))
        self.assertEqual(
            self.user.avatar_url,
            "https://res.cloudinary.com/demo/image/upload/v1/budgetwise/avatars/user_1_avatar.jpg",
        )
        self.assertEqual(self.user.avatar_public_id, "budgetwise/avatars/user_1_avatar")

        profile_response = self.client.get(self.profile_url)
        self.assertEqual(profile_response.status_code, status.HTTP_200_OK)
        self.assertEqual(profile_response.data["avatarUrl"], response.data["avatarUrl"])

    def test_upload_avatar_to_cloudinary_replaces_previous_cloudinary_avatar(self):
        self.authenticate()
        self.user.avatar_url = "https://res.cloudinary.com/demo/image/upload/v1/budgetwise/avatars/old.jpg"
        self.user.avatar_public_id = "budgetwise/avatars/old_avatar"
        self.user.save(update_fields=["avatar_url", "avatar_public_id"])

        from unittest.mock import patch

        with patch(
            "cloudinary.uploader.upload",
            return_value={
                "secure_url": "https://res.cloudinary.com/demo/image/upload/v1/budgetwise/avatars/new.jpg",
                "public_id": "budgetwise/avatars/new_avatar",
            },
        ), patch("cloudinary.uploader.destroy", return_value={"result": "ok"}) as destroy_mock:
            response = self.client.post(
                self.avatar_url,
                {"avatar": make_avatar_file("new.png", content_type="image/png")},
                format="multipart",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["avatarUrl"], "https://res.cloudinary.com/demo/image/upload/v1/budgetwise/avatars/new.jpg")
        destroy_mock.assert_called_once_with(
            "budgetwise/avatars/old_avatar",
            resource_type="image",
            invalidate=True,
        )

    def test_delete_cloudinary_avatar_clears_url_and_public_id(self):
        self.authenticate()
        self.user.avatar_url = "https://res.cloudinary.com/demo/image/upload/v1/budgetwise/avatars/avatar.jpg"
        self.user.avatar_public_id = "budgetwise/avatars/avatar"
        self.user.save(update_fields=["avatar_url", "avatar_public_id"])

        from unittest.mock import patch

        with patch("cloudinary.uploader.destroy", return_value={"result": "ok"}) as destroy_mock:
            response = self.client.delete(self.avatar_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"deleted": True, "avatarUrl": None})
        destroy_mock.assert_called_once_with(
            "budgetwise/avatars/avatar",
            resource_type="image",
            invalidate=True,
        )

        self.user.refresh_from_db()
        self.assertEqual(self.user.avatar_url, "")
        self.assertEqual(self.user.avatar_public_id, "")
        self.assertFalse(bool(self.user.avatar))
