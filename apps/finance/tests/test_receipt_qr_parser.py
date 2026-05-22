from decimal import Decimal

from django.test import SimpleTestCase

from apps.finance.receipt_qr import (
    RECEIPT_OPERATION_EXPENSE,
    RECEIPT_OPERATION_INCOME,
    ReceiptQRParseError,
    build_receipt_deduplication_key,
    parse_receipt_qr,
)


class ReceiptQRParserTests(SimpleTestCase):
    valid_qr = "t=20240522T1421&s=1250.50&fn=9280440300891234&i=12345&fp=987654321&n=1"

    def test_parse_valid_fiscal_receipt_qr(self):
        result = parse_receipt_qr(self.valid_qr)

        self.assertEqual(result.total_amount, Decimal("1250.50"))
        self.assertEqual(result.fiscal_drive_number, "9280440300891234")
        self.assertEqual(result.fiscal_document_number, "12345")
        self.assertEqual(result.fiscal_sign, "987654321")
        self.assertEqual(result.operation_type_code, "1")
        self.assertEqual(result.operation_type, RECEIPT_OPERATION_INCOME)
        self.assertEqual(result.date_time.year, 2024)
        self.assertEqual(result.date_time.month, 5)
        self.assertEqual(result.date_time.day, 22)
        self.assertEqual(result.date_time.hour, 14)
        self.assertEqual(result.date_time.minute, 21)
        self.assertTrue(result.raw_hash)
        self.assertEqual(
            build_receipt_deduplication_key(result),
            "receipt:9280440300891234:12345:987654321",
        )

    def test_parse_qr_from_full_url_and_comma_amount(self):
        result = parse_receipt_qr(
            "https://qr.nalog.ru/?t=2024-05-22T14%3A21&s=1250,50&fn=9280440300891234&i=12345&fp=987654321&n=3"
        )

        self.assertEqual(result.total_amount, Decimal("1250.50"))
        self.assertEqual(result.operation_type, RECEIPT_OPERATION_EXPENSE)
        self.assertEqual(result.date_time.hour, 14)
        self.assertEqual(result.date_time.minute, 21)

    def test_hash_is_stable_for_same_fiscal_query_with_different_order(self):
        first = parse_receipt_qr(
            "t=20240522T1421&s=1250.50&fn=9280440300891234&i=12345&fp=987654321&n=1"
        )
        second = parse_receipt_qr(
            "fp=987654321&i=12345&n=1&fn=9280440300891234&s=1250.50&t=20240522T1421"
        )

        self.assertEqual(first.raw_hash, second.raw_hash)
        self.assertEqual(first.canonical, second.canonical)

    def test_as_dict_returns_frontend_friendly_keys(self):
        result = parse_receipt_qr(self.valid_qr).as_dict()

        self.assertEqual(result["totalAmount"], "1250.50")
        self.assertEqual(result["fiscalDriveNumber"], "9280440300891234")
        self.assertEqual(result["fiscalDocumentNumber"], "12345")
        self.assertEqual(result["fiscalSign"], "987654321")
        self.assertEqual(result["operationType"], RECEIPT_OPERATION_INCOME)
        self.assertEqual(result["fiscalKey"], "9280440300891234:12345:987654321")

    def test_empty_qr_raises_clear_error(self):
        with self.assertRaises(ReceiptQRParseError) as context:
            parse_receipt_qr(" ")

        self.assertEqual(context.exception.code, "receipt_qr_empty")
        self.assertIn("qrRaw", context.exception.field_errors)

    def test_invalid_format_raises_clear_error(self):
        with self.assertRaises(ReceiptQRParseError) as context:
            parse_receipt_qr("not-a-fiscal-query")

        self.assertEqual(context.exception.code, "receipt_qr_invalid_format")
        self.assertIn("qrRaw", context.exception.field_errors)

    def test_missing_required_fields_raises_clear_error(self):
        with self.assertRaises(ReceiptQRParseError) as context:
            parse_receipt_qr("t=20240522T1421&s=1250.50&fn=9280440300891234")

        self.assertEqual(context.exception.code, "receipt_qr_missing_fields")
        self.assertEqual(
            set(context.exception.field_errors),
            {"fp", "i", "n"},
        )

    def test_invalid_amount_raises_clear_error(self):
        with self.assertRaises(ReceiptQRParseError) as context:
            parse_receipt_qr(
                "t=20240522T1421&s=wrong&fn=9280440300891234&i=12345&fp=987654321&n=1"
            )

        self.assertEqual(context.exception.code, "receipt_qr_invalid_amount")
        self.assertIn("s", context.exception.field_errors)

    def test_invalid_datetime_raises_clear_error(self):
        with self.assertRaises(ReceiptQRParseError) as context:
            parse_receipt_qr(
                "t=wrong&s=1250.50&fn=9280440300891234&i=12345&fp=987654321&n=1"
            )

        self.assertEqual(context.exception.code, "receipt_qr_invalid_datetime")
        self.assertIn("t", context.exception.field_errors)

    def test_invalid_fiscal_field_raises_clear_error(self):
        with self.assertRaises(ReceiptQRParseError) as context:
            parse_receipt_qr(
                "t=20240522T1421&s=1250.50&fn=not-digits&i=12345&fp=987654321&n=1"
            )

        self.assertEqual(context.exception.code, "receipt_qr_invalid_fiscal_field")
        self.assertIn("fn", context.exception.field_errors)

    def test_invalid_operation_type_raises_clear_error(self):
        with self.assertRaises(ReceiptQRParseError) as context:
            parse_receipt_qr(
                "t=20240522T1421&s=1250.50&fn=9280440300891234&i=12345&fp=987654321&n=9"
            )

        self.assertEqual(context.exception.code, "receipt_qr_invalid_operation_type")
        self.assertIn("n", context.exception.field_errors)
