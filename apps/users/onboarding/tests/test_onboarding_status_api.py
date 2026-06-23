from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.users.models import OnboardingSurvey, OnboardingSurveyStatus


User = get_user_model()


class OnboardingStatusAPITests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse("users:onboarding-status")
        self.user = User.objects.create_user(
            username="onboarding_status_user",
            email="onboarding-status-user@example.com",
            password="StrongPass123!",
        )

    def test_onboarding_status_requires_authentication(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"]["status_code"], 401)

    def test_onboarding_status_returns_not_started_without_creating_survey(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], OnboardingSurveyStatus.NOT_STARTED)
        self.assertFalse(response.data["isCompleted"])
        self.assertIsNone(response.data["startedAt"])
        self.assertIsNone(response.data["completedAt"])
        self.assertFalse(OnboardingSurvey.objects.filter(user=self.user).exists())

    def test_onboarding_status_returns_in_progress_survey(self):
        survey = OnboardingSurvey.objects.create(user=self.user)
        survey.mark_started()
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], OnboardingSurveyStatus.IN_PROGRESS)
        self.assertFalse(response.data["isCompleted"])
        self.assertIsNotNone(response.data["startedAt"])
        self.assertIsNone(response.data["completedAt"])

    def test_onboarding_status_returns_completed_survey(self):
        survey = OnboardingSurvey.objects.create(user=self.user)
        survey.mark_completed(result={"created": {"categories": 3}})
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], OnboardingSurveyStatus.COMPLETED)
        self.assertTrue(response.data["isCompleted"])
        self.assertIsNotNone(response.data["startedAt"])
        self.assertIsNotNone(response.data["completedAt"])

    def test_onboarding_status_returns_failed_survey(self):
        survey = OnboardingSurvey.objects.create(user=self.user)
        survey.mark_failed(result={"error": "configuration_failed"})
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], OnboardingSurveyStatus.FAILED)
        self.assertFalse(response.data["isCompleted"])
        self.assertIsNone(response.data["completedAt"])
