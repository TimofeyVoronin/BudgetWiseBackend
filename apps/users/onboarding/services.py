from __future__ import annotations

from django.contrib.auth import get_user_model

from apps.users.models import OnboardingSurvey, OnboardingSurveyStatus


User = get_user_model()


def get_user_onboarding_survey(user: User) -> OnboardingSurvey | None:
    try:
        return user.onboarding_survey
    except OnboardingSurvey.DoesNotExist:
        return None


def get_user_onboarding_status(user: User) -> str:
    survey = get_user_onboarding_survey(user)
    if survey is None:
        return OnboardingSurveyStatus.NOT_STARTED

    return survey.status


def is_user_onboarding_completed(user: User) -> bool:
    return get_user_onboarding_status(user) == OnboardingSurveyStatus.COMPLETED


def build_onboarding_status_payload(user: User) -> dict:
    survey = get_user_onboarding_survey(user)

    if survey is None:
        return {
            "status": OnboardingSurveyStatus.NOT_STARTED,
            "isCompleted": False,
            "startedAt": None,
            "completedAt": None,
        }

    return {
        "status": survey.status,
        "isCompleted": survey.is_completed,
        "startedAt": survey.started_at,
        "completedAt": survey.completed_at,
    }
