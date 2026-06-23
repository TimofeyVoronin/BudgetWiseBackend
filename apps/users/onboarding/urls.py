from django.urls import path

from apps.users.onboarding.views import OnboardingStatusView


urlpatterns = [
    path("status/", OnboardingStatusView.as_view(), name="onboarding-status"),
]
