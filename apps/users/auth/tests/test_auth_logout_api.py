from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken

from apps.users.auth.serializers import LOGOUT_SUCCESS_MESSAGE


User = get_user_model()


class LogoutAPITests(APITestCase):
    def setUp(self):
        cache.clear()

        self.login_url = reverse("auth:login")
        self.logout_url = reverse("auth:logout")
        self.refresh_url = reverse("auth:token-refresh")

        self.user_password = "user-password-123"
        self.user = User.objects.create_user(
            username="logout_user",
            email="logout-user@example.com",
            password=self.user_password,
            first_name="Logout",
            last_name="User",
        )

    def _login(self):
        response = self.client.post(
            self.login_url,
            {
                "email": self.user.email,
                "password": self.user_password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data["access"], response.data["refresh"]

    def test_logout_success_blacklists_refresh_token(self):
        access_token, refresh_token = self._login()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

        response = self.client.post(
            self.logout_url,
            {"refresh": refresh_token},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["detail"], LOGOUT_SUCCESS_MESSAGE)
        self.assertEqual(BlacklistedToken.objects.count(), 1)

        refresh_response = self.client.post(
            self.refresh_url,
            {"refresh": refresh_token},
            format="json",
        )

        self.assertEqual(refresh_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_requires_authentication(self):
        _, refresh_token = self._login()
        self.client.credentials()

        response = self.client.post(
            self.logout_url,
            {"refresh": refresh_token},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"]["code"], "not_authenticated")

    def test_logout_without_refresh_returns_400(self):
        access_token, _ = self._login()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

        response = self.client.post(
            self.logout_url,
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])

        error = response.data["error"]
        self.assertEqual(error["status_code"], status.HTTP_400_BAD_REQUEST)
        self.assertEqual(error["code"], "required")
        self.assertIn("refresh", error["field_errors"])

    def test_logout_with_invalid_refresh_returns_400(self):
        access_token, _ = self._login()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

        response = self.client.post(
            self.logout_url,
            {"refresh": "invalid-refresh-token"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])

        error = response.data["error"]
        self.assertEqual(error["status_code"], status.HTTP_400_BAD_REQUEST)
        self.assertEqual(error["code"], "invalid_token")
        self.assertIn("refresh", error["field_errors"])
