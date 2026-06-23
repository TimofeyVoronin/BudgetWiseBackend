from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.users.models import OnboardingSurvey, OnboardingSurveyStatus
from apps.users.onboarding.configuration import (
    apply_onboarding_initial_configuration,
    build_default_onboarding_result,
)


User = get_user_model()


DEFAULT_ONBOARDING_RESULT = build_default_onboarding_result()


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


def build_onboarding_answers_payload(survey: OnboardingSurvey) -> dict:
    return {
        "status": survey.status,
        "isCompleted": survey.is_completed,
        "startedAt": survey.started_at,
        "completedAt": survey.completed_at,
        "answers": survey.answers,
        "result": survey.result or build_default_onboarding_result(),
    }


@transaction.atomic
def save_onboarding_answers(user: User, answers: dict) -> OnboardingSurvey:
    survey, _ = OnboardingSurvey.objects.select_for_update().get_or_create(user=user)
    now = timezone.now()
    result = apply_onboarding_initial_configuration(
        user,
        answers,
        previous_result=survey.result,
    )

    survey.answers = answers
    survey.status = OnboardingSurveyStatus.COMPLETED
    if survey.started_at is None:
        survey.started_at = now
    survey.completed_at = now
    survey.result = result
    survey.save(
        update_fields=[
            "answers",
            "status",
            "started_at",
            "completed_at",
            "result",
            "updated_at",
        ]
    )

    return survey
