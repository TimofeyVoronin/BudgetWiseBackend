from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.finance.models import (
    Account,
    Category,
    ReceiptAuditAction,
    ReceiptAuditLog,
    ReceiptAuditStatus,
    ReceiptStatus,
    TransactionType,
)
from apps.finance.receipt_audit import log_receipt_audit_event
from apps.finance.receipt_duplicates import register_receipt_from_qr
from apps.finance.receipt_provider import normalize_proverkacheka_response
from apps.finance.receipt_transactions import (
    RECEIPT_TRANSACTION_MODE_SINGLE,
    ReceiptTransactionCreationError,
    create_transactions_from_receipt,
)


User = get_user_model()
VALID_QR = "t=20240522T1421&s=1250.50&fn=9280440300891234&i=12345&fp=987654321&n=1"


class ReceiptAuditTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="receipt_audit_user",
            email="receipt_audit@example.com",
            password="StrongPass123!",
        )
        self.account = Account.objects.create(
            user=self.user,
            name="Карта",
            initial_balance=Decimal("10000.00"),
            balance=Decimal("10000.00"),
            currency="RUB",
        )
        self.category = Category.objects.create(
            user=self.user,
            name="Продукты",
            type=TransactionType.EXPENSE,
            icon="cart",
            color="#66BB6A",
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

    def test_register_receipt_logs_qr_parsed_event(self):
        result = register_receipt_from_qr(user=self.user, qr_raw=VALID_QR)

        audit_log = ReceiptAuditLog.objects.get(receipt=result.receipt)
        self.assertEqual(audit_log.user, self.user)
        self.assertEqual(audit_log.action, ReceiptAuditAction.QR_PARSED)
        self.assertEqual(audit_log.status, ReceiptAuditStatus.SUCCESS)
        self.assertEqual(audit_log.qr_raw_hash, result.receipt.raw_hash)
        self.assertEqual(audit_log.fiscal_key, result.receipt.fiscal_key)
        self.assertEqual(audit_log.metadata["receiptStatus"], ReceiptStatus.PARSED)

    def test_register_receipt_with_provider_logs_fetch_and_mapping_events(self):
        details = normalize_proverkacheka_response(self.provider_payload())

        result = register_receipt_from_qr(
            user=self.user,
            qr_raw=VALID_QR,
            provider_details=details,
            status=ReceiptStatus.FETCHED,
        )

        actions = list(
            ReceiptAuditLog.objects.filter(receipt=result.receipt)
            .order_by("id")
            .values_list("action", flat=True)
        )
        self.assertEqual(
            actions,
            [
                ReceiptAuditAction.PROVIDER_FETCH_SUCCESS,
                ReceiptAuditAction.ITEMS_MAPPED,
            ],
        )
        mapped_event = ReceiptAuditLog.objects.get(
            receipt=result.receipt,
            action=ReceiptAuditAction.ITEMS_MAPPED,
        )
        self.assertEqual(mapped_event.metadata["itemsCount"], 1)

    def test_duplicate_import_logs_warning_event(self):
        first = register_receipt_from_qr(user=self.user, qr_raw=VALID_QR)
        second = register_receipt_from_qr(user=self.user, qr_raw=VALID_QR)

        self.assertFalse(second.created)
        audit_log = ReceiptAuditLog.objects.filter(
            receipt=first.receipt,
            action=ReceiptAuditAction.DUPLICATE_DETECTED,
        ).latest("id")
        self.assertEqual(audit_log.status, ReceiptAuditStatus.WARNING)
        self.assertEqual(audit_log.metadata["fiscalKey"], first.receipt.fiscal_key)

    def test_transaction_creation_logs_audit_event(self):
        receipt = register_receipt_from_qr(user=self.user, qr_raw=VALID_QR).receipt

        result = create_transactions_from_receipt(
            user=self.user,
            receipt=receipt,
            account=self.account,
            mode=RECEIPT_TRANSACTION_MODE_SINGLE,
            category=self.category,
        )

        audit_log = ReceiptAuditLog.objects.get(
            receipt=receipt,
            action=ReceiptAuditAction.TRANSACTIONS_CREATED,
        )
        self.assertEqual(audit_log.status, ReceiptAuditStatus.SUCCESS)
        self.assertEqual(audit_log.metadata["mode"], RECEIPT_TRANSACTION_MODE_SINGLE)
        self.assertEqual(audit_log.metadata["createdCount"], 1)
        self.assertEqual(audit_log.metadata["transactionIds"], [result.transactions[0].id])

    def test_transaction_creation_error_logs_audit_event(self):
        receipt = register_receipt_from_qr(user=self.user, qr_raw=VALID_QR).receipt

        with self.assertRaises(ReceiptTransactionCreationError):
            create_transactions_from_receipt(
                user=self.user,
                receipt=receipt,
                account=self.account,
                mode=RECEIPT_TRANSACTION_MODE_SINGLE,
                category=None,
            )

        audit_log = ReceiptAuditLog.objects.get(
            receipt=receipt,
            action=ReceiptAuditAction.IMPORT_FAILED,
        )
        self.assertEqual(audit_log.status, ReceiptAuditStatus.ERROR)
        self.assertEqual(audit_log.metadata["code"], "category_required")
        self.assertIn("categoryId", audit_log.metadata["fieldErrors"])

    def test_manual_audit_event_keeps_receipt_identity(self):
        receipt = register_receipt_from_qr(user=self.user, qr_raw=VALID_QR).receipt

        audit_log = log_receipt_audit_event(
            receipt=receipt,
            action=ReceiptAuditAction.PROVIDER_FETCH_FAILED,
            status=ReceiptAuditStatus.ERROR,
            message="Провайдер недоступен.",
            metadata={"providerCode": 5},
        )

        self.assertEqual(audit_log.user, self.user)
        self.assertEqual(audit_log.qr_raw_hash, receipt.raw_hash)
        self.assertEqual(audit_log.fiscal_key, receipt.fiscal_key)
        self.assertEqual(audit_log.metadata["providerCode"], 5)
