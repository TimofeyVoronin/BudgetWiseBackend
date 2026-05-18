from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient


class HealthCheckTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_health_check_is_public_and_returns_dependency_checks(self):
        response = self.client.get("/health/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "ok")
        self.assertEqual(response.data["service"], "BudgetWiseBackend")
        self.assertEqual(response.data["version"], "1.0.0")
        self.assertIn("timestamp", response.data)
        self.assertIn("checks", response.data)

        checks = response.data["checks"]

        self.assertIn("database", checks)
        self.assertEqual(checks["database"]["status"], "ok")
        self.assertTrue(checks["database"]["required"])
        self.assertIn("latency_ms", checks["database"])
        self.assertIn("details", checks["database"])
        self.assertIn("vendor", checks["database"]["details"])
        self.assertIn("alias", checks["database"]["details"])

        self.assertIn("redis", checks)
        self.assertEqual(checks["redis"]["status"], "skipped")
        self.assertFalse(checks["redis"]["required"])
        self.assertIn("latency_ms", checks["redis"])
        self.assertIn("details", checks["redis"])

        self.assertIn("celery", checks)
        self.assertEqual(checks["celery"]["status"], "skipped")
        self.assertFalse(checks["celery"]["required"])
        self.assertIn("latency_ms", checks["celery"])
        self.assertIn("details", checks["celery"])

        self.assertIn("external_services", checks)
        self.assertEqual(checks["external_services"]["status"], "skipped")
        self.assertFalse(checks["external_services"]["required"])
        self.assertIn("latency_ms", checks["external_services"])
        self.assertIn("details", checks["external_services"])

    def test_api_root_is_public(self):
        response = self.client.get(reverse("api-root"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["service"], "BudgetWiseBackend API")
        self.assertEqual(response.data["version"], "v1")
        self.assertIn("endpoints", response.data)
        self.assertEqual(response.data["endpoints"]["health"], "/health/")
        self.assertEqual(response.data["endpoints"]["schema"], "/api/schema/")
        self.assertEqual(response.data["endpoints"]["docs"], "/api/docs/")