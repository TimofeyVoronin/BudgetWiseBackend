from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient


User = get_user_model()


class UsersProfileAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.user = User.objects.create_user(
            username="demo",
            email="demo@example.com",
            password="demo-password-123",
        )
        self.admin = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="admin-password-123",
        )
        self.other_user = User.objects.create_user(
            username="other",
            email="other@example.com",
            password="other-password-123",
        )

    def test_current_user_requires_authentication(self):
        response = self.client.get(reverse("users:current-user"))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"]["status_code"], 401)

    def test_current_user_get_and_patch(self):
        self.client.force_authenticate(user=self.user)

        get_response = self.client.get(reverse("users:current-user"))

        self.assertEqual(get_response.status_code, status.HTTP_200_OK)
        self.assertEqual(get_response.data["username"], "demo")
        self.assertEqual(get_response.data["role"], "user")

        patch_response = self.client.patch(
            reverse("users:current-user"),
            data={
                "first_name": "Timofey",
                "last_name": "Demo",
            },
            format="json",
        )

        self.assertEqual(patch_response.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_response.data["first_name"], "Timofey")
        self.assertEqual(patch_response.data["last_name"], "Demo")

        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Timofey")
        self.assertEqual(self.user.last_name, "Demo")
