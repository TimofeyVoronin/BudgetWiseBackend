from __future__ import annotations

from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.users.onboarding.serializers import OnboardingStatusSerializer
from apps.users.onboarding.services import build_onboarding_status_payload


class OnboardingStatusView(GenericAPIView):
    serializer_class = OnboardingStatusSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["users-onboarding"],
        operation_id="users_onboarding_status_retrieve",
        summary="Получить статус onboarding текущего пользователя",
        description=(
            "Возвращает текущий статус прохождения onboarding-анкеты. "
            "Frontend использует эти данные, чтобы решить, показывать анкету, "
            "экран продолжения заполнения или обычный dashboard. Если анкета ещё "
            "не создавалась, backend возвращает статус not_started без создания записи в базе."
        ),
        responses={200: OnboardingStatusSerializer},
        examples=[
            OpenApiExample(
                "Анкета ещё не начата",
                value={
                    "status": "not_started",
                    "isCompleted": False,
                    "startedAt": None,
                    "completedAt": None,
                },
                response_only=True,
            ),
            OpenApiExample(
                "Анкета завершена",
                value={
                    "status": "completed",
                    "isCompleted": True,
                    "startedAt": "2026-06-23T10:00:00+0700",
                    "completedAt": "2026-06-23T10:05:00+0700",
                },
                response_only=True,
            ),
        ],
    )
    def get(self, request, *args, **kwargs):
        serializer = self.get_serializer(build_onboarding_status_payload(request.user))
        return Response(serializer.data)
