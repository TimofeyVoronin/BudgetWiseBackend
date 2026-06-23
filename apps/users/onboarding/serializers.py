from __future__ import annotations

from rest_framework import serializers

from apps.users.models import OnboardingSurveyStatus


class OnboardingStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=OnboardingSurveyStatus.choices,
        help_text="Текущий статус onboarding пользователя.",
    )
    isCompleted = serializers.BooleanField(
        help_text="Завершил ли пользователь onboarding-анкету.",
    )
    startedAt = serializers.DateTimeField(
        allow_null=True,
        help_text="Дата начала onboarding или null, если анкета ещё не начата.",
    )
    completedAt = serializers.DateTimeField(
        allow_null=True,
        help_text="Дата завершения onboarding или null, если анкета ещё не завершена.",
    )
