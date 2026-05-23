from django.urls import reverse
from rest_framework import status

from apps.finance.testing import FinanceAPITestCase


class FinancialCalculatorAPITests(FinanceAPITestCase):
    def calculate_url(self, calculator_id: str) -> str:
        return reverse("finance:calculator-calculate", kwargs={"calc_id": calculator_id})

    def defaults_url(self, calculator_id: str) -> str:
        return reverse("finance:calculator-defaults", kwargs={"calc_id": calculator_id})

    def test_calculators_hub_requires_authentication(self):
        response = self.client.get(reverse("finance:calculators-hub"))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(response.data["success"])

    def test_calculators_hub_returns_catalog_and_search(self):
        self.authenticate()

        response = self.client.get(reverse("finance:calculators-hub"))
        search_response = self.client.get(reverse("finance:calculators-hub"), {"q": "ипотека"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["totalCount"], 6)
        self.assertEqual(
            {item["id"] for item in response.data["items"]},
            {"credit", "mortgage", "installment", "deposit", "pension", "inflation"},
        )
        self.assertEqual(search_response.status_code, status.HTTP_200_OK)
        self.assertEqual(search_response.data["totalCount"], 1)
        self.assertEqual(search_response.data["items"][0]["id"], "mortgage")

    def test_defaults_for_supported_calculators(self):
        self.authenticate()

        for calculator_id in ["credit", "mortgage", "installment", "deposit", "pension", "inflation"]:
            response = self.client.get(self.defaults_url(calculator_id))
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["calculatorId"], calculator_id)
            self.assertTrue(response.data["defaults"])

    def test_unknown_calculator_returns_not_found(self):
        self.authenticate()

        defaults_response = self.client.get(self.defaults_url("unknown"))
        calculate_response = self.client.post(
            self.calculate_url("unknown"),
            {},
            format="json",
        )

        self.assertEqual(defaults_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(defaults_response.data["error"]["code"], "calculator_not_found")
        self.assertIn("calcId", defaults_response.data["error"]["field_errors"])
        self.assertEqual(calculate_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(calculate_response.data["error"]["code"], "calculator_not_found")

    def test_credit_calculate_endpoint(self):
        self.authenticate()

        response = self.client.post(
            self.calculate_url("credit"),
            {
                "amount": 120000,
                "ratePct": 12,
                "termMonths": 12,
                "paymentType": "annuity",
                "issueDate": "2026-01-01",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertAlmostEqual(response.data["monthlyPayment"], 10661.85, places=2)
        self.assertEqual(len(response.data["schedule"]), 12)
        self.assertEqual(response.data["schedule"][-1]["remaining"], 0.0)

    def test_mortgage_calculate_endpoint(self):
        self.authenticate()

        response = self.client.post(
            self.calculate_url("mortgage"),
            {
                "propertyPrice": 6500000,
                "downPaymentPct": 20,
                "ratePct": 8.7,
                "termYears": 20,
                "withInsurance": True,
                "isFamilyMortgage": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertAlmostEqual(response.data["loanAmount"], 5200000.0, places=2)
        self.assertAlmostEqual(response.data["monthlyPayment"], 50120.52, places=2)
        self.assertGreater(response.data["recommendedIncome"], response.data["monthlyPayment"])

    def test_installment_calculate_endpoint(self):
        self.authenticate()

        response = self.client.post(
            self.calculate_url("installment"),
            {
                "price": 89990,
                "termMonths": 12,
                "bankFeePct": 0,
                "downPayment": 0,
                "zeroOverpayment": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["installment"]["overpayment"], 0.0)
        self.assertGreater(response.data["creditCard"]["overpayment"], 0)

    def test_deposit_calculate_endpoint(self):
        self.authenticate()

        response = self.client.post(
            self.calculate_url("deposit"),
            {
                "amount": 500000,
                "ratePct": 16,
                "termMonths": 12,
                "capitalization": "monthly",
                "topUp": "none",
                "monthlyTopUp": 10000,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertAlmostEqual(response.data["income"], 86135.40, places=2)
        self.assertAlmostEqual(response.data["finalAmount"], 586135.40, places=2)
        self.assertEqual(response.data["series"][0]["month"], 0)

    def test_pension_calculate_endpoint(self):
        self.authenticate()

        response = self.client.post(
            self.calculate_url("pension"),
            {
                "currentAge": 32,
                "retireAge": 65,
                "monthlyContribution": 15000,
                "returnRatePct": 8,
                "inflationPct": 5,
                "initialSaved": 240000,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertAlmostEqual(response.data["capitalAtRetirement"], 32338512.80, places=2)
        self.assertGreater(len(response.data["series"]), 2)

    def test_inflation_calculate_endpoint(self):
        self.authenticate()

        response = self.client.post(
            self.calculate_url("inflation"),
            {
                "amount": 1000000,
                "years": 10,
                "inflationPct": 5,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertAlmostEqual(response.data["futureValue"], 613913.25, places=2)
        self.assertAlmostEqual(response.data["lossPct"], 38.61, places=2)

    def test_empty_payload_returns_field_errors(self):
        self.authenticate()

        response = self.client.post(self.calculate_url("credit"), {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"]["code"], "VALIDATION_FAILED")
        self.assertIn("amount", response.data["error"]["field_errors"])
        self.assertIn("ratePct", response.data["error"]["field_errors"])

    def test_invalid_credit_payload_returns_validation_errors(self):
        self.authenticate()

        response = self.client.post(
            self.calculate_url("credit"),
            {
                "amount": -1,
                "ratePct": 150,
                "termMonths": 0,
                "paymentType": "wrong",
                "issueDate": "wrong-date",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        errors = response.data["error"]["field_errors"]
        self.assertIn("amount", errors)
        self.assertIn("ratePct", errors)
        self.assertIn("termMonths", errors)
        self.assertIn("paymentType", errors)
        self.assertIn("issueDate", errors)

    def test_cross_field_validation_errors(self):
        self.authenticate()

        installment_response = self.client.post(
            self.calculate_url("installment"),
            {
                "price": 89990,
                "termMonths": 12,
                "bankFeePct": 0,
                "downPayment": 89990,
                "zeroOverpayment": True,
            },
            format="json",
        )
        pension_response = self.client.post(
            self.calculate_url("pension"),
            {
                "currentAge": 65,
                "retireAge": 32,
                "monthlyContribution": 15000,
                "returnRatePct": 8,
                "inflationPct": 5,
                "initialSaved": 240000,
            },
            format="json",
        )

        self.assertEqual(installment_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("downPayment", installment_response.data["error"]["field_errors"])
        self.assertEqual(pension_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("retireAge", pension_response.data["error"]["field_errors"])
