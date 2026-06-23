from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.users.models import OnboardingSurvey, OnboardingSurveyStatus


User = get_user_model()


class OnboardingSurveyModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="onboarding_user",
            email="onboarding-user@example.com",
            password="StrongPass123!",
        )

    def test_onboarding_survey_created_with_defaults(self):
        survey = OnboardingSurvey.objects.create(user=self.user)

        self.assertEqual(survey.status, OnboardingSurveyStatus.NOT_STARTED)
        self.assertEqual(survey.answers, {})
        self.assertEqual(survey.result, {})
        self.assertIsNone(survey.started_at)
        self.assertIsNone(survey.completed_at)
        self.assertFalse(survey.is_completed)

    def test_onboarding_survey_stores_answers_and_result(self):
        survey = OnboardingSurvey.objects.create(
            user=self.user,
            status=OnboardingSurveyStatus.IN_PROGRESS,
            started_at=timezone.now(),
            answers={
                "mainGoal": "expense_control",
                "expenseAreas": ["food", "transport"],
            },
            result={"created": {"categories": 2}},
        )

        survey.refresh_from_db()

        self.assertEqual(survey.answers["mainGoal"], "expense_control")
        self.assertEqual(survey.answers["expenseAreas"], ["food", "transport"])
        self.assertEqual(survey.result["created"]["categories"], 2)

    def test_onboarding_survey_is_unique_per_user(self):
        OnboardingSurvey.objects.create(user=self.user)

        with self.assertRaises(ValidationError) as context:
            OnboardingSurvey.objects.create(user=self.user)

        self.assertIn("user", context.exception.message_dict)

    def test_onboarding_survey_rejects_non_object_answers(self):
        survey = OnboardingSurvey(user=self.user, answers=["wrong"])

        with self.assertRaises(ValidationError) as context:
            survey.full_clean()

        self.assertIn("answers", context.exception.message_dict)

    def test_onboarding_survey_rejects_non_object_result(self):
        survey = OnboardingSurvey(user=self.user, result=["wrong"])

        with self.assertRaises(ValidationError) as context:
            survey.full_clean()

        self.assertIn("result", context.exception.message_dict)

    def test_mark_started_sets_in_progress_status(self):
        survey = OnboardingSurvey.objects.create(user=self.user)

        survey.mark_started()
        survey.refresh_from_db()

        self.assertEqual(survey.status, OnboardingSurveyStatus.IN_PROGRESS)
        self.assertIsNotNone(survey.started_at)
        self.assertIsNone(survey.completed_at)

    def test_mark_completed_sets_completed_status_and_result(self):
        survey = OnboardingSurvey.objects.create(user=self.user)

        survey.mark_completed(result={"created": {"categories": 3}})
        survey.refresh_from_db()

        self.assertEqual(survey.status, OnboardingSurveyStatus.COMPLETED)
        self.assertTrue(survey.is_completed)
        self.assertIsNotNone(survey.started_at)
        self.assertIsNotNone(survey.completed_at)
        self.assertEqual(survey.result["created"]["categories"], 3)

    def test_completed_status_auto_sets_completed_at(self):
        survey = OnboardingSurvey.objects.create(
            user=self.user,
            status=OnboardingSurveyStatus.COMPLETED,
        )

        self.assertIsNotNone(survey.completed_at)
