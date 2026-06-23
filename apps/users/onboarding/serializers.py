from __future__ import annotations

from rest_framework import serializers

from apps.users.models import OnboardingSurveyStatus
from apps.users.onboarding.questions import get_question_map


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


class OnboardingQuestionOptionSerializer(serializers.Serializer):
    value = serializers.CharField(help_text="Машинное значение варианта ответа.")
    label = serializers.CharField(help_text="Подпись варианта ответа для интерфейса.")
    description = serializers.CharField(
        required=False,
        help_text="Дополнительное пояснение к варианту ответа.",
    )


class OnboardingQuestionSerializer(serializers.Serializer):
    id = serializers.CharField(help_text="Уникальный ключ вопроса.")
    stepId = serializers.CharField(help_text="Идентификатор шага анкеты.")
    order = serializers.IntegerField(help_text="Порядок отображения вопроса внутри анкеты.")
    type = serializers.ChoiceField(
        choices=["single_choice", "multi_choice", "boolean"],
        help_text="Тип поля: single_choice, multi_choice или boolean.",
    )
    title = serializers.CharField(help_text="Текст вопроса.")
    description = serializers.CharField(
        required=False,
        help_text="Дополнительное пояснение к вопросу.",
    )
    required = serializers.BooleanField(help_text="Обязателен ли вопрос для отправки анкеты.")
    minSelected = serializers.IntegerField(
        required=False,
        help_text="Минимальное количество выбранных вариантов для multi_choice.",
    )
    maxSelected = serializers.IntegerField(
        required=False,
        help_text="Максимальное количество выбранных вариантов для multi_choice.",
    )
    options = OnboardingQuestionOptionSerializer(
        many=True,
        required=False,
        help_text="Варианты ответа для choice-вопросов.",
    )


class OnboardingStepSerializer(serializers.Serializer):
    id = serializers.CharField(help_text="Уникальный идентификатор шага анкеты.")
    order = serializers.IntegerField(help_text="Порядок отображения шага.")
    title = serializers.CharField(help_text="Название шага.")
    description = serializers.CharField(help_text="Описание шага.")
    questions = OnboardingQuestionSerializer(
        many=True,
        help_text="Вопросы, которые относятся к шагу анкеты.",
    )


class OnboardingQuestionsResponseSerializer(serializers.Serializer):
    version = serializers.CharField(help_text="Версия конфигурации onboarding-анкеты.")
    title = serializers.CharField(help_text="Название анкеты для интерфейса.")
    description = serializers.CharField(help_text="Описание назначения onboarding-анкеты.")
    estimatedMinutes = serializers.IntegerField(help_text="Примерное время заполнения анкеты в минутах.")
    totalQuestions = serializers.IntegerField(help_text="Общее количество вопросов в анкете.")
    steps = OnboardingStepSerializer(
        many=True,
        help_text="Шаги анкеты с вложенными вопросами.",
    )


class OnboardingAnswersSubmitSerializer(serializers.Serializer):
    answers = serializers.JSONField(
        help_text="Ответы пользователя на onboarding-анкету. Ключи должны совпадать с id вопросов.",
    )

    def validate_answers(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Ответы onboarding должны быть объектом.", code="invalid")

        errors = {}
        normalized = {}
        question_map = get_question_map()

        for question_id, question in question_map.items():
            is_required = bool(question.get("required"))

            if question_id not in value:
                if is_required:
                    errors[question_id] = "Обязательный вопрос не заполнен."
                continue

            raw_answer = value.get(question_id)
            question_type = question["type"]

            if question_type == "single_choice":
                normalized_answer, error = self._validate_single_choice_answer(question, raw_answer)
            elif question_type == "multi_choice":
                normalized_answer, error = self._validate_multi_choice_answer(question, raw_answer)
            elif question_type == "boolean":
                normalized_answer, error = self._validate_boolean_answer(raw_answer)
            else:
                normalized_answer, error = None, "Тип вопроса не поддерживается."

            if error:
                errors[question_id] = error
            else:
                normalized[question_id] = normalized_answer

        unknown_question_ids = sorted(set(value.keys()) - set(question_map.keys()))
        for question_id in unknown_question_ids:
            errors[question_id] = "Неизвестный вопрос onboarding-анкеты."

        if errors:
            raise serializers.ValidationError(errors, code="invalid")

        return normalized

    def _validate_single_choice_answer(self, question: dict, value):
        if not isinstance(value, str) or not value.strip():
            return None, "Выберите один вариант ответа."

        normalized_value = value.strip()
        allowed_values = {option["value"] for option in question.get("options", [])}

        if normalized_value not in allowed_values:
            return None, "Выбран недопустимый вариант ответа."

        return normalized_value, None

    def _validate_multi_choice_answer(self, question: dict, value):
        if not isinstance(value, list):
            return None, "Передайте список выбранных вариантов."

        normalized_values = []
        for item in value:
            if not isinstance(item, str) or not item.strip():
                return None, "Все выбранные варианты должны быть строками."
            normalized_values.append(item.strip())

        unique_values = list(dict.fromkeys(normalized_values))
        min_selected = question.get("minSelected")
        max_selected = question.get("maxSelected")

        if min_selected is not None and len(unique_values) < min_selected:
            return None, f"Выберите не менее {min_selected} варианта(ов)."

        if max_selected is not None and len(unique_values) > max_selected:
            return None, f"Выберите не более {max_selected} варианта(ов)."

        allowed_values = {option["value"] for option in question.get("options", [])}
        invalid_values = [item for item in unique_values if item not in allowed_values]

        if invalid_values:
            return None, "Список содержит недопустимые варианты ответа."

        return unique_values, None

    def _validate_boolean_answer(self, value):
        if not isinstance(value, bool):
            return None, "Передайте значение true или false."

        return value, None


class OnboardingSubmitResultSerializer(serializers.Serializer):
    configurationApplied = serializers.BooleanField(
        help_text="Применена ли начальная конфигурация по ответам анкеты.",
    )
    nextStep = serializers.CharField(
        help_text="Следующий backend-шаг после сохранения ответов.",
    )
    created = serializers.DictField(
        child=serializers.IntegerField(),
        help_text="Количество созданных стартовых сущностей. До BUD-1057 значения равны нулю.",
    )


class OnboardingAnswersResponseSerializer(OnboardingStatusSerializer):
    answers = serializers.JSONField(help_text="Сохранённые ответы пользователя.")
    result = OnboardingSubmitResultSerializer(help_text="Результат обработки onboarding-ответов.")
