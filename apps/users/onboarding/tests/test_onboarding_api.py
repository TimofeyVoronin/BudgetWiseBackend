from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.users.models import OnboardingSurvey, OnboardingSurveyStatus


User = get_user_model()


class OnboardingQuestionsAPITests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse("users:onboarding-questions")
        self.user = User.objects.create_user(
            username="onboarding_questions_user",
            email="onboarding-questions-user@example.com",
            password="StrongPass123!",
        )

    def test_onboarding_questions_requires_authentication(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"]["status_code"], 401)

    def test_onboarding_questions_returns_quiz_configuration(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["version"], "2026.06")
        self.assertEqual(response.data["totalQuestions"], 6)
        self.assertGreaterEqual(len(response.data["steps"]), 1)

        questions = [
            question
            for step in response.data["steps"]
            for question in step["questions"]
        ]
        question_ids = {question["id"] for question in questions}

        self.assertIn("mainGoal", question_ids)
        self.assertIn("incomeType", question_ids)
        self.assertIn("expenseAreas", question_ids)
        self.assertIn("budgetStyle", question_ids)
        self.assertIn("hasSavingsGoal", question_ids)
        self.assertIn("defaultCurrency", question_ids)


class OnboardingAnswersAPITests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse("users:onboarding-answers")
        self.status_url = reverse("users:onboarding-status")
        self.user = User.objects.create_user(
            username="onboarding_answers_user",
            email="onboarding-answers-user@example.com",
            password="StrongPass123!",
        )
        self.valid_payload = {
            "answers": {
                "mainGoal": "expense_control",
                "incomeType": "regular",
                "expenseAreas": ["food", "transport", "subscriptions"],
                "budgetStyle": "balanced",
                "hasSavingsGoal": True,
                "defaultCurrency": "RUB",
            }
        }

    def test_onboarding_answers_requires_authentication(self):
        response = self.client.post(self.url, self.valid_payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"]["status_code"], 401)

    def test_onboarding_answers_save_completed_survey(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(self.url, self.valid_payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], OnboardingSurveyStatus.COMPLETED)
        self.assertTrue(response.data["isCompleted"])
        self.assertIsNotNone(response.data["startedAt"])
        self.assertIsNotNone(response.data["completedAt"])
        self.assertEqual(response.data["answers"]["mainGoal"], "expense_control")
        self.assertTrue(response.data["result"]["configurationApplied"])
        self.assertEqual(response.data["result"]["nextStep"], "dashboard")
        self.assertGreaterEqual(response.data["result"]["created"]["categories"], 1)
        self.assertGreaterEqual(response.data["result"]["created"]["budgets"], 1)
        self.assertGreaterEqual(response.data["result"]["created"]["recommendations"], 1)

        survey = OnboardingSurvey.objects.get(user=self.user)
        self.assertEqual(survey.status, OnboardingSurveyStatus.COMPLETED)
        self.assertEqual(survey.answers["defaultCurrency"], "RUB")
        self.assertTrue(survey.result["configurationApplied"])

    def test_onboarding_answers_update_existing_survey_without_duplicate(self):
        self.client.force_authenticate(user=self.user)
        self.client.post(self.url, self.valid_payload, format="json")

        updated_payload = {
            "answers": {
                **self.valid_payload["answers"],
                "mainGoal": "budget_planning",
                "expenseAreas": ["food", "housing"],
            }
        }
        response = self.client.post(self.url, updated_payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["answers"]["mainGoal"], "budget_planning")
        self.assertEqual(OnboardingSurvey.objects.filter(user=self.user).count(), 1)

    def test_onboarding_status_returns_completed_after_answers_submission(self):
        self.client.force_authenticate(user=self.user)
        self.client.post(self.url, self.valid_payload, format="json")

        response = self.client.get(self.status_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], OnboardingSurveyStatus.COMPLETED)
        self.assertTrue(response.data["isCompleted"])

    def test_onboarding_answers_reject_missing_required_question(self):
        self.client.force_authenticate(user=self.user)
        payload = {"answers": {**self.valid_payload["answers"]}}
        payload["answers"].pop("mainGoal")

        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("answers", response.data["error"]["field_errors"])
        self.assertFalse(OnboardingSurvey.objects.filter(user=self.user).exists())

    def test_onboarding_answers_reject_invalid_choice(self):
        self.client.force_authenticate(user=self.user)
        payload = {
            "answers": {
                **self.valid_payload["answers"],
                "defaultCurrency": "BAD",
            }
        }

        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("answers", response.data["error"]["field_errors"])

    def test_onboarding_answers_reject_unknown_question(self):
        self.client.force_authenticate(user=self.user)
        payload = {
            "answers": {
                **self.valid_payload["answers"],
                "unknownQuestion": "value",
            }
        }

        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("answers", response.data["error"]["field_errors"])

    def test_onboarding_answers_reject_wrong_boolean_type(self):
        self.client.force_authenticate(user=self.user)
        payload = {
            "answers": {
                **self.valid_payload["answers"],
                "hasSavingsGoal": "true",
            }
        }

        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("answers", response.data["error"]["field_errors"])
