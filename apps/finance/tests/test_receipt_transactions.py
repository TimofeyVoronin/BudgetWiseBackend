from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.finance.models import (
    Account,
    Category,
    ReceiptItem,
    ReceiptStatus,
    Transaction,
    TransactionType,
)
from apps.finance.receipt_duplicates import register_receipt_from_qr
from apps.finance.receipt_transactions import (
    RECEIPT_TRANSACTION_MODE_BY_ITEMS,
    RECEIPT_TRANSACTION_MODE_SINGLE,
    ReceiptItemTransactionInput,
    ReceiptTransactionCreationError,
    create_transactions_from_receipt,
)


User = get_user_model()
VALID_QR = "t=20240522T1421&s=1250.50&fn=9280440300891234&i=12345&fp=987654321&n=1"


class ReceiptTransactionCreationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="receipt_tx_user",
            email="receipt_tx@example.com",
            password="StrongPass123!",
        )
        self.other_user = User.objects.create_user(
            username="receipt_tx_other",
            email="receipt_tx_other@example.com",
            password="StrongPass123!",
        )
        self.account = Account.objects.create(
            user=self.user,
            name="Карта",
            initial_balance=Decimal("10000.00"),
            balance=Decimal("10000.00"),
            currency="RUB",
        )
        self.other_account = Account.objects.create(
            user=self.other_user,
            name="Чужая карта",
            initial_balance=Decimal("1000.00"),
            balance=Decimal("1000.00"),
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
        self.other_category = Category.objects.create(
            user=self.other_user,
            name="Чужая категория",
            type=TransactionType.EXPENSE,
        )
        self.receipt = register_receipt_from_qr(user=self.user, qr_raw=VALID_QR).receipt
        self.receipt.store_name = "Пятёрочка"
        self.receipt.save(update_fields=["store_name", "updated_at"])
        self.milk = ReceiptItem.objects.create(
            receipt=self.receipt,
            line_number=1,
            name="Молоко",
            quantity=Decimal("1.000"),
            price=Decimal("90.00"),
            amount=Decimal("90.00"),
            suggested_category=self.products,
            mapping_confidence=Decimal("0.85"),
        )
        self.coffee = ReceiptItem.objects.create(
            receipt=self.receipt,
            line_number=2,
            name="Капучино",
            quantity=Decimal("1.000"),
            price=Decimal("180.00"),
            amount=Decimal("180.00"),
            suggested_category=self.cafe,
            mapping_confidence=Decimal("0.85"),
        )

    def test_create_single_transaction_from_receipt(self):
        result = create_transactions_from_receipt(
            user=self.user,
            receipt=self.receipt,
            account=self.account,
            mode=RECEIPT_TRANSACTION_MODE_SINGLE,
            category=self.products,
        )

        self.assertEqual(result.created_count, 1)
        transaction = result.transactions[0]
        self.assertEqual(transaction.receipt, self.receipt)
        self.assertIsNone(transaction.receipt_item)
        self.assertEqual(transaction.type, TransactionType.EXPENSE)
        self.assertEqual(transaction.amount, Decimal("1250.50"))
        self.assertEqual(transaction.category, self.products)
        self.assertEqual(transaction.operation_date, timezone.localdate(self.receipt.receipt_datetime))

        self.receipt.refresh_from_db()
        self.account.refresh_from_db()
        self.assertEqual(self.receipt.status, ReceiptStatus.IMPORTED)
        self.assertEqual(self.account.balance, Decimal("8749.50"))

    def test_create_transactions_by_receipt_items(self):
        result = create_transactions_from_receipt(
            user=self.user,
            receipt=self.receipt,
            account=self.account,
            mode=RECEIPT_TRANSACTION_MODE_BY_ITEMS,
            items=[
                ReceiptItemTransactionInput(receipt_item_id=self.milk.id, category_id=self.products.id),
                ReceiptItemTransactionInput(receipt_item_id=self.coffee.id, category_id=self.cafe.id),
            ],
        )

        self.assertEqual(result.created_count, 2)
        self.assertEqual(Transaction.objects.filter(receipt=self.receipt).count(), 2)
        self.assertEqual(
            list(Transaction.objects.filter(receipt=self.receipt).order_by("id").values_list("amount", flat=True)),
            [Decimal("90.00"), Decimal("180.00")],
        )
        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal("9730.00"))

    def test_create_by_items_uses_suggested_category_when_category_not_passed(self):
        result = create_transactions_from_receipt(
            user=self.user,
            receipt=self.receipt,
            account=self.account,
            mode=RECEIPT_TRANSACTION_MODE_BY_ITEMS,
            items=[ReceiptItemTransactionInput(receipt_item_id=self.milk.id)],
        )

        self.assertEqual(result.created_count, 1)
        self.assertEqual(result.transactions[0].category, self.products)

    def test_receipt_cannot_be_imported_twice(self):
        create_transactions_from_receipt(
            user=self.user,
            receipt=self.receipt,
            account=self.account,
            mode=RECEIPT_TRANSACTION_MODE_SINGLE,
            category=self.products,
        )

        with self.assertRaises(ReceiptTransactionCreationError) as context:
            create_transactions_from_receipt(
                user=self.user,
                receipt=self.receipt,
                account=self.account,
                mode=RECEIPT_TRANSACTION_MODE_SINGLE,
                category=self.products,
            )

        self.assertEqual(context.exception.code, "receipt_already_imported")

    def test_category_type_must_match_receipt_transaction_type(self):
        with self.assertRaises(ReceiptTransactionCreationError) as context:
            create_transactions_from_receipt(
                user=self.user,
                receipt=self.receipt,
                account=self.account,
                mode=RECEIPT_TRANSACTION_MODE_SINGLE,
                category=self.income_category,
            )

        self.assertEqual(context.exception.code, "category_type_mismatch")

    def test_rejects_account_from_another_user(self):
        with self.assertRaises(ReceiptTransactionCreationError) as context:
            create_transactions_from_receipt(
                user=self.user,
                receipt=self.receipt,
                account=self.other_account,
                mode=RECEIPT_TRANSACTION_MODE_SINGLE,
                category=self.products,
            )

        self.assertEqual(context.exception.code, "account_not_found")


class ReceiptTransactionAPITests(ReceiptTransactionCreationTests):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.url = f"/api/v1/finance/receipts/{self.receipt.id}/create-transactions/"

    def authenticate(self):
        self.client.force_authenticate(user=self.user)

    def test_create_single_transaction_endpoint(self):
        self.authenticate()

        response = self.client.post(
            self.url,
            {
                "accountId": self.account.id,
                "mode": "single",
                "categoryId": self.products.id,
                "description": "Чек из Пятёрочки",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["createdCount"], 1)
        self.assertEqual(response.data["mode"], "single")
        self.assertEqual(response.data["receipt"]["status"], ReceiptStatus.IMPORTED)
        self.assertEqual(len(response.data["transactions"]), 1)
        self.assertEqual(response.data["transactions"][0]["receiptId"], self.receipt.id)

    def test_create_by_items_endpoint(self):
        self.authenticate()

        response = self.client.post(
            self.url,
            {
                "accountId": self.account.id,
                "mode": "by_items",
                "items": [
                    {"receiptItemId": self.milk.id, "categoryId": self.products.id},
                    {"receiptItemId": self.coffee.id, "categoryId": self.cafe.id},
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["createdCount"], 2)
        self.assertEqual(Transaction.objects.filter(receipt=self.receipt).count(), 2)

    def test_endpoint_requires_authentication(self):
        response = self.client.post(
            self.url,
            {
                "accountId": self.account.id,
                "mode": "single",
                "categoryId": self.products.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_endpoint_rejects_unknown_receipt(self):
        self.authenticate()
        response = self.client.post(
            "/api/v1/finance/receipts/999999/create-transactions/",
            {
                "accountId": self.account.id,
                "mode": "single",
                "categoryId": self.products.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_endpoint_rejects_duplicate_import(self):
        self.authenticate()
        payload = {
            "accountId": self.account.id,
            "mode": "single",
            "categoryId": self.products.id,
        }
        first = self.client.post(self.url, payload, format="json")
        second = self.client.post(self.url, payload, format="json")

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Transaction.objects.filter(receipt=self.receipt).count(), 1)
