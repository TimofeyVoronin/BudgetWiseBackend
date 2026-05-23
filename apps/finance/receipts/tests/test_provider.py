import json
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch
from urllib.error import URLError
from urllib.parse import parse_qs

from django.test import SimpleTestCase, override_settings

from apps.finance.receipts.provider import (
    FiscalReceiptDetails,
    MockReceiptProviderClient,
    ProverkaChekaClient,
    ReceiptProviderError,
    normalize_proverkacheka_response,
)
from apps.finance.receipts.qr import parse_receipt_qr


VALID_QR = "t=20240522T1421&s=1250.50&fn=9280440300891234&i=12345&fp=987654321&n=1"


class FakeHTTPResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        if isinstance(self.payload, bytes):
            return self.payload
        return json.dumps(self.payload).encode("utf-8")


class ReceiptProviderTests(SimpleTestCase):
    def success_payload(self):
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
                            "price": 6050,
                            "quantity": 2,
                            "sum": 12100,
                        },
                    ],
                    "totalSum": 21100,
                    "cashTotalSum": 0,
                    "ecashTotalSum": 21100,
                    "fiscalDriveNumber": "9280440300891234",
                    "fiscalDocumentNumber": "12345",
                    "fiscalSign": "987654321",
                },
                "html": "<p>receipt</p>",
            },
        }

    def test_normalize_success_response(self):
        details = normalize_proverkacheka_response(self.success_payload())

        self.assertEqual(details.provider, "proverkacheka")
        self.assertTrue(details.first)
        self.assertEqual(details.organization_name, "ООО Ромашка")
        self.assertEqual(details.seller_inn, "7700000000")
        self.assertEqual(details.operation_type_label, "Приход")
        self.assertEqual(details.total_amount, Decimal("211.00"))
        self.assertEqual(details.card_total_amount, Decimal("211.00"))
        self.assertEqual(len(details.items), 2)
        self.assertEqual(details.items[0].name, "Молоко")
        self.assertEqual(details.items[0].price, Decimal("90.00"))
        self.assertEqual(details.items[1].amount, Decimal("121.00"))
        self.assertEqual(details.fiscal_key, "9280440300891234:12345:987654321")

    def test_normalize_provider_pending_code_raises_error(self):
        with self.assertRaises(ReceiptProviderError) as context:
            normalize_proverkacheka_response({"code": 2, "first": 0, "data": {}})

        self.assertEqual(context.exception.code, "receipt_provider_pending")
        self.assertEqual(context.exception.provider_code, 2)

    def test_normalize_invalid_response_without_data_json_raises_error(self):
        with self.assertRaises(ReceiptProviderError) as context:
            normalize_proverkacheka_response({"code": 1, "first": 1, "data": {}})

        self.assertEqual(context.exception.code, "receipt_provider_invalid_response")

    @override_settings(
        PROVERKACHEKA_ENABLED=False,
        PROVERKACHEKA_API_TOKEN="token",
        PROVERKACHEKA_API_URL="https://example.test/check",
        PROVERKACHEKA_TIMEOUT_SECONDS=5,
    )
    def test_disabled_provider_raises_configuration_error(self):
        client = ProverkaChekaClient()

        with self.assertRaises(ReceiptProviderError) as context:
            client.fetch_by_qr_raw(VALID_QR)

        self.assertEqual(context.exception.code, "receipt_provider_disabled")

    @override_settings(
        PROVERKACHEKA_ENABLED=True,
        PROVERKACHEKA_API_TOKEN="",
        PROVERKACHEKA_API_URL="https://example.test/check",
        PROVERKACHEKA_TIMEOUT_SECONDS=5,
    )
    def test_missing_token_raises_configuration_error(self):
        client = ProverkaChekaClient()

        with self.assertRaises(ReceiptProviderError) as context:
            client.fetch_by_qr_raw(VALID_QR)

        self.assertEqual(context.exception.code, "receipt_provider_token_missing")
        self.assertIn("token", context.exception.field_errors)

    @override_settings(
        PROVERKACHEKA_ENABLED=True,
        PROVERKACHEKA_API_TOKEN="secret-token",
        PROVERKACHEKA_API_URL="https://example.test/check",
        PROVERKACHEKA_TIMEOUT_SECONDS=5,
    )
    @patch("apps.finance.receipts.provider.urlopen")
    def test_fetch_by_qr_sends_qrraw_and_token(self, mocked_urlopen):
        mocked_urlopen.return_value = FakeHTTPResponse(self.success_payload())
        client = ProverkaChekaClient()

        details = client.fetch_by_qr_raw(VALID_QR)

        self.assertEqual(details.total_amount, Decimal("211.00"))
        request = mocked_urlopen.call_args.args[0]
        body = request.data.decode("utf-8")
        payload = parse_qs(body)
        self.assertEqual(payload["token"], ["secret-token"])
        self.assertEqual(payload["qrraw"], [parse_receipt_qr(VALID_QR).canonical])
        self.assertEqual(mocked_urlopen.call_args.kwargs["timeout"], 5)

    @override_settings(
        PROVERKACHEKA_ENABLED=True,
        PROVERKACHEKA_API_TOKEN="secret-token",
        PROVERKACHEKA_API_URL="https://example.test/check",
        PROVERKACHEKA_TIMEOUT_SECONDS=5,
    )
    @patch("apps.finance.receipts.provider.urlopen")
    def test_fetch_by_qr_rejects_invalid_json_response(self, mocked_urlopen):
        mocked_urlopen.return_value = FakeHTTPResponse(b"not-json")
        client = ProverkaChekaClient()

        with self.assertRaises(ReceiptProviderError) as context:
            client.fetch_by_qr_raw(VALID_QR)

        self.assertEqual(context.exception.code, "receipt_provider_invalid_json")

    @override_settings(
        PROVERKACHEKA_ENABLED=True,
        PROVERKACHEKA_API_TOKEN="secret-token",
        PROVERKACHEKA_API_URL="https://example.test/check",
        PROVERKACHEKA_TIMEOUT_SECONDS=5,
    )
    @patch("apps.finance.receipts.provider.urlopen")
    def test_fetch_by_qr_wraps_network_errors(self, mocked_urlopen):
        mocked_urlopen.side_effect = URLError("network unavailable")
        client = ProverkaChekaClient()

        with self.assertRaises(ReceiptProviderError) as context:
            client.fetch_by_qr_raw(VALID_QR)

        self.assertEqual(context.exception.code, "receipt_provider_unavailable")

    def test_mock_provider_returns_configured_receipt(self):
        receipt = normalize_proverkacheka_response(self.success_payload())
        client = MockReceiptProviderClient(receipt=receipt)

        result = client.fetch_by_qr_raw(VALID_QR)

        self.assertIsInstance(result, FiscalReceiptDetails)
        self.assertEqual(result.organization_name, "ООО Ромашка")
