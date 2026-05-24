from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from apps.finance.models import Receipt, ReceiptAuditAction, ReceiptAuditLog, ReceiptStatus
from apps.finance.receipts.provider import MockReceiptProviderClient, normalize_proverkacheka_response


User = get_user_model()
VALID_QR = "t=20240522T1421&s=270.00&fn=9280440300891234&i=12345&fp=987654321&n=1"


class ReceiptQRImportAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="receipt_qr_user",
            email="receipt_qr@example.com",
            password="StrongPass123!",
        )
        self.client = APIClient()
        self.url = "/api/v1/finance/receipts/qr/"

    def authenticate(self):
        self.client.force_authenticate(user=self.user)

    def provider_payload(self):
        return {
            "code": 1,
            "first": 1,
            "data": {
                "json": {
                    "user": "ООО Ромашка",
                    "retailPlaceAddres": "г. Москва, ул. Примерная, 1",
                    "userInn": "7700000000",
                    "ticketDate": "2024-05-22T14:21:00",
                    "requestNumber": 12,
                    "shiftNumber": 3,
                    "operator": "Иванов",
                    "operationType": 1,
                    "items": [
                        {
                            "name": "Молоко",
                            "price": 9000,
                            "quantity": 1,
                            "sum": 9000,
                        },
                        {
                            "name": "Хлеб",
                            "price": 18000,
                            "quantity": 1,
                            "sum": 18000,
                        },
                    ],
                    "totalSum": 27000,
                    "cashTotalSum": 0,
                    "ecashTotalSum": 27000,
                    "fiscalDriveNumber": "9280440300891234",
                    "fiscalDocumentNumber": "12345",
                    "fiscalSign": "987654321",
                },
                "html": "<p>receipt</p>",
            },
        }

    def test_qr_endpoint_requires_authentication(self):
        response = self.client.get(self.url, {"qrRaw": VALID_QR, "fetchProvider": "false"})

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_qr_endpoint_registers_parsed_receipt_without_provider(self):
        self.authenticate()

        response = self.client.get(self.url, {"qrRaw": VALID_QR, "fetchProvider": "false"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["created"])
        self.assertFalse(response.data["isDuplicate"])
        self.assertEqual(response.data["providerStatus"], "skipped")
        self.assertIsNone(response.data["providerError"])
        self.assertEqual(response.data["receipt"]["status"], ReceiptStatus.PARSED)
        self.assertEqual(response.data["receipt"]["total_amount"], "270.00")
        self.assertEqual(Receipt.objects.filter(user=self.user).count(), 1)

    def test_qr_endpoint_returns_existing_receipt_for_duplicate_qr(self):
        self.authenticate()
        first = self.client.get(self.url, {"qrRaw": VALID_QR, "fetchProvider": "false"})
        second = self.client.get(self.url, {"qrRaw": VALID_QR, "fetchProvider": "false"})

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertTrue(first.data["created"])
        self.assertFalse(second.data["created"])
        self.assertTrue(second.data["isDuplicate"])
        self.assertEqual(second.data["receipt"]["id"], first.data["receipt"]["id"])
        self.assertEqual(Receipt.objects.filter(user=self.user).count(), 1)


    @patch("apps.finance.receipts.views.get_receipt_provider_client")
    def test_qr_endpoint_refetches_items_for_existing_parsed_receipt(self, mocked_get_client):
        self.authenticate()
        first = self.client.get(self.url, {"qrRaw": VALID_QR, "fetchProvider": "false"})
        details = normalize_proverkacheka_response(self.provider_payload())
        mocked_get_client.return_value = MockReceiptProviderClient(receipt=details)

        second = self.client.get(self.url, {"qrRaw": VALID_QR, "fetchProvider": "true"})

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertTrue(first.data["created"])
        self.assertFalse(second.data["created"])
        self.assertTrue(second.data["isDuplicate"])
        self.assertEqual(second.data["providerStatus"], "fetched")
        self.assertEqual(second.data["receipt"]["id"], first.data["receipt"]["id"])
        self.assertEqual(second.data["receipt"]["status"], ReceiptStatus.FETCHED)
        self.assertEqual(len(second.data["receipt"]["items"]), 2)

    def test_qr_endpoint_rejects_invalid_qr(self):
        self.authenticate()

        response = self.client.get(self.url, {"qrRaw": "not-a-qr"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Receipt.objects.filter(user=self.user).count(), 0)

    @override_settings(PROVERKACHEKA_ENABLED=False, PROVERKACHEKA_API_TOKEN="")
    def test_qr_endpoint_returns_response_even_when_provider_is_disabled(self):
        self.authenticate()

        response = self.client.get(self.url, {"qrRaw": VALID_QR})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["created"])
        self.assertEqual(response.data["providerStatus"], "failed")
        self.assertEqual(response.data["providerError"]["code"], "receipt_provider_disabled")
        self.assertEqual(response.data["receipt"]["status"], ReceiptStatus.PARSED)
        self.assertTrue(
            ReceiptAuditLog.objects.filter(
                receipt_id=response.data["receipt"]["id"],
                action=ReceiptAuditAction.PROVIDER_FETCH_FAILED,
            ).exists()
        )

    @patch("apps.finance.receipts.views.get_receipt_provider_client")
    def test_qr_endpoint_fetches_provider_details_and_items(self, mocked_get_client):
        self.authenticate()
        details = normalize_proverkacheka_response(self.provider_payload())
        mocked_get_client.return_value = MockReceiptProviderClient(receipt=details)

        response = self.client.get(self.url, {"qrRaw": VALID_QR})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["created"])
        self.assertEqual(response.data["providerStatus"], "fetched")
        self.assertIsNone(response.data["providerError"])
        self.assertEqual(response.data["receipt"]["status"], ReceiptStatus.FETCHED)
        self.assertEqual(response.data["receipt"]["store_name"], "ООО Ромашка")
        self.assertEqual(response.data["receipt"]["seller_inn"], "7700000000")
        self.assertEqual(len(response.data["receipt"]["items"]), 2)
        self.assertEqual(Receipt.objects.get(user=self.user).total_amount, Decimal("270.00"))
