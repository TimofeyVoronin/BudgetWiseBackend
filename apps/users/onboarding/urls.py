from django.urls import path

from apps.users.onboarding.views import (
    OnboardingAnalyticsView,
    OnboardingAnswersView,
    OnboardingQuestionsView,
    OnboardingStatusView,
)


urlpatterns = [
    path("questions/", OnboardingQuestionsView.as_view(), name="onboarding-questions"),
    path("status/", OnboardingStatusView.as_view(), name="onboarding-status"),
    path("answers/", OnboardingAnswersView.as_view(), name="onboarding-answers"),
    path("analytics/", OnboardingAnalyticsView.as_view(), name="onboarding-analytics"),
]
