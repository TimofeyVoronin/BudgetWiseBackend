from django.test import override_settings
from rest_framework import status

from apps.pwa.models import PwaPushSubscription
from apps.pwa.tests.base import PwaAPITestCase


class PwaPushSubscriptionAPITests(PwaAPITestCase):
    def setUp(self):
        super().setUp()
        self.authenticate()

    def test_pwa_meta_returns_capabilities(self):
        response = self.client.get("/api/v1/pwa/meta/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["pushSubscriptionsEnabled"])
        self.assertIn("backgroundSyncEnabled", response.data)
        self.assertEqual(response.data["supportedPushProvider"], "web_push")
        self.assertIn("sync_conflict", response.data["supportedEvents"])
        self.assertIn("pushSubscriptions", response.data["endpoints"])

    def test_create_push_subscription(self):
        response = self.client.post(
            "/api/v1/pwa/push-subscriptions/",
            self.subscription_payload(),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["deviceId"], "browser-device-1")
        self.assertEqual(response.data["provider"], "web_push")
        self.assertEqual(response.data["endpointHost"], "push.example.test")
        self.assertTrue(response.data["isActive"])
        self.assertNotIn("p256dh", response.data)
        self.assertNotIn("auth", response.data)
        self.assertEqual(PwaPushSubscription.objects.filter(user=self.user).count(), 1)

    def test_create_push_subscription_is_idempotent_by_endpoint(self):
        first_response = self.client.post(
            "/api/v1/pwa/push-subscriptions/",
            self.subscription_payload(browser="Chrome"),
            format="json",
        )
        second_response = self.client.post(
            "/api/v1/pwa/push-subscriptions/",
            self.subscription_payload(browser="Firefox"),
            format="json",
        )

        self.assertEqual(first_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(PwaPushSubscription.objects.filter(user=self.user).count(), 1)
        subscription = PwaPushSubscription.objects.get(user=self.user)
        self.assertEqual(subscription.browser, "Firefox")

    def test_list_push_subscriptions_returns_only_current_user_items(self):
        own_subscription = PwaPushSubscription.objects.create(
            user=self.user,
            device_id="own-device",
            endpoint="https://push.example.test/own",
            p256dh="own-key",
            auth="own-auth",
        )
        PwaPushSubscription.objects.create(
            user=self.other_user,
            device_id="other-device",
            endpoint="https://push.example.test/other",
            p256dh="other-key",
            auth="other-auth",
        )

        response = self.client.get("/api/v1/pwa/push-subscriptions/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [item["id"] for item in response.data["items"]]
        self.assertEqual(ids, [str(own_subscription.pk)])

    def test_delete_push_subscription_soft_deletes_item(self):
        subscription = PwaPushSubscription.objects.create(
            user=self.user,
            device_id="own-device",
            endpoint="https://push.example.test/own",
            p256dh="own-key",
            auth="own-auth",
        )

        response = self.client.delete(f"/api/v1/pwa/push-subscriptions/{subscription.pk}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["deleted"])
        subscription.refresh_from_db()
        self.assertFalse(subscription.is_active)
        self.assertIsNotNone(subscription.revoked_at)

    def test_cannot_delete_another_user_subscription(self):
        subscription = PwaPushSubscription.objects.create(
            user=self.other_user,
            device_id="other-device",
            endpoint="https://push.example.test/other",
            p256dh="other-key",
            auth="other-auth",
        )

        response = self.client.delete(f"/api/v1/pwa/push-subscriptions/{subscription.pk}/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @override_settings(PWA_MAX_PUSH_SUBSCRIPTIONS_PER_USER=1)
    def test_create_push_subscription_checks_user_limit(self):
        PwaPushSubscription.objects.create(
            user=self.user,
            device_id="existing-device",
            endpoint="https://push.example.test/existing",
            p256dh="existing-key",
            auth="existing-auth",
        )

        response = self.client.post(
            "/api/v1/pwa/push-subscriptions/",
            self.subscription_payload(endpoint="https://push.example.test/new"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("general", response.data["error"]["field_errors"])

    def test_test_push_subscription_returns_disabled_provider_response(self):
        subscription = PwaPushSubscription.objects.create(
            user=self.user,
            device_id="own-device",
            endpoint="https://push.example.test/own",
            p256dh="own-key",
            auth="own-auth",
        )

        response = self.client.post(f"/api/v1/pwa/push-subscriptions/{subscription.pk}/test/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["sent"])
        self.assertEqual(response.data["provider"], "web_push")
        self.assertEqual(response.data["code"], "push_provider_disabled")
