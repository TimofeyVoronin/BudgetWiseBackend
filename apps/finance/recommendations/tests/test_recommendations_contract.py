from django.test import SimpleTestCase

from apps.finance.recommendations.constants import (
    RECOMMENDATION_ACTION_ACCEPT,
    RECOMMENDATION_ACTION_HIDE,
    RECOMMENDATION_ACTION_SNOOZE,
    RECOMMENDATION_DEFAULT_PRIORITY,
    RECOMMENDATION_DEFAULT_STATUS,
    RECOMMENDATION_GENERATION_MODE_RULE_BASED,
    RECOMMENDATION_PRIORITY_HIGH,
    RECOMMENDATION_PRIORITY_LOW,
    RECOMMENDATION_PRIORITY_MEDIUM,
    RECOMMENDATION_STATUS_ACCEPTED,
    RECOMMENDATION_STATUS_ACTIVE,
    RECOMMENDATION_STATUS_EXPIRED,
    RECOMMENDATION_STATUS_HIDDEN,
    RECOMMENDATION_STATUS_NEW,
    RECOMMENDATION_STATUS_SNOOZED,
    RECOMMENDATION_TYPE_BUDGET,
    RECOMMENDATION_TYPE_CASHFLOW,
    RECOMMENDATION_TYPE_EXPENSE_STABILITY,
    RECOMMENDATION_TYPE_FINANCIAL_HEALTH,
    RECOMMENDATION_TYPE_GOAL,
    RECOMMENDATION_TYPE_ONBOARDING,
    RECOMMENDATION_TYPE_PLANNED_PAYMENT,
    RECOMMENDATION_TYPE_SAVING,
)
from apps.finance.recommendations.contracts import (
    build_recommendations_meta,
    get_recommendation_action_values,
    get_recommendation_code_values,
    get_recommendation_priority_values,
    get_recommendation_status_values,
    get_recommendation_type_values,
    validate_recommendation_contract,
)


class RecommendationsContractTests(SimpleTestCase):
    def test_recommendations_meta_contains_contract_sections(self):
        meta = build_recommendations_meta()

        self.assertEqual(meta["generation"]["mode"], RECOMMENDATION_GENERATION_MODE_RULE_BASED)
        self.assertFalse(meta["generation"]["mlEnabled"])
        self.assertTrue(meta["generation"]["usesFinancialHealthCheck"])
        self.assertEqual(meta["defaults"]["status"], RECOMMENDATION_DEFAULT_STATUS)
        self.assertEqual(meta["defaults"]["priority"], RECOMMENDATION_DEFAULT_PRIORITY)
        self.assertIn("types", meta)
        self.assertIn("statuses", meta)
        self.assertIn("priorities", meta)
        self.assertIn("actions", meta)
        self.assertIn("events", meta)
        self.assertIn("codes", meta)
        self.assertIn("endpoints", meta)
        self.assertIn("itemContract", meta)
        self.assertIn("statsContract", meta)

    def test_recommendation_types_match_first_version_scope(self):
        self.assertEqual(
            get_recommendation_type_values(),
            [
                RECOMMENDATION_TYPE_BUDGET,
                RECOMMENDATION_TYPE_SAVING,
                RECOMMENDATION_TYPE_GOAL,
                RECOMMENDATION_TYPE_CASHFLOW,
                RECOMMENDATION_TYPE_PLANNED_PAYMENT,
                RECOMMENDATION_TYPE_EXPENSE_STABILITY,
                RECOMMENDATION_TYPE_ONBOARDING,
                RECOMMENDATION_TYPE_FINANCIAL_HEALTH,
            ],
        )

    def test_statuses_priorities_and_actions_are_stable(self):
        self.assertEqual(
            get_recommendation_status_values(),
            [
                RECOMMENDATION_STATUS_NEW,
                RECOMMENDATION_STATUS_ACTIVE,
                RECOMMENDATION_STATUS_ACCEPTED,
                RECOMMENDATION_STATUS_HIDDEN,
                RECOMMENDATION_STATUS_SNOOZED,
                RECOMMENDATION_STATUS_EXPIRED,
            ],
        )
        self.assertEqual(
            get_recommendation_priority_values(),
            [
                RECOMMENDATION_PRIORITY_HIGH,
                RECOMMENDATION_PRIORITY_MEDIUM,
                RECOMMENDATION_PRIORITY_LOW,
            ],
        )
        actions = get_recommendation_action_values()
        self.assertIn(RECOMMENDATION_ACTION_ACCEPT, actions)
        self.assertIn(RECOMMENDATION_ACTION_HIDE, actions)
        self.assertIn(RECOMMENDATION_ACTION_SNOOZE, actions)

    def test_recommendation_codes_are_unique_and_cover_base_scenarios(self):
        codes = get_recommendation_code_values()

        self.assertEqual(len(codes), len(set(codes)))
        self.assertIn("create_budget", codes)
        self.assertIn("increase_savings_rate", codes)
        self.assertIn("create_emergency_fund_goal", codes)
        self.assertIn("fix_cash_gap_risk", codes)
        self.assertIn("complete_onboarding", codes)

    def test_contract_validation_passes(self):
        self.assertTrue(validate_recommendation_contract())
