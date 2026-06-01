from __future__ import annotations

from unittest.mock import Mock, patch

from django.conf import settings
from django.test import SimpleTestCase, override_settings

from apps.common.monitoring.health import CHECK_STATUS_OK, check_celery, check_redis, mask_connection_url
from config.celery import app


class CeleryRedisConfigTests(SimpleTestCase):
    def test_celery_app_uses_django_settings_namespace(self):
        self.assertEqual(app.main, "budgetwise")
        self.assertIn(
            "finance-run-due-recurring-transactions-daily",
            settings.CELERY_BEAT_SCHEDULE,
        )

    def test_connection_url_password_is_masked(self):
        masked = mask_connection_url("redis://user:secret@redis:6379/0")

        self.assertEqual(masked, "redis://user:***@redis:6379/0")

    @override_settings(
        REDIS_HEALTH_ENABLED=True,
        REDIS_HEALTH_REQUIRED=True,
        REDIS_HEALTH_URL="redis://redis:6379/0",
    )
    @patch("apps.common.monitoring.health.redis.Redis.from_url")
    def test_redis_health_check_returns_ok_when_ping_succeeds(self, from_url):
        client = Mock()
        client.ping.return_value = True
        from_url.return_value = client

        result = check_redis()

        self.assertEqual(result["status"], CHECK_STATUS_OK)
        self.assertTrue(result["required"])
        self.assertEqual(result["details"]["url"], "redis://redis:6379/0")
        client.ping.assert_called_once()

    @override_settings(
        CELERY_HEALTH_ENABLED=True,
        CELERY_HEALTH_REQUIRED=False,
        CELERY_BROKER_URL="redis://redis:6379/0",
    )
    @patch("apps.common.monitoring.health.celery_current_app.control.ping")
    def test_celery_health_check_returns_ok_when_worker_responds(self, ping):
        ping.return_value = [{"celery@worker": {"ok": "pong"}}]

        result = check_celery()

        self.assertEqual(result["status"], CHECK_STATUS_OK)
        self.assertFalse(result["required"])
        self.assertEqual(result["details"]["workersOnline"], 1)
