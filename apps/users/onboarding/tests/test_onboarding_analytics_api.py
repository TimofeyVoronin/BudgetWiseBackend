from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.users.models import OnboardingSurvey, OnboardingSurveyStatus


User = get_user_model()


class OnboardingAnalyticsAPITests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse("users:onboarding-analytics")
        self.staff_user = User.objects.create_user(
            username="onboarding_analytics_staff",
            email="onboarding-analytics-staff@example.com",
            password="StrongPass123!",
            is_staff=True,
        )
        self.regular_user = User.objects.create_user(
            username="onboarding_analytics_regular",
            email="onboarding-analytics-regular@example.com",
            password="StrongPass123!",
        )

    def test_onboarding_analytics_requires_authentication(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"]["status_code"], 401)

    def test_onboarding_analytics_forbidden_for_regular_user(self):
        self.client.force_authenticate(user=self.regular_user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"]["status_code"], 403)

    def test_onboarding_analytics_returns_empty_stats_for_staff(self):
        self.client.force_authenticate(user=self.staff_user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["totalSurveys"], 0)
        self.assertEqual(response.data["startedCount"], 0)
        self.assertEqual(response.data["completedCount"], 0)
        self.assertEqual(response.data["completionRate"], 0.0)
        self.assertEqual(response.data["statusCounts"][OnboardingSurveyStatus.NOT_STARTED], 0)
        self.assertEqual(response.data["statusCounts"][OnboardingSurveyStatus.IN_PROGRESS], 0)
        self.assertEqual(response.data["statusCounts"][OnboardingSurveyStatus.COMPLETED], 0)
        self.assertEqual(response.data["statusCounts"][OnboardingSurveyStatus.FAILED], 0)
        self.assertEqual(response.data["mostSkippedQuestions"], [])
        self.assertEqual(response.data["dropOffSteps"], [])

    def test_onboarding_analytics_returns_status_counts_completion_and_drop_offs(self):
        completed_user = self._create_user("completed")
        in_progress_user = self._create_user("in_progress")
        failed_user = self._create_user("failed")
        not_started_user = self._create_user("not_started")

        OnboardingSurvey.objects.create(
            user=completed_user,
            status=OnboardingSurveyStatus.COMPLETED,
            answers={
                "mainGoal": "expense_control",
                "incomeType": "regular",
                "expenseAreas": ["food", "transport"],
                "budgetStyle": "balanced",
                "hasSavingsGoal": True,
                "defaultCurrency": "RUB",
            },
        )
        in_progress_survey = OnboardingSurvey.objects.create(
            user=in_progress_user,
            status=OnboardingSurveyStatus.IN_PROGRESS,
            answers={
                "mainGoal": "expense_control",
                "incomeType": "regular",
            },
        )
        in_progress_survey.mark_started()
        OnboardingSurvey.objects.create(
            user=failed_user,
            status=OnboardingSurveyStatus.FAILED,
            answers={
                "mainGoal": "budget_planning",
                "incomeType": "mixed",
                "expenseAreas": ["food"],
            },
        )
        OnboardingSurvey.objects.create(
            user=not_started_user,
            status=OnboardingSurveyStatus.NOT_STARTED,
            answers={},
        )
        self.client.force_authenticate(user=self.staff_user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["totalSurveys"], 4)
        self.assertEqual(response.data["startedCount"], 3)
        self.assertEqual(response.data["completedCount"], 1)
        self.assertEqual(response.data["inProgressCount"], 1)
        self.assertEqual(response.data["failedCount"], 1)
        self.assertEqual(response.data["notStartedCount"], 1)
        self.assertEqual(response.data["completionRate"], 33.33)
        self.assertEqual(response.data["statusCounts"][OnboardingSurveyStatus.COMPLETED], 1)

        skipped_question_ids = {
            item["questionId"]: item
            for item in response.data["mostSkippedQuestions"]
        }
        self.assertIn("defaultCurrency", skipped_question_ids)
        self.assertEqual(skipped_question_ids["defaultCurrency"]["skippedCount"], 2)

        drop_off_steps = {
            item["stepId"]: item
            for item in response.data["dropOffSteps"]
        }
        self.assertEqual(drop_off_steps["income"]["dropOffCount"], 1)
        self.assertEqual(drop_off_steps["expenses"]["dropOffCount"], 1)

    def _create_user(self, suffix: str):
        return User.objects.create_user(
            username=f"onboarding_analytics_{suffix}",
            email=f"onboarding-analytics-{suffix}@example.com",
            password="StrongPass123!",
        )
