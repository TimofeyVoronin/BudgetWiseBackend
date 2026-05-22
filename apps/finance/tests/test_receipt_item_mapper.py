from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.finance.models import Category, ReceiptItem, TransactionType
from apps.finance.receipt_duplicates import register_receipt_from_qr
from apps.finance.receipt_item_mapper import (
    map_receipt_details_to_items,
    map_receipt_items,
    normalize_mapping_text,
    refresh_receipt_item_mappings,
    suggest_category_for_receipt_item,
)
from apps.finance.receipt_provider import ReceiptLineItem, normalize_proverkacheka_response


User = get_user_model()

VALID_QR = "t=20240522T1421&s=1250.50&fn=9280440300891234&i=12345&fp=987654321&n=1"


class ReceiptItemMapperTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="receipt_mapper",
            email="receipt_mapper@example.com",
            password="StrongPass123!",
        )
        self.other_user = User.objects.create_user(
            username="receipt_mapper_other",
            email="receipt_mapper_other@example.com",
            password="StrongPass123!",
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
        self.transport = Category.objects.create(
            user=self.user,
            name="Транспорт",
            type=TransactionType.EXPENSE,
            icon="bus",
            color="#42A5F5",
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
            name="Продукты",
            type=TransactionType.EXPENSE,
            icon="cart",
            color="#66BB6A",
        )
        self.receipt = register_receipt_from_qr(user=self.user, qr_raw=VALID_QR).receipt

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
                        {
                            "name": "Неизвестная позиция",
                            "price": 10000,
                            "quantity": 1,
                            "sum": 10000,
                        },
                    ],
                    "totalSum": 38000,
                    "cashTotalSum": 0,
                    "ecashTotalSum": 38000,
                    "fiscalDriveNumber": "9280440300891234",
                    "fiscalDocumentNumber": "12345",
                    "fiscalSign": "987654321",
                },
                "html": "<p>receipt</p>",
            },
        }

    def test_normalize_mapping_text_removes_case_punctuation_and_yo(self):
        self.assertEqual(
            normalize_mapping_text("  Молоко, ЁГУРТ 2.5%!  "),
            "молоко егурт 2 5",
        )

    def test_suggest_category_by_keyword(self):
        suggestion = suggest_category_for_receipt_item(
            user=self.user,
            item_name="Молоко Простоквашино 2.5%",
            receipt=self.receipt,
        )

        self.assertEqual(suggestion.category, self.products)
        self.assertEqual(suggestion.confidence, Decimal("0.85"))
        self.assertIn("keyword_match", suggestion.reason)

    def test_suggest_category_by_category_name_match_has_higher_confidence(self):
        suggestion = suggest_category_for_receipt_item(
            user=self.user,
            item_name="Оплата кафе на вокзале",
            receipt=self.receipt,
        )

        self.assertEqual(suggestion.category, self.cafe)
        self.assertEqual(suggestion.confidence, Decimal("0.90"))
        self.assertIn("category_name_match", suggestion.reason)

    def test_suggest_category_ignores_other_users_and_income_categories(self):
        self.products.delete()
        suggestion = suggest_category_for_receipt_item(
            user=self.user,
            item_name="Молоко",
            receipt=self.receipt,
        )

        self.assertIsNone(suggestion.category)
        self.assertEqual(suggestion.reason, "no_match")
        self.assertNotEqual(suggestion.category, self.other_category)
        self.assertNotEqual(suggestion.category, self.income_category)

    def test_map_receipt_details_to_items_creates_receipt_items_with_suggestions(self):
        details = normalize_proverkacheka_response(self.provider_payload())

        results = map_receipt_details_to_items(self.receipt, details)

        self.assertEqual(len(results), 3)
        self.assertEqual(self.receipt.items.count(), 3)
        first_item = self.receipt.items.order_by("line_number").first()
        self.assertEqual(first_item.name, "Молоко Простоквашино 2.5%")
        self.assertEqual(first_item.quantity, Decimal("1.000"))
        self.assertEqual(first_item.price, Decimal("90.00"))
        self.assertEqual(first_item.amount, Decimal("90.00"))
        self.assertEqual(first_item.suggested_category, self.products)
        self.assertEqual(first_item.mapping_confidence, Decimal("0.85"))
        self.assertIn("name", first_item.provider_payload)

    def test_map_receipt_items_replaces_existing_items_by_default(self):
        first_batch = [
            ReceiptLineItem(
                name="Молоко",
                quantity=Decimal("1"),
                price=Decimal("90.00"),
                amount=Decimal("90.00"),
                raw={"name": "Молоко"},
            )
        ]
        second_batch = [
            ReceiptLineItem(
                name="Капучино",
                quantity=Decimal("1"),
                price=Decimal("180.00"),
                amount=Decimal("180.00"),
                raw={"name": "Капучино"},
            )
        ]

        map_receipt_items(receipt=self.receipt, items=first_batch)
        map_receipt_items(receipt=self.receipt, items=second_batch)

        self.assertEqual(self.receipt.items.count(), 1)
        item = self.receipt.items.get()
        self.assertEqual(item.name, "Капучино")
        self.assertEqual(item.suggested_category, self.cafe)

    def test_register_receipt_with_provider_details_maps_items_automatically(self):
        qr = "t=20240522T1422&s=380.00&fn=9280440300891234&i=12346&fp=987654322&n=1"
        details = normalize_proverkacheka_response(self.provider_payload())

        result = register_receipt_from_qr(
            user=self.user,
            qr_raw=qr,
            provider_details=details,
        )

        self.assertTrue(result.created)
        self.assertEqual(result.receipt.items.count(), 3)
        self.assertEqual(
            result.receipt.items.order_by("line_number").first().suggested_category,
            self.products,
        )

    def test_refresh_receipt_item_mappings_updates_existing_items(self):
        receipt_item = ReceiptItem.objects.create(
            receipt=self.receipt,
            line_number=1,
            name="Капучино большой",
            quantity=Decimal("1.000"),
            price=Decimal("180.00"),
            amount=Decimal("180.00"),
        )

        results = refresh_receipt_item_mappings(self.receipt)
        receipt_item.refresh_from_db()

        self.assertEqual(len(results), 1)
        self.assertEqual(receipt_item.suggested_category, self.cafe)
        self.assertEqual(receipt_item.mapping_confidence, Decimal("0.85"))

    def test_receipt_item_rejects_category_from_another_user(self):
        item = ReceiptItem(
            receipt=self.receipt,
            line_number=1,
            name="Молоко",
            quantity=Decimal("1.000"),
            price=Decimal("90.00"),
            amount=Decimal("90.00"),
            suggested_category=self.other_category,
        )

        with self.assertRaises(ValidationError):
            item.full_clean()
