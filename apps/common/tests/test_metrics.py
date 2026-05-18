from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient


@override_settings(METRICS_ACCESS_TOKEN="test-metrics-token")
class MetricsEndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_metrics_endpoint_requires_token(self):
        response = self.client.get("/metrics/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"]["status_code"], 403)
        self.assertEqual(response.data["error"]["code"], "permission_denied")

    def test_metrics_endpoint_rejects_invalid_token(self):
        response = self.client.get(
            "/metrics/",
            HTTP_X_METRICS_TOKEN="wrong-token",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"]["status_code"], 403)
        self.assertEqual(response.data["error"]["code"], "permission_denied")

    def test_metrics_endpoint_returns_prometheus_metrics(self):
        self.client.get("/health/")

        response = self.client.get(
            "/metrics/",
            HTTP_X_METRICS_TOKEN="test-metrics-token",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        content = response.content.decode("utf-8")

        self.assertIn("http_requests_total", content)
        self.assertIn("http_request_duration_seconds", content)
        self.assertIn("http_requests_in_progress", content)
        self.assertIn("api_errors_total", content)
        self.assertIn("database_up", content)
        self.assertIn("database_check_duration_seconds", content)
        self.assertIn("health_status", content)