from datetime import datetime, timezone as datetime_timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase


User = get_user_model()


class HomeGreetingAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="demo",
            email="demo@example.com",
            password="demo-password-123",
            first_name="Данил",
        )

    def test_home_greeting_requires_authentication(self):
        response = self.client.get(reverse("home-greeting"))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(response.data["success"])

    def test_home_greeting_returns_phrase_and_user_name(self):
        self.client.force_authenticate(user=self.user)

        with patch(
            "apps.users.profile.views.timezone.now",
            return_value=datetime(2026, 5, 24, 6, 0, tzinfo=datetime_timezone.utc),
        ):
            response = self.client.get(reverse("home-greeting"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data,
            {
                "phrase": "Добрый день",
                "userName": "Данил",
            },
        )

    def test_home_greeting_falls_back_to_username(self):
        self.user.first_name = ""
        self.user.save(update_fields=["first_name"])
        self.client.force_authenticate(user=self.user)

        response = self.client.get(reverse("home-greeting"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["userName"], "demo")
