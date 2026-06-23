from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse
from rest_framework import status

from apps.finance.formulas.constants import FORMULA_ID_DEFAULT, MAX_FORMULA_CODE_LENGTH
from apps.finance.formulas.parser import validate_formula_code
from apps.finance.models import FormulaIdeDraft, TransactionType
from apps.finance.testing import FinanceAPITestCase


FIXED_TODAY = date(2026, 6, 22)


VALID_FORMULA = "LET income = SUM(TRANSACTIONS(type: INCOME, date: $period)); RETURN income;"
NET_FLOW_FORMULA = (
    "LET income = SUM(TRANSACTIONS(type: INCOME, date: $period)); "
    "LET expenses = SUM(TRANSACTIONS(type: EXPENSE, date: $period)); "
    "RETURN income - expenses;"
)


class FormulaDslParserTests(FinanceAPITestCase):
    def assert_diagnostic_id(self, code: str, diagnostic_id: str) -> None:
        result = validate_formula_code(code)
        self.assertFalse(result.is_valid)
        self.assertIn(diagnostic_id, {error["id"] for error in result.errors})

    def test_valid_formula_has_no_diagnostics(self):
        result = validate_formula_code(NET_FLOW_FORMULA)

        self.assertTrue(result.is_valid)
        self.assertEqual(result.errors, [])

    def test_missing_return_is_reported(self):
        self.assert_diagnostic_id("LET income = 100;", "missing-return")

    def test_unknown_variable_is_reported(self):
        self.assert_diagnostic_id("RETURN unknown_value;", "unknown-variable")

    def test_unknown_function_is_reported(self):
        self.assert_diagnostic_id("RETURN MAGIC(100);", "unknown-function")

    def test_unclosed_bracket_is_reported(self):
        self.assert_diagnostic_id("RETURN SUM(TRANSACTIONS(type: INCOME, date: $period);", "unclosed-bracket")

    def test_empty_and_too_long_code_are_reported(self):
        self.assert_diagnostic_id("   ", "empty-code")
        self.assert_diagnostic_id("RETURN 1;" + " " * MAX_FORMULA_CODE_LENGTH, "formula-too-long")

    def test_security_restrictions_are_reported(self):
        cases = [
            ("RETURN eval(\"1 + 1\");", "unsafe-construct"),
            ("RETURN __import__(\"os\");", "dunder-access-denied"),
            ("RETURN user.password;", "attribute-access-denied"),
            ("RETURN [1, 2, 3];", "unsupported-construction"),
        ]

        for code, diagnostic_id in cases:
            with self.subTest(code=code):
                self.assert_diagnostic_id(code, diagnostic_id)


@override_settings(CURRENCY_RATES_ENABLED=False)
class FormulaIdeAPITests(FinanceAPITestCase):
    def setUp(self):
        super().setUp()
        self.state_url = reverse("finance:formula-ide-state")
        self.meta_url = reverse("finance:formula-ide-meta")
        self.validate_url = reverse("finance:formula-ide-validate")
        self.preview_url = reverse("finance:formula-ide-preview")

    def create_preview_dataset(self):
        month_data = [
            (date(2026, 1, 5), "10000.00", "1200.00"),
            (date(2026, 2, 5), "11000.00", "1300.00"),
            (date(2026, 3, 5), "12000.00", "1400.00"),
            (date(2026, 4, 5), "13000.00", "1500.00"),
            (date(2026, 5, 5), "14000.00", "1600.00"),
            (date(2026, 6, 5), "15000.00", "2000.00"),
        ]
        for operation_date, income_amount, expense_amount in month_data:
            self.create_transaction(
                account=self.account,
                category=self.income_category,
                type=TransactionType.INCOME,
                amount=income_amount,
                operation_date=operation_date,
                description=f"Доход {operation_date:%Y-%m}",
            )
            self.create_transaction(
                account=self.account,
                category=self.expense_category,
                type=TransactionType.EXPENSE,
                amount=expense_amount,
                operation_date=operation_date,
                description=f"Расход {operation_date:%Y-%m}",
            )

    def patch_formula_today(self):
        return patch("apps.finance.formulas.evaluator.get_user_app_today", return_value=FIXED_TODAY)

    def assert_field_error(self, response, expected_field: str):
        field_errors = response.data.get("error", {}).get("field_errors", response.data)
        self.assertIn(expected_field, field_errors)

    def assert_dsl_error_response(self, response, expected_id: str):
        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        self.assertEqual(response.data["detail"], "В формуле найдены ошибки")
        self.assertIn("errors", response.data)
        self.assertIn("error", response.data)
        self.assertEqual(response.data["error"]["code"], "FORMULA_VALIDATION_FAILED")
        self.assertIn(expected_id, {error["id"] for error in response.data["errors"]})
        self.assertEqual(response.data["errors"], response.data["error"]["errors"])

    def test_formula_ide_endpoints_require_authentication(self):
        requests = [
            (self.client.get, self.state_url, None),
            (self.client.put, self.state_url, {"code": VALID_FORMULA, "constructor_blocks": []}),
            (self.client.get, self.meta_url, None),
            (self.client.post, self.validate_url, {"code": VALID_FORMULA}),
            (self.client.post, self.preview_url, {"code": VALID_FORMULA}),
        ]

        for method, url, payload in requests:
            with self.subTest(url=url):
                if payload is None:
                    response = method(url)
                else:
                    response = method(url, data=payload, format="json")
                self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
                self.assertFalse(response.data["success"])

    def test_state_get_returns_default_draft_for_new_user(self):
        self.authenticate()

        response = self.client.get(self.state_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["formula_id"], FORMULA_ID_DEFAULT)
        self.assertIn("RETURN", response.data["code"])
        self.assertIsInstance(response.data["constructor_blocks"], list)
        self.assertIsNone(response.data["updated_at"])
        self.assertFalse(response.data["is_saved"])

    def test_state_put_saves_draft_and_get_returns_saved_state(self):
        self.authenticate()
        blocks = [{"id": "b1", "kind": "function", "label": "SUM"}]

        save_response = self.client.put(
            self.state_url,
            data={"code": VALID_FORMULA, "constructor_blocks": blocks},
            format="json",
        )

        self.assertEqual(save_response.status_code, status.HTTP_200_OK)
        self.assertEqual(save_response.data["formula_id"], FORMULA_ID_DEFAULT)
        self.assertTrue(save_response.data["is_saved"])
        self.assertTrue(FormulaIdeDraft.objects.filter(user=self.user, formula_id=FORMULA_ID_DEFAULT).exists())

        get_response = self.client.get(self.state_url)

        self.assertEqual(get_response.status_code, status.HTTP_200_OK)
        self.assertEqual(get_response.data["code"], VALID_FORMULA)
        self.assertEqual(get_response.data["constructor_blocks"], blocks)
        self.assertTrue(get_response.data["is_saved"])
        self.assertIsNotNone(get_response.data["updated_at"])

    def test_state_drafts_are_isolated_by_user(self):
        self.authenticate()
        self.client.put(
            self.state_url,
            data={"code": VALID_FORMULA, "constructor_blocks": []},
            format="json",
        )

        self.client.force_authenticate(user=self.other_user)
        response = self.client.get(self.state_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["is_saved"])
        self.assertNotEqual(response.data["code"], VALID_FORMULA)

    def test_meta_returns_palette_and_autocomplete_data(self):
        self.authenticate()

        response = self.client.get(self.meta_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("variable_groups", response.data)
        self.assertIn("constructor_variables", response.data)
        self.assertIn("constructor_operators", response.data)
        self.assertIn("autocomplete_items", response.data)
        self.assertTrue(any(item["name"] == "SUM()" for item in response.data["autocomplete_items"]))

    def test_validate_returns_valid_result_for_correct_formula(self):
        self.authenticate()

        response = self.client.post(self.validate_url, data={"code": NET_FLOW_FORMULA}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["is_valid"])
        self.assertEqual(response.data["errors"], [])

    def test_validate_returns_diagnostics_for_dsl_errors(self):
        self.authenticate()

        response = self.client.post(self.validate_url, data={"code": "LET income = 100;"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["is_valid"])
        self.assertIn("missing-return", {error["id"] for error in response.data["errors"]})
        self.assertEqual(response.data["errors"][0]["severity"], "error")

    def test_validate_bad_body_returns_400(self):
        self.authenticate()

        response = self.client.post(self.validate_url, data={}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assert_field_error(response, "code")

    def test_preview_returns_rows_and_chart_points(self):
        self.authenticate()
        self.create_preview_dataset()

        with self.patch_formula_today():
            response = self.client.post(
                self.preview_url,
                data={"code": NET_FLOW_FORMULA, "constructor_blocks": []},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([row["id"] for row in response.data["rows"]], ["income", "expense", "net"])
        self.assertEqual(response.data["rows"][2]["value"], "13 000 ₽")
        self.assertTrue(response.data["rows"][2]["highlight"])
        self.assertEqual(len(response.data["chart_points"]), 6)
        self.assertEqual(response.data["chart_points"][-1]["month"], "Июн")
        self.assertEqual(response.data["chart_points"][-1]["value"], 13000.0)

    def test_preview_does_not_include_other_user_transactions(self):
        self.authenticate()
        self.create_preview_dataset()
        self.create_transaction(
            user=self.other_user,
            account=self.other_account,
            category=self.other_category,
            type=TransactionType.INCOME,
            amount="999999.00",
            operation_date=date(2026, 6, 7),
            description="Чужой доход",
        )

        with self.patch_formula_today():
            response = self.client.post(
                self.preview_url,
                data={"code": NET_FLOW_FORMULA, "constructor_blocks": []},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["rows"][2]["value"], "13 000 ₽")
        self.assertEqual(response.data["chart_points"][-1]["value"], 13000.0)

    def test_preview_returns_422_for_dsl_errors(self):
        self.authenticate()

        response = self.client.post(self.preview_url, data={"code": "LET income = 100;"}, format="json")

        self.assert_dsl_error_response(response, "missing-return")

    def test_preview_returns_422_for_division_by_zero(self):
        self.authenticate()

        response = self.client.post(self.preview_url, data={"code": "RETURN 100 / 0;"}, format="json")

        self.assert_dsl_error_response(response, "division-by-zero")

    def test_preview_lazy_if_does_not_evaluate_unused_branch(self):
        self.authenticate()

        response = self.client.post(
            self.preview_url,
            data={"code": "RETURN IF(1 == 2, 100 / 0, 500);", "constructor_blocks": []},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["rows"][2]["value"], "500 ₽")

    def test_preview_bad_body_returns_400(self):
        self.authenticate()

        response = self.client.post(self.preview_url, data={}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assert_field_error(response, "code")

    def test_security_restrictions_are_exposed_through_validation_api(self):
        self.authenticate()
        cases = [
            ("RETURN eval(\"1 + 1\");", "unsafe-construct"),
            ("RETURN __import__(\"os\");", "dunder-access-denied"),
            ("RETURN user.password;", "attribute-access-denied"),
            ("RETURN [1, 2, 3];", "unsupported-construction"),
        ]

        for code, expected_id in cases:
            with self.subTest(expected_id=expected_id):
                response = self.client.post(self.validate_url, data={"code": code}, format="json")
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertFalse(response.data["is_valid"])
                self.assertIn(expected_id, {error["id"] for error in response.data["errors"]})

    def test_unknown_argument_is_reported_by_preview(self):
        self.authenticate()

        response = self.client.post(
            self.preview_url,
            data={"code": "RETURN SUM(TRANSACTIONS(type: INCOME, unknown: 123));"},
            format="json",
        )

        self.assert_dsl_error_response(response, "unknown-argument")
