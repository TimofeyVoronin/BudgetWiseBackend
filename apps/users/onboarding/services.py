from __future__ import annotations

from collections import Counter

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from apps.users.models import OnboardingSurvey, OnboardingSurveyStatus
from apps.users.onboarding.configuration import (
    apply_onboarding_initial_configuration,
    build_default_onboarding_result,
)
from apps.users.onboarding.questions import get_onboarding_steps


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


def build_onboarding_analytics_payload() -> dict:
    surveys = list(OnboardingSurvey.objects.all().only("status", "answers", "started_at"))
    status_counts = _build_status_counts()
    started_count = _count_started_surveys(status_counts)
    completed_count = status_counts[OnboardingSurveyStatus.COMPLETED]
    completion_rate = _calculate_completion_rate(completed_count, started_count)
    steps, question_to_step = _build_onboarding_step_maps()

    return {
        "totalSurveys": len(surveys),
        "startedCount": started_count,
        "completedCount": completed_count,
        "inProgressCount": status_counts[OnboardingSurveyStatus.IN_PROGRESS],
        "failedCount": status_counts[OnboardingSurveyStatus.FAILED],
        "notStartedCount": status_counts[OnboardingSurveyStatus.NOT_STARTED],
        "completionRate": completion_rate,
        "statusCounts": dict(status_counts),
        "mostSkippedQuestions": _build_most_skipped_questions(surveys, steps),
        "dropOffSteps": _build_drop_off_steps(surveys, steps, question_to_step),
    }


def _build_status_counts() -> Counter:
    status_counts = Counter({status: 0 for status in OnboardingSurveyStatus.values})
    queryset = OnboardingSurvey.objects.values("status").annotate(count=Count("id"))

    for item in queryset:
        status_counts[item["status"]] = item["count"]

    return status_counts


def _count_started_surveys(status_counts: Counter) -> int:
    return sum(
        status_counts[status]
        for status in [
            OnboardingSurveyStatus.IN_PROGRESS,
            OnboardingSurveyStatus.COMPLETED,
            OnboardingSurveyStatus.FAILED,
        ]
    )


def _calculate_completion_rate(completed_count: int, started_count: int) -> float:
    if started_count == 0:
        return 0.0

    return round((completed_count / started_count) * 100, 2)


def _build_onboarding_step_maps() -> tuple[list[dict], dict[str, dict]]:
    steps = get_onboarding_steps()
    question_to_step = {}

    for step in steps:
        for question in step.get("questions", []):
            question_to_step[question["id"]] = {
                "id": step["id"],
                "title": step["title"],
                "order": step["order"],
            }

    return steps, question_to_step


def _build_most_skipped_questions(surveys: list[OnboardingSurvey], steps: list[dict]) -> list[dict]:
    answered_surveys = [
        survey
        for survey in surveys
        if isinstance(survey.answers, dict)
        and (survey.status != OnboardingSurveyStatus.NOT_STARTED or bool(survey.answers))
    ]
    total = len(answered_surveys)
    if total == 0:
        return []

    skipped_questions = []
    for step in steps:
        for question in step.get("questions", []):
            question_id = question["id"]
            skipped_count = sum(1 for survey in answered_surveys if question_id not in survey.answers)
            if skipped_count == 0:
                continue

            skipped_questions.append(
                {
                    "questionId": question_id,
                    "stepId": step["id"],
                    "title": question["title"],
                    "skippedCount": skipped_count,
                    "skippedRate": round((skipped_count / total) * 100, 2),
                }
            )

    return sorted(
        skipped_questions,
        key=lambda item: (-item["skippedCount"], item["stepId"], item["questionId"]),
    )


def _build_drop_off_steps(
    surveys: list[OnboardingSurvey],
    steps: list[dict],
    question_to_step: dict[str, dict],
) -> list[dict]:
    incomplete_surveys = [
        survey
        for survey in surveys
        if survey.status in {OnboardingSurveyStatus.IN_PROGRESS, OnboardingSurveyStatus.FAILED}
    ]
    if not incomplete_surveys:
        return []

    step_counters = Counter()
    step_titles = {step["id"]: step["title"] for step in steps}
    step_order = {step["id"]: step["order"] for step in steps}

    for survey in incomplete_surveys:
        step_id = _resolve_drop_off_step_id(survey, steps, question_to_step)
        step_counters[step_id] += 1

    total = len(incomplete_surveys)
    return [
        {
            "stepId": step_id,
            "title": step_titles.get(step_id, "Анкета не начата"),
            "dropOffCount": count,
            "dropOffRate": round((count / total) * 100, 2),
        }
        for step_id, count in sorted(
            step_counters.items(),
            key=lambda item: (step_order.get(item[0], 0), item[0]),
        )
    ]


def _resolve_drop_off_step_id(
    survey: OnboardingSurvey,
    steps: list[dict],
    question_to_step: dict[str, dict],
) -> str:
    if not isinstance(survey.answers, dict) or not survey.answers:
        return steps[0]["id"] if steps else "not_started"

    answered_step_ids = [
        question_to_step[question_id]["id"]
        for question_id in survey.answers.keys()
        if question_id in question_to_step
    ]
    if not answered_step_ids:
        return steps[0]["id"] if steps else "not_started"

    return max(
        answered_step_ids,
        key=lambda step_id: next(step["order"] for step in steps if step["id"] == step_id),
    )
