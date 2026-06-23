from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.finance.models import Budget, Category, Goal
from apps.users.models import OnboardingSurvey, OnboardingSurveyStatus


User = get_user_model()


class OnboardingFullFlowAPITests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.questions_url = reverse("users:onboarding-questions")
        self.status_url = reverse("users:onboarding-status")
        self.answers_url = reverse("users:onboarding-answers")
        self.analytics_url = reverse("users:onboarding-analytics")
        self.user = User.objects.create_user(
            username="onboarding_flow_user",
            email="onboarding-flow-user@example.com",
            password="StrongPass123!",
        )
        self.other_user = User.objects.create_user(
            username="onboarding_flow_other_user",
            email="onboarding-flow-other-user@example.com",
            password="StrongPass123!",
        )
        self.staff_user = User.objects.create_user(
            username="onboarding_flow_staff_user",
            email="onboarding-flow-staff-user@example.com",
            password="StrongPass123!",
            is_staff=True,
        )
        self.payload = {
            "answers": {
                "mainGoal": "expense_control",
                "incomeType": "regular",
                "expenseAreas": ["food", "transport", "subscriptions"],
                "budgetStyle": "balanced",
                "hasSavingsGoal": True,
                "defaultCurrency": "RUB",
            }
        }

    def test_complete_onboarding_flow_from_status_to_analytics(self):
        self.client.force_authenticate(user=self.user)

        initial_status_response = self.client.get(self.status_url)
        self.assertEqual(initial_status_response.status_code, status.HTTP_200_OK)
        self.assertEqual(initial_status_response.data["status"], OnboardingSurveyStatus.NOT_STARTED)
        self.assertFalse(initial_status_response.data["isCompleted"])
        self.assertFalse(OnboardingSurvey.objects.filter(user=self.user).exists())

        questions_response = self.client.get(self.questions_url)
        self.assertEqual(questions_response.status_code, status.HTTP_200_OK)
        self.assertEqual(questions_response.data["totalQuestions"], 6)
        question_ids = {
            question["id"]
            for step in questions_response.data["steps"]
            for question in step["questions"]
        }
        self.assertSetEqual(
            question_ids,
            {
                "mainGoal",
                "incomeType",
                "expenseAreas",
                "budgetStyle",
                "hasSavingsGoal",
                "defaultCurrency",
            },
        )

        submit_response = self.client.post(self.answers_url, self.payload, format="json")
        self.assertEqual(submit_response.status_code, status.HTTP_200_OK)
        self.assertEqual(submit_response.data["status"], OnboardingSurveyStatus.COMPLETED)
        self.assertTrue(submit_response.data["isCompleted"])
        self.assertTrue(submit_response.data["result"]["configurationApplied"])
        self.assertEqual(submit_response.data["result"]["nextStep"], "dashboard")

        survey = OnboardingSurvey.objects.get(user=self.user)
        self.assertEqual(survey.status, OnboardingSurveyStatus.COMPLETED)
        self.assertEqual(survey.answers, self.payload["answers"])
        self.assertTrue(survey.result["configurationApplied"])
        self.assertEqual(Category.objects.filter(user=self.user).count(), 4)
        self.assertEqual(Budget.objects.filter(user=self.user).count(), 3)
        self.assertEqual(Goal.objects.filter(user=self.user).count(), 1)

        completed_status_response = self.client.get(self.status_url)
        self.assertEqual(completed_status_response.status_code, status.HTTP_200_OK)
        self.assertEqual(completed_status_response.data["status"], OnboardingSurveyStatus.COMPLETED)
        self.assertTrue(completed_status_response.data["isCompleted"])
        self.assertIsNotNone(completed_status_response.data["startedAt"])
        self.assertIsNotNone(completed_status_response.data["completedAt"])

        self.client.force_authenticate(user=self.staff_user)
        analytics_response = self.client.get(self.analytics_url)
        self.assertEqual(analytics_response.status_code, status.HTTP_200_OK)
        self.assertEqual(analytics_response.data["totalSurveys"], 1)
        self.assertEqual(analytics_response.data["startedCount"], 1)
        self.assertEqual(analytics_response.data["completedCount"], 1)
        self.assertEqual(analytics_response.data["completionRate"], 100.0)
        self.assertEqual(analytics_response.data["statusCounts"][OnboardingSurveyStatus.COMPLETED], 1)

    def test_onboarding_data_is_isolated_between_users(self):
        self.client.force_authenticate(user=self.user)
        first_response = self.client.post(self.answers_url, self.payload, format="json")
        self.assertEqual(first_response.status_code, status.HTTP_200_OK)

        self.client.force_authenticate(user=self.other_user)
        other_status_response = self.client.get(self.status_url)
        self.assertEqual(other_status_response.status_code, status.HTTP_200_OK)
        self.assertEqual(other_status_response.data["status"], OnboardingSurveyStatus.NOT_STARTED)
        self.assertFalse(OnboardingSurvey.objects.filter(user=self.other_user).exists())
        self.assertFalse(Category.objects.filter(user=self.other_user).exists())
        self.assertFalse(Budget.objects.filter(user=self.other_user).exists())
        self.assertFalse(Goal.objects.filter(user=self.other_user).exists())

        other_payload = {
            "answers": {
                "mainGoal": "budget_planning",
                "incomeType": "none",
                "expenseAreas": ["health"],
                "budgetStyle": "strict",
                "hasSavingsGoal": False,
                "defaultCurrency": "USD",
            }
        }
        other_submit_response = self.client.post(self.answers_url, other_payload, format="json")
        self.assertEqual(other_submit_response.status_code, status.HTTP_200_OK)

        self.assertEqual(OnboardingSurvey.objects.filter(user=self.user).count(), 1)
        self.assertEqual(OnboardingSurvey.objects.filter(user=self.other_user).count(), 1)
        self.assertEqual(Category.objects.filter(user=self.user).count(), 4)
        self.assertEqual(Budget.objects.filter(user=self.user).count(), 3)
        self.assertEqual(Goal.objects.filter(user=self.user).count(), 1)
        self.assertEqual(Category.objects.filter(user=self.other_user).count(), 2)
        self.assertEqual(Budget.objects.filter(user=self.other_user).count(), 1)
        self.assertEqual(Goal.objects.filter(user=self.other_user).count(), 0)

    def test_repeated_submission_with_changed_answers_does_not_create_duplicate_configuration(self):
        self.client.force_authenticate(user=self.user)
        first_response = self.client.post(self.answers_url, self.payload, format="json")
        self.assertEqual(first_response.status_code, status.HTTP_200_OK)

        updated_payload = {
            "answers": {
                **self.payload["answers"],
                "expenseAreas": ["food", "health", "travel"],
                "hasSavingsGoal": False,
                "defaultCurrency": "EUR",
            }
        }
        second_response = self.client.post(self.answers_url, updated_payload, format="json")
        self.assertEqual(second_response.status_code, status.HTTP_200_OK)

        survey = OnboardingSurvey.objects.get(user=self.user)
        self.assertEqual(survey.answers, updated_payload["answers"])
        self.assertEqual(OnboardingSurvey.objects.filter(user=self.user).count(), 1)
        self.assertEqual(Category.objects.filter(user=self.user).count(), 4)
        self.assertEqual(Budget.objects.filter(user=self.user).count(), 3)
        self.assertEqual(Goal.objects.filter(user=self.user).count(), 1)
        self.assertEqual(second_response.data["result"], first_response.data["result"])

    def test_invalid_answers_do_not_create_survey_or_initial_configuration(self):
        self.client.force_authenticate(user=self.user)
        invalid_payload = {
            "answers": {
                **self.payload["answers"],
                "expenseAreas": [],
            }
        }

        response = self.client.post(self.answers_url, invalid_payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("answers", response.data["error"]["field_errors"])
        self.assertFalse(OnboardingSurvey.objects.filter(user=self.user).exists())
        self.assertFalse(Category.objects.filter(user=self.user).exists())
        self.assertFalse(Budget.objects.filter(user=self.user).exists())
        self.assertFalse(Goal.objects.filter(user=self.user).exists())

    def test_answers_reject_too_many_expense_areas(self):
        self.client.force_authenticate(user=self.user)
        invalid_payload = {
            "answers": {
                **self.payload["answers"],
                "expenseAreas": [
                    "food",
                    "transport",
                    "housing",
                    "subscriptions",
                    "health",
                    "education",
                    "travel",
                ],
            }
        }

        response = self.client.post(self.answers_url, invalid_payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("answers", response.data["error"]["field_errors"])
        self.assertFalse(OnboardingSurvey.objects.filter(user=self.user).exists())

    def test_answers_reject_non_object_answers_payload(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(self.answers_url, {"answers": []}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("answers", response.data["error"]["field_errors"])
        self.assertFalse(OnboardingSurvey.objects.filter(user=self.user).exists())
