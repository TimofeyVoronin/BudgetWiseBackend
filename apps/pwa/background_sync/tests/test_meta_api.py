from rest_framework import status

from apps.pwa.tests.base import PwaAPITestCase


class PwaBackgroundSyncMetaAPITests(PwaAPITestCase):
    def setUp(self):
        super().setUp()
        self.authenticate()

    def test_background_sync_meta_returns_finance_sync_endpoints(self):
        response = self.client.get("/api/v1/pwa/background-sync/meta/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["enabled"])
        self.assertEqual(response.data["syncEndpoint"], "/api/v1/finance/sync/push/")
        self.assertEqual(response.data["pullEndpoint"], "/api/v1/finance/sync/pull/")
        self.assertEqual(response.data["statusEndpoint"], "/api/v1/finance/sync/status/")
        self.assertEqual(response.data["operationsEndpoint"], "/api/v1/finance/sync/operations/")
        self.assertGreater(response.data["maxBatchSize"], 0)
