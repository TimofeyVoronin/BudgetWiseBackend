from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.finance.models import Receipt, ReceiptStatus
from apps.finance.receipts.duplicates import (
    ReceiptDuplicateError,
    build_receipt_import_deduplication_key,
    check_receipt_duplicate,
    ensure_receipt_not_duplicate,
    register_receipt_from_qr,
)
from apps.finance.receipts.provider import normalize_proverkacheka_response
from apps.finance.receipts.qr import parse_receipt_qr


User = get_user_model()

VALID_QR = "t=20240522T1421&s=1250.50&fn=9280440300891234&i=12345&fp=987654321&n=1"
REORDERED_QR = "fp=987654321&n=1&i=12345&fn=9280440300891234&s=1250.50&t=20240522T1421"
OTHER_RECEIPT_QR = "t=20240522T1421&s=1250.50&fn=9280440300891234&i=12346&fp=987654321&n=1"


class ReceiptDuplicatePreventionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="receipt_user",
            email="receipt@example.com",
            password="StrongPass123!",
        )
        self.other_user = User.objects.create_user(
            username="receipt_other",
            email="receipt_other@example.com",
            password="StrongPass123!",
        )

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
                        }
                    ],
                    "totalSum": 125050,
                    "cashTotalSum": 0,
                    "ecashTotalSum": 125050,
                    "fiscalDriveNumber": "9280440300891234",
                    "fiscalDocumentNumber": "12345",
                    "fiscalSign": "987654321",
                },
                "html": "<p>receipt</p>",
            },
        }

    def test_build_import_deduplication_key_uses_date_amount_and_fiscal_fields(self):
        qr_data = parse_receipt_qr(VALID_QR)

        key = build_receipt_import_deduplication_key(qr_data)

        self.assertIn("20240522T142100", key)
        self.assertIn("1250.50", key)
        self.assertIn("9280440300891234", key)
        self.assertIn("12345", key)
        self.assertIn("987654321", key)

    def test_register_receipt_from_qr_creates_receipt(self):
        result = register_receipt_from_qr(user=self.user, qr_raw=VALID_QR)

        self.assertTrue(result.created)
        self.assertFalse(result.is_duplicate)
        self.assertEqual(Receipt.objects.filter(user=self.user).count(), 1)
        self.assertEqual(result.receipt.total_amount, Decimal("1250.50"))
        self.assertEqual(result.receipt.fiscal_key, "9280440300891234:12345:987654321")
        self.assertEqual(result.receipt.status, ReceiptStatus.PARSED)
        self.assertTrue(result.receipt.deduplication_key)
        self.assertTrue(result.receipt.raw_hash)

    def test_register_same_receipt_twice_returns_existing_receipt(self):
        first = register_receipt_from_qr(user=self.user, qr_raw=VALID_QR)
        second = register_receipt_from_qr(user=self.user, qr_raw=VALID_QR)

        self.assertTrue(first.created)
        self.assertFalse(second.created)
        self.assertTrue(second.is_duplicate)
        self.assertEqual(first.receipt.id, second.receipt.id)
        self.assertEqual(Receipt.objects.filter(user=self.user).count(), 1)

    def test_reordered_qr_params_are_detected_as_duplicate(self):
        first = register_receipt_from_qr(user=self.user, qr_raw=VALID_QR)
        second = register_receipt_from_qr(user=self.user, qr_raw=REORDERED_QR)

        self.assertEqual(first.receipt.id, second.receipt.id)
        self.assertTrue(second.is_duplicate)
        self.assertEqual(Receipt.objects.filter(user=self.user).count(), 1)

    def test_same_receipt_can_be_imported_by_different_users(self):
        first = register_receipt_from_qr(user=self.user, qr_raw=VALID_QR)
        second = register_receipt_from_qr(user=self.other_user, qr_raw=VALID_QR)

        self.assertNotEqual(first.receipt.id, second.receipt.id)
        self.assertTrue(first.created)
        self.assertTrue(second.created)
        self.assertEqual(Receipt.objects.count(), 2)

    def test_other_fiscal_document_is_not_duplicate(self):
        first = register_receipt_from_qr(user=self.user, qr_raw=VALID_QR)
        second = register_receipt_from_qr(user=self.user, qr_raw=OTHER_RECEIPT_QR)

        self.assertNotEqual(first.receipt.id, second.receipt.id)
        self.assertTrue(second.created)
        self.assertEqual(Receipt.objects.filter(user=self.user).count(), 2)

    def test_check_receipt_duplicate_returns_existing_receipt(self):
        created = register_receipt_from_qr(user=self.user, qr_raw=VALID_QR)
        duplicate_check = check_receipt_duplicate(self.user, parse_receipt_qr(VALID_QR))

        self.assertTrue(duplicate_check.is_duplicate)
        self.assertEqual(duplicate_check.existing_receipt.id, created.receipt.id)
        self.assertEqual(duplicate_check.fiscal_key, "9280440300891234:12345:987654321")

    def test_ensure_receipt_not_duplicate_raises_clear_error(self):
        created = register_receipt_from_qr(user=self.user, qr_raw=VALID_QR)

        with self.assertRaises(ReceiptDuplicateError) as context:
            ensure_receipt_not_duplicate(self.user, parse_receipt_qr(VALID_QR))

        self.assertEqual(context.exception.receipt.id, created.receipt.id)

    def test_register_receipt_stores_provider_details(self):
        details = normalize_proverkacheka_response(self.provider_payload())

        result = register_receipt_from_qr(
            user=self.user,
            qr_raw=VALID_QR,
            provider_details=details,
            status=ReceiptStatus.FETCHED,
        )

        self.assertTrue(result.created)
        self.assertEqual(result.receipt.status, ReceiptStatus.FETCHED)
        self.assertEqual(result.receipt.provider_name, "proverkacheka")
        self.assertEqual(result.receipt.provider_code, 1)
        self.assertEqual(result.receipt.store_name, "ООО Ромашка")
        self.assertEqual(result.receipt.seller_inn, "7700000000")
        self.assertIn("data", result.receipt.provider_payload)
