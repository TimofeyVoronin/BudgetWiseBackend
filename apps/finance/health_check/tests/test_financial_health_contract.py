from django.test import SimpleTestCase

from apps.finance.health_check.constants import (
    FINANCIAL_HEALTH_DEFAULT_CURRENCY,
    FINANCIAL_HEALTH_DEFAULT_PERIOD,
    FINANCIAL_HEALTH_SCORE_MAX,
    FINANCIAL_HEALTH_SCORE_MIN,
    METRIC_BUDGET_USAGE,
    METRIC_CASH_GAP_RISK,
    METRIC_EMERGENCY_FUND_PROGRESS,
    METRIC_EXPENSE_STABILITY,
    METRIC_INCOME_EXPENSE_RATIO,
    METRIC_PLANNED_PAYMENTS_LOAD,
    METRIC_SAVINGS_RATE,
)
from apps.finance.health_check.contracts import (
    build_financial_health_meta,
    get_financial_health_level,
    get_financial_health_metric_ids,
    validate_metric_weights,
)


class FinancialHealthContractTests(SimpleTestCase):
    def test_meta_contract_contains_metrics_levels_periods_and_summary_shape(self):
        meta = build_financial_health_meta()

        self.assertEqual(meta["scoreRange"]["min"], FINANCIAL_HEALTH_SCORE_MIN)
        self.assertEqual(meta["scoreRange"]["max"], FINANCIAL_HEALTH_SCORE_MAX)
        self.assertEqual(meta["defaultPeriod"], FINANCIAL_HEALTH_DEFAULT_PERIOD)
        self.assertEqual(meta["defaultCurrency"], FINANCIAL_HEALTH_DEFAULT_CURRENCY)
        self.assertGreaterEqual(len(meta["periods"]), 4)
        self.assertEqual(len(meta["levels"]), 5)
        self.assertEqual(len(meta["metrics"]), 7)
        self.assertIn("summaryContract", meta)
        self.assertIn("recommendations", meta["summaryContract"])
        self.assertIn("dataQuality", meta["summaryContract"])

    def test_metric_ids_match_first_version_scope(self):
        self.assertEqual(
            get_financial_health_metric_ids(),
            [
                METRIC_INCOME_EXPENSE_RATIO,
                METRIC_SAVINGS_RATE,
                METRIC_BUDGET_USAGE,
                METRIC_EMERGENCY_FUND_PROGRESS,
                METRIC_CASH_GAP_RISK,
                METRIC_PLANNED_PAYMENTS_LOAD,
                METRIC_EXPENSE_STABILITY,
            ],
        )

    def test_metric_weights_sum_to_one_hundred(self):
        self.assertTrue(validate_metric_weights())

    def test_score_level_boundaries_are_stable(self):
        cases = {
            -10: "critical",
            0: "critical",
            39: "critical",
            40: "risk",
            59: "risk",
            60: "warning",
            74: "warning",
            75: "good",
            89: "good",
            90: "excellent",
            100: "excellent",
            150: "excellent",
        }

        for score, expected_level in cases.items():
            with self.subTest(score=score):
                self.assertEqual(get_financial_health_level(score), expected_level)
