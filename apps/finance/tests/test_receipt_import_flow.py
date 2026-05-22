from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.finance.models import (
    Account,
    Category,
    Receipt,
    ReceiptAuditAction,
    ReceiptAuditLog,
    ReceiptAuditStatus,
    ReceiptStatus,
    Transaction,
    TransactionType,
)
from apps.finance.receipt_duplicates import register_receipt_from_qr
from apps.finance.receipt_provider import ReceiptProviderError, normalize_proverkacheka_response
from apps.finance.receipt_qr import ReceiptQRParseError, parse_receipt_qr
from apps.finance.receipt_transactions import (
    RECEIPT_TRANSACTION_MODE_SINGLE,
    ReceiptTransactionCreationError,
    create_transactions_from_receipt,
)


User = get_user_model()

VALID_QR = "t=20240522T1421&s=270.00&fn=9280440300891234&i=12345&fp=987654321&n=1"
REORDERED_QR = "fp=987654321&n=1&i=12345&fn=9280440300891234&s=270.00&t=20240522T1421"


class ReceiptImportFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="receipt_flow_user",
            email="receipt_flow@example.com",
            password="StrongPass123!",
        )
        self.other_user = User.objects.create_user(
            username="receipt_flow_other",
            email="receipt_flow_other@example.com",
            password="StrongPass123!",
        )
        self.account = Account.objects.create(
            user=self.user,
            name="Карта",
            initial_balance=Decimal("10000.00"),
            balance=Decimal("10000.00"),
            currency="RUB",
        )
        self.products = Category.objects.create(
            user=self.user,
            name="Продукты",
            type=TransactionType.EXPENSE,
            icon="cart",
            color="#66BB6A",
        )
        self.cafe = Category.objects.create(
            user=self.user,
            name="Кафе",
            type=TransactionType.EXPENSE,
            icon="coffee",
            color="#FFA726",
        )
        self.income_category = Category.objects.create(
            user=self.user,
            name="Зарплата",
            type=TransactionType.INCOME,
            icon="cash",
            color="#26A69A",
        )
        self.client = APIClient()

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
                            "name": "Молоко Простоквашино 2.5%",
                            "price": 9000,
                            "quantity": 1,
                            "sum": 9000,
                        },
                        {
                            "name": "Капучино большой",
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

    def register_receipt_with_provider(self):
        details = normalize_proverkacheka_response(self.provider_payload())
        return register_receipt_from_qr(
            user=self.user,
            qr_raw=VALID_QR,
            provider_details=details,
            status=ReceiptStatus.FETCHED,
        ).receipt

    def test_qr_parser_accepts_frontend_payload_variants(self):
        cases = [
            VALID_QR,
            "https://qr.nalog.ru/?t=20240522T142100&s=270.00&fn=9280440300891234&i=12345&fp=987654321&n=1",
            "t=2024-05-22T14:21&s=270,00&fn=9280440300891234&i=12345&fp=987654321&n=1",
        ]

        for qr_raw in cases:
            with self.subTest(qr_raw=qr_raw):
                result = parse_receipt_qr(qr_raw)
                self.assertEqual(result.total_amount, Decimal("270.00"))
                self.assertEqual(result.fiscal_key, "9280440300891234:12345:987654321")
                self.assertEqual(result.date_time.hour, 14)
                self.assertEqual(result.date_time.minute, 21)

    def test_qr_parser_rejects_common_frontend_errors(self):
        cases = {
            "": "receipt_qr_empty",
            "not-a-qr": "receipt_qr_invalid_format",
            "t=20240522T1421&s=270.00&fn=9280440300891234": "receipt_qr_missing_fields",
            "t=wrong&s=270.00&fn=9280440300891234&i=12345&fp=987654321&n=1": "receipt_qr_invalid_datetime",
            "t=20240522T1421&s=-1&fn=9280440300891234&i=12345&fp=987654321&n=1": "receipt_qr_invalid_amount",
            "t=20240522T1421&s=270.00&fn=abc&i=12345&fp=987654321&n=1": "receipt_qr_invalid_fiscal_field",
            "t=20240522T1421&s=270.00&fn=9280440300891234&i=12345&fp=987654321&n=9": "receipt_qr_invalid_operation_type",
        }

        for qr_raw, expected_code in cases.items():
            with self.subTest(expected_code=expected_code):
                with self.assertRaises(ReceiptQRParseError) as context:
                    parse_receipt_qr(qr_raw)
                self.assertEqual(context.exception.code, expected_code)
                self.assertTrue(context.exception.field_errors)

    def test_provider_common_failure_codes_are_normalized(self):
        expected_codes = {
            0: "receipt_provider_invalid_receipt",
            2: "receipt_provider_pending",
            3: "receipt_provider_limit_exceeded",
            4: "receipt_provider_retry_later",
            5: "receipt_provider_no_data",
        }

        for provider_code, expected_error_code in expected_codes.items():
            with self.subTest(provider_code=provider_code):
                with self.assertRaises(ReceiptProviderError) as context:
                    normalize_proverkacheka_response({"code": provider_code, "first": 0, "data": {}})
                self.assertEqual(context.exception.code, expected_error_code)
                self.assertEqual(context.exception.provider_code, provider_code)

    def test_full_receipt_flow_from_provider_to_item_transactions_and_audit(self):
        receipt = self.register_receipt_with_provider()

        self.assertEqual(receipt.status, ReceiptStatus.FETCHED)
        self.assertEqual(receipt.store_name, "ООО Ромашка")
        self.assertEqual(receipt.items.count(), 2)
        self.assertEqual(receipt.items.order_by("line_number").first().suggested_category, self.products)
        self.assertTrue(
            ReceiptAuditLog.objects.filter(
                receipt=receipt,
                action=ReceiptAuditAction.PROVIDER_FETCH_SUCCESS,
                status=ReceiptAuditStatus.SUCCESS,
            ).exists()
        )
        self.assertTrue(
            ReceiptAuditLog.objects.filter(
                receipt=receipt,
                action=ReceiptAuditAction.ITEMS_MAPPED,
                status=ReceiptAuditStatus.SUCCESS,
            ).exists()
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            f"/api/v1/finance/receipts/{receipt.id}/create-transactions/",
            {
                "accountId": self.account.id,
                "mode": "by_items",
                "items": [
                    {"receiptItemId": receipt_item.id}
                    for receipt_item in receipt.items.order_by("line_number")
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["createdCount"], 2)
        receipt.refresh_from_db()
        self.account.refresh_from_db()
        self.assertEqual(receipt.status, ReceiptStatus.IMPORTED)
        self.assertEqual(Transaction.objects.filter(receipt=receipt).count(), 2)
        self.assertEqual(self.account.balance, Decimal("9730.00"))
        self.assertTrue(
            ReceiptAuditLog.objects.filter(
                receipt=receipt,
                action=ReceiptAuditAction.TRANSACTIONS_CREATED,
                status=ReceiptAuditStatus.SUCCESS,
            ).exists()
        )

    def test_duplicate_scan_returns_existing_receipt_and_logs_warning(self):
        first = register_receipt_from_qr(user=self.user, qr_raw=VALID_QR)
        second = register_receipt_from_qr(user=self.user, qr_raw=REORDERED_QR)

        self.assertTrue(first.created)
        self.assertFalse(second.created)
        self.assertTrue(second.is_duplicate)
        self.assertEqual(first.receipt.id, second.receipt.id)
        self.assertEqual(Receipt.objects.filter(user=self.user).count(), 1)
        self.assertTrue(
            ReceiptAuditLog.objects.filter(
                receipt=first.receipt,
                action=ReceiptAuditAction.DUPLICATE_DETECTED,
                status=ReceiptAuditStatus.WARNING,
            ).exists()
        )

    def test_import_errors_are_audited_and_do_not_create_transactions(self):
        receipt = register_receipt_from_qr(user=self.user, qr_raw=VALID_QR).receipt

        with self.assertRaises(ReceiptTransactionCreationError) as context:
            create_transactions_from_receipt(
                user=self.user,
                receipt=receipt,
                account=self.account,
                mode=RECEIPT_TRANSACTION_MODE_SINGLE,
                category=self.income_category,
            )

        self.assertEqual(context.exception.code, "category_type_mismatch")
        self.assertFalse(Transaction.objects.filter(receipt=receipt).exists())
        self.assertTrue(
            ReceiptAuditLog.objects.filter(
                receipt=receipt,
                action=ReceiptAuditAction.IMPORT_FAILED,
                status=ReceiptAuditStatus.ERROR,
                metadata__code="category_type_mismatch",
            ).exists()
        )

    def test_receipt_import_is_isolated_between_users(self):
        receipt = self.register_receipt_with_provider()
        self.client.force_authenticate(user=self.other_user)

        response = self.client.post(
            f"/api/v1/finance/receipts/{receipt.id}/create-transactions/",
            {
                "accountId": self.account.id,
                "mode": "single",
                "categoryId": self.products.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(Transaction.objects.filter(receipt=receipt).exists())
