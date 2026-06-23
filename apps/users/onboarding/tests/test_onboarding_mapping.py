from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.finance.models import Budget, Category, Goal, TransactionType
from apps.users.app_settings.services import get_or_create_user_app_settings
from apps.users.models import OnboardingSurvey


User = get_user_model()


class OnboardingInitialConfigurationTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse("users:onboarding-answers")
        self.user = User.objects.create_user(
            username="onboarding_mapping_user",
            email="onboarding-mapping-user@example.com",
            password="StrongPass123!",
        )
        self.client.force_authenticate(user=self.user)
        self.payload = {
            "answers": {
                "mainGoal": "expense_control",
                "incomeType": "regular",
                "expenseAreas": ["food", "transport", "subscriptions"],
                "budgetStyle": "balanced",
                "hasSavingsGoal": True,
                "defaultCurrency": "EUR",
            }
        }

    def test_answers_submission_applies_initial_configuration(self):
        response = self.client.post(self.url, self.payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result = response.data["result"]

        self.assertTrue(result["configurationApplied"])
        self.assertEqual(result["nextStep"], "dashboard")
        self.assertEqual(result["created"]["categories"], 4)
        self.assertEqual(result["created"]["goals"], 1)
        self.assertEqual(result["created"]["budgets"], 3)
        self.assertGreaterEqual(result["created"]["recommendations"], 1)
        self.assertEqual(result["appliedSettings"]["defaultCurrency"], "EUR")

        self.assertEqual(Category.objects.filter(user=self.user, type=TransactionType.EXPENSE).count(), 3)
        self.assertEqual(Category.objects.filter(user=self.user, type=TransactionType.INCOME).count(), 1)
        self.assertEqual(Budget.objects.filter(user=self.user).count(), 3)
        self.assertEqual(Goal.objects.filter(user=self.user).count(), 1)

        settings = get_or_create_user_app_settings(self.user)
        self.assertEqual(settings.default_currency, "EUR")

        survey = OnboardingSurvey.objects.get(user=self.user)
        self.assertTrue(survey.result["configurationApplied"])
        self.assertEqual(survey.result["created"]["budgets"], 3)

    def test_repeated_submission_does_not_create_duplicates(self):
        first_response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(first_response.status_code, status.HTTP_200_OK)

        second_response = self.client.post(self.url, self.payload, format="json")

        self.assertEqual(second_response.status_code, status.HTTP_200_OK)
        self.assertEqual(Category.objects.filter(user=self.user).count(), 4)
        self.assertEqual(Budget.objects.filter(user=self.user).count(), 3)
        self.assertEqual(Goal.objects.filter(user=self.user).count(), 1)
        self.assertEqual(OnboardingSurvey.objects.filter(user=self.user).count(), 1)
        self.assertEqual(second_response.data["result"]["created"], first_response.data["result"]["created"])

    def test_existing_category_is_reused(self):
        Category.objects.create(
            user=self.user,
            name="Продукты и кафе",
            type=TransactionType.EXPENSE,
            icon="shopping-cart",
            color="#10B981",
        )

        response = self.client.post(self.url, self.payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Category.objects.filter(user=self.user, name="Продукты и кафе").count(), 1)
        self.assertEqual(response.data["result"]["created"]["categories"], 3)
        self.assertEqual(Budget.objects.filter(user=self.user).count(), 3)

    def test_savings_goal_is_not_created_when_user_does_not_need_it(self):
        payload = {
            "answers": {
                **self.payload["answers"],
                "mainGoal": "budget_planning",
                "hasSavingsGoal": False,
            }
        }

        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["result"]["created"]["goals"], 0)
        self.assertFalse(Goal.objects.filter(user=self.user).exists())
