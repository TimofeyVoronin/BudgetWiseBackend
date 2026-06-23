from __future__ import annotations

from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.users.onboarding.questions import get_onboarding_quiz_config
from apps.users.onboarding.serializers import (
    OnboardingAnswersResponseSerializer,
    OnboardingAnswersSubmitSerializer,
    OnboardingQuestionsResponseSerializer,
    OnboardingStatusSerializer,
)
from apps.users.onboarding.services import (
    build_onboarding_answers_payload,
    build_onboarding_status_payload,
    save_onboarding_answers,
)


class OnboardingQuestionsView(GenericAPIView):
    serializer_class = OnboardingQuestionsResponseSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["users-onboarding"],
        operation_id="users_onboarding_questions_retrieve",
        summary="Получить конфигурацию onboarding-анкеты",
        description=(
            "Возвращает стабильную конфигурацию onboarding-анкеты: шаги, вопросы, "
            "варианты ответов, типы полей, обязательность и порядок отображения. "
            "Конфигурация нужна frontend после регистрации или при продолжении первичной настройки."
        ),
        responses={200: OnboardingQuestionsResponseSerializer},
        examples=[
            OpenApiExample(
                "Фрагмент ответа",
                value={
                    "version": "2026.06",
                    "title": "Стартовая настройка личных финансов",
                    "description": "Короткая анкета помогает подготовить приложение под задачи пользователя.",
                    "estimatedMinutes": 2,
                    "totalQuestions": 6,
                    "steps": [
                        {
                            "id": "goals",
                            "order": 1,
                            "title": "Цели",
                            "description": "Определяем, зачем пользователь начинает вести личные финансы.",
                            "questions": [
                                {
                                    "id": "mainGoal",
                                    "stepId": "goals",
                                    "order": 1,
                                    "type": "single_choice",
                                    "title": "Какая основная цель использования приложения?",
                                    "required": True,
                                    "options": [
                                        {
                                            "value": "expense_control",
                                            "label": "Контролировать расходы",
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                },
                response_only=True,
            )
        ],
    )
    def get(self, request, *args, **kwargs):
        serializer = self.get_serializer(get_onboarding_quiz_config())
        return Response(serializer.data)


class OnboardingAnswersView(GenericAPIView):
    serializer_class = OnboardingAnswersSubmitSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["users-onboarding"],
        operation_id="users_onboarding_answers_create",
        summary="Отправить ответы onboarding-анкеты",
        description=(
            "Принимает ответы пользователя, проверяет обязательные вопросы и допустимые значения, "
            "сохраняет ответы в OnboardingSurvey, применяет начальную конфигурацию пользователя "
            "и переводит анкету в статус completed. Стартовая конфигурация создаёт только "
            "недостающие категории, цели и бюджеты, поэтому повторная отправка не создаёт дубли."
        ),
        request=OnboardingAnswersSubmitSerializer,
        responses={200: OnboardingAnswersResponseSerializer, 400: OnboardingAnswersSubmitSerializer},
        examples=[
            OpenApiExample(
                "Пример запроса",
                value={
                    "answers": {
                        "mainGoal": "expense_control",
                        "incomeType": "regular",
                        "expenseAreas": ["food", "transport", "subscriptions"],
                        "budgetStyle": "balanced",
                        "hasSavingsGoal": True,
                        "defaultCurrency": "RUB",
                    }
                },
                request_only=True,
            ),
            OpenApiExample(
                "Успешный ответ",
                value={
                    "status": "completed",
                    "isCompleted": True,
                    "startedAt": "2026-06-23T10:00:00+0700",
                    "completedAt": "2026-06-23T10:05:00+0700",
                    "answers": {
                        "mainGoal": "expense_control",
                        "incomeType": "regular",
                        "expenseAreas": ["food", "transport", "subscriptions"],
                        "budgetStyle": "balanced",
                        "hasSavingsGoal": True,
                        "defaultCurrency": "RUB",
                    },
                    "result": {
                        "configurationApplied": True,
                        "nextStep": "dashboard",
                        "created": {
                            "categories": 4,
                            "goals": 1,
                            "budgets": 3,
                            "recommendations": 2,
                        },
                        "createdIds": {
                            "categories": [1, 2, 3, 4],
                            "goals": [1],
                            "budgets": [1, 2, 3],
                        },
                        "appliedSettings": {
                            "defaultCurrency": "RUB",
                            "defaultCurrencyChanged": False,
                        },
                        "recommendations": [
                            {
                                "id": "review-top-expenses",
                                "title": "Проверьте крупные расходы за месяц",
                                "description": (
                                    "Начните с регулярного просмотра категорий, "
                                    "где расходы растут быстрее всего."
                                ),
                            }
                        ],
                    },
                },
                response_only=True,
            ),
        ],
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        survey = save_onboarding_answers(
            request.user,
            serializer.validated_data["answers"],
        )
        response_serializer = OnboardingAnswersResponseSerializer(build_onboarding_answers_payload(survey))
        return Response(response_serializer.data, status=status.HTTP_200_OK)


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
