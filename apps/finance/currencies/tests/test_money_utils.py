from decimal import Decimal

from rest_framework.exceptions import ValidationError

from apps.finance.currencies.money import (
    MoneyAmount,
    MoneyAmountSerializer,
    build_money_payload,
    build_money_payload_map,
    build_zero_money_payload,
    normalize_decimal,
    parse_money_payload,
    quantize_money,
)
from apps.finance.testing import FinanceAPITestCase


class MoneyUtilsTests(FinanceAPITestCase):
    def test_money_amount_returns_frontend_payload_shape(self):
        money = MoneyAmount(amount=Decimal("125.50"), currency="eur")

        self.assertEqual(money.amount, Decimal("125.50"))
        self.assertEqual(money.currency, "EUR")
        self.assertEqual(money.as_payload(), {"amount": 125.5, "currency": "EUR"})

    def test_build_money_payload_quantizes_amount(self):
        payload = build_money_payload(
            Decimal("125.555"),
            currency="usd",
        )

        self.assertEqual(payload, {"amount": 125.56, "currency": "USD"})

    def test_build_money_payload_can_skip_quantize(self):
        payload = build_money_payload(
            Decimal("0.12345678"),
            currency="BTC",
            quantize=False,
        )

        self.assertEqual(payload, {"amount": 0.12345678, "currency": "BTC"})

    def test_build_zero_money_payload(self):
        self.assertEqual(
            build_zero_money_payload(currency="eur"),
            {"amount": 0.0, "currency": "EUR"},
        )

    def test_build_money_payload_map(self):
        payload = build_money_payload_map(
            {
                "income": Decimal("100.00"),
                "expenses": Decimal("55.555"),
            },
            currency="rub",
        )

        self.assertEqual(
            payload,
            {
                "income": {"amount": 100.0, "currency": "RUB"},
                "expenses": {"amount": 55.56, "currency": "RUB"},
            },
        )

    def test_parse_money_payload(self):
        money = parse_money_payload({"amount": "125,50", "currency": "eur"})

        self.assertEqual(money.amount, Decimal("125.50"))
        self.assertEqual(money.currency, "EUR")

    def test_parse_money_payload_uses_default_currency(self):
        money = parse_money_payload({"amount": "10.00"}, default_currency="usd")

        self.assertEqual(money.as_payload(), {"amount": 10.0, "currency": "USD"})

    def test_normalize_decimal_rejects_invalid_amount(self):
        with self.assertRaises(ValidationError):
            normalize_decimal("wrong")

    def test_quantize_money(self):
        self.assertEqual(quantize_money(Decimal("10.005")), Decimal("10.01"))

    def test_money_amount_serializer_matches_contract(self):
        serializer = MoneyAmountSerializer(
            data={"amount": 125.5, "currency": "EUR"},
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
