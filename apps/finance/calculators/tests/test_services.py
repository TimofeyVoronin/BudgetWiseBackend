from datetime import date

from django.test import SimpleTestCase

from apps.finance.calculators.services import (
    calculate_credit,
    calculate_deposit,
    calculate_inflation,
    calculate_installment,
    calculate_mortgage,
    calculate_pension,
    get_calculator_defaults,
    get_calculators_catalog,
)


class FinancialCalculatorFormulaTests(SimpleTestCase):
    def assert_money_close(self, actual, expected, places=2):
        self.assertAlmostEqual(float(actual), float(expected), places=places)

    def test_catalog_and_defaults_are_available_for_all_calculators(self):
        catalog = get_calculators_catalog()
        calculator_ids = {item["id"] for item in catalog}

        self.assertEqual(
            calculator_ids,
            {"credit", "mortgage", "installment", "deposit", "pension", "inflation"},
        )
        self.assertEqual(len(get_calculators_catalog("ипотека")), 1)

        for calculator_id in calculator_ids:
            defaults = get_calculator_defaults(calculator_id)
            self.assertEqual(defaults["calculatorId"], calculator_id)
            self.assertTrue(defaults["defaults"])

    def test_credit_annuity_formula_builds_stable_schedule(self):
        result = calculate_credit(
            {
                "amount": 120000,
                "ratePct": 12,
                "termMonths": 12,
                "paymentType": "annuity",
                "issueDate": date(2026, 1, 1),
            }
        )

        self.assert_money_close(result["monthlyPayment"], 10661.85)
        self.assert_money_close(result["totalPayment"], 127942.20)
        self.assert_money_close(result["overpayment"], 7942.20)
        self.assertEqual(len(result["schedule"]), 12)
        self.assertEqual(result["schedule"][0]["date"], "2026-02-01")
        self.assertEqual(result["schedule"][-1]["remaining"], 0.0)

    def test_credit_differentiated_formula_decreases_payment(self):
        result = calculate_credit(
            {
                "amount": 120000,
                "ratePct": 12,
                "termMonths": 12,
                "paymentType": "differentiated",
                "issueDate": date(2026, 1, 1),
            }
        )

        self.assert_money_close(result["firstPayment"], 11200.00)
        self.assert_money_close(result["lastPayment"], 10100.00)
        self.assertGreater(result["firstPayment"], result["lastPayment"])
        self.assertEqual(result["schedule"][-1]["remaining"], 0.0)

    def test_mortgage_calculates_loan_payment_income_and_shares(self):
        result = calculate_mortgage(
            {
                "propertyPrice": 6500000,
                "downPaymentPct": 20,
                "ratePct": 8.7,
                "termYears": 20,
                "withInsurance": True,
                "isFamilyMortgage": False,
            }
        )

        self.assert_money_close(result["loanAmount"], 5200000.00)
        self.assert_money_close(result["monthlyPayment"], 50120.52)
        self.assert_money_close(result["recommendedIncome"], 100241.05)
        self.assert_money_close(result["totalPayment"], 12028925.60)
        self.assert_money_close(result["totalInterest"], 6828925.60)
        self.assertAlmostEqual(result["principalShare"], 0.43, places=2)
        self.assertAlmostEqual(result["interestShare"], 0.57, places=2)

    def test_installment_without_overpayment_and_card_comparison(self):
        result = calculate_installment(
            {
                "price": 89990,
                "termMonths": 12,
                "bankFeePct": 0,
                "downPayment": 0,
                "zeroOverpayment": True,
            }
        )

        self.assert_money_close(result["installment"]["monthlyPayment"], 7499.17)
        self.assert_money_close(result["installment"]["totalToPay"], 89990.00)
        self.assertEqual(result["installment"]["overpayment"], 0.0)
        self.assertGreater(result["creditCard"]["overpayment"], 0)
        self.assertEqual(result["comparisonMeta"]["annualRatePct"], 29.9)

    def test_installment_with_fee_and_down_payment(self):
        result = calculate_installment(
            {
                "price": 120000,
                "termMonths": 12,
                "bankFeePct": 10,
                "downPayment": 20000,
                "zeroOverpayment": False,
            }
        )

        self.assert_money_close(result["installment"]["monthlyPayment"], 9166.67)
        self.assert_money_close(result["installment"]["totalToPay"], 110000.00)
        self.assert_money_close(result["installment"]["overpayment"], 10000.00)
        self.assertAlmostEqual(result["installment"]["overpaymentPct"], 10.0, places=2)

    def test_deposit_monthly_capitalization(self):
        result = calculate_deposit(
            {
                "amount": 500000,
                "ratePct": 16,
                "termMonths": 12,
                "capitalization": "monthly",
                "topUp": "none",
                "monthlyTopUp": 0,
            }
        )

        self.assert_money_close(result["income"], 86135.40)
        self.assert_money_close(result["finalAmount"], 586135.40)
        self.assertAlmostEqual(result["effectiveRatePct"], 17.23, places=2)
        self.assertEqual(len(result["series"]), 13)
        self.assertEqual(result["series"][0]["month"], 0)
        self.assertEqual(result["series"][-1]["month"], 12)

    def test_deposit_without_capitalization_with_monthly_top_up(self):
        result = calculate_deposit(
            {
                "amount": 100000,
                "ratePct": 12,
                "termMonths": 3,
                "capitalization": "none",
                "topUp": "monthly",
                "monthlyTopUp": 10000,
            }
        )

        self.assert_money_close(result["income"], 3300.00)
        self.assert_money_close(result["finalAmount"], 133300.00)
        self.assertEqual(len(result["series"]), 4)

    def test_pension_forecast_uses_return_and_inflation(self):
        result = calculate_pension(
            {
                "currentAge": 32,
                "retireAge": 65,
                "monthlyContribution": 15000,
                "returnRatePct": 8,
                "inflationPct": 5,
                "initialSaved": 240000,
            }
        )

        self.assert_money_close(result["capitalAtRetirement"], 32338512.80)
        self.assert_money_close(result["monthlyPensionReal"], 25966.40)
        self.assertEqual(result["series"][0]["age"], 32)
        self.assertEqual(result["series"][-1]["age"], 65)
        self.assertGreater(result["series"][-1]["growth"], result["series"][-1]["contributions"])

    def test_inflation_reduces_future_purchasing_power(self):
        result = calculate_inflation(
            {
                "amount": 1000000,
                "years": 10,
                "inflationPct": 5,
            }
        )

        self.assert_money_close(result["futureValue"], 613913.25)
        self.assert_money_close(result["purchasingPowerLoss"], 386086.75)
        self.assertAlmostEqual(result["lossPct"], 38.61, places=2)
