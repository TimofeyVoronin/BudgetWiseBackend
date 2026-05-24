from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase


class PwaAPITestCase(APITestCase):
    def setUp(self):
        super().setUp()
        User = get_user_model()
        self.user = User.objects.create_user(
            username="pwa-user",
            email="pwa-user@example.com",
            password="test-password-123",
        )
        self.other_user = User.objects.create_user(
            username="other-pwa-user",
            email="other-pwa-user@example.com",
            password="test-password-123",
        )

    def authenticate(self, user=None):
        self.client.force_authenticate(user=user or self.user)

    def subscription_payload(self, **overrides):
        payload = {
            "deviceId": "browser-device-1",
            "endpoint": "https://push.example.test/subscriptions/one",
            "p256dh": "client-public-key",
            "auth": "client-auth-secret",
            "browser": "Chrome",
            "platform": "Windows",
            "userAgent": "Mozilla/5.0",
            "isActive": True,
        }
        payload.update(overrides)
        return payload
