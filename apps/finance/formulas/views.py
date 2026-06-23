from __future__ import annotations

from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.finance.formulas.constants import FORMULA_IDE_TAG
from apps.finance.formulas.serializers import (
    FormulaIdeMetaResponseSerializer,
    FormulaIdeStateResponseSerializer,
    FormulaIdeStateSaveResponseSerializer,
    FormulaIdeStateUpdateSerializer,
    FormulaIdePreviewRequestSerializer,
    FormulaIdePreviewResponseSerializer,
    FormulaIdeValidationRequestSerializer,
    FormulaIdeValidationResponseSerializer,
)
from apps.finance.formulas.services import (
    get_formula_ide_meta,
    get_formula_ide_state,
    save_formula_ide_state,
    validate_formula_ide_code,
)
from apps.finance.formulas.evaluator import (
    FormulaEvaluationError,
    build_formula_preview,
    build_formula_validation_failed_payload,
)


class FormulaIdeStateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=[FORMULA_IDE_TAG],
        summary="Получить состояние редактора формул",
        description=(
            "Возвращает сохранённый черновик текущего пользователя для редактора формул. "
            "Если черновик ещё не создан, возвращает дефолтный пример с is_saved=false."
        ),
        responses={
            200: FormulaIdeStateResponseSerializer,
            401: OpenApiResponse(description="Пользователь не авторизован."),
        },
        examples=[
            OpenApiExample(
                "Состояние редактора",
                value={
                    "formula_id": "draft-default",
                    "code": "RETURN start_balance + income - expenses;",
                    "constructor_blocks": [
                        {"id": "b1", "kind": "function", "label": "SUM"},
                    ],
                    "updated_at": "2026-06-13T10:00:00Z",
                    "is_saved": True,
                },
                response_only=True,
            )
        ],
    )
    def get(self, request):
        return Response(get_formula_ide_state(user=request.user))

    @extend_schema(
        tags=[FORMULA_IDE_TAG],
        summary="Сохранить черновик редактора формул",
        description=(
            "Сохраняет код формулы и блоки конструктора для текущего пользователя. "
            "Валидация DSL и предпросмотр результата реализуются отдельными endpoint'ами."
        ),
        request=FormulaIdeStateUpdateSerializer,
        responses={
            200: FormulaIdeStateSaveResponseSerializer,
            400: OpenApiResponse(description="Некорректное тело запроса."),
            401: OpenApiResponse(description="Пользователь не авторизован."),
        },
        examples=[
            OpenApiExample(
                "Save draft request",
                value={
                    "code": "RETURN start_balance + income - expenses;",
                    "constructor_blocks": [
                        {"id": "b1", "kind": "function", "label": "SUM"},
                    ],
                },
                request_only=True,
            )
        ],
    )
    def put(self, request):
        serializer = FormulaIdeStateUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = save_formula_ide_state(
            user=request.user,
            code=serializer.validated_data["code"],
            constructor_blocks=serializer.validated_data.get("constructor_blocks", []),
        )
        return Response(payload)


class FormulaIdeMetaView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=[FORMULA_IDE_TAG],
        summary="Получить метаданные редактора формул",
        description=(
            "Возвращает справочник палитр, переменных, операторов и элементов автодополнения "
            "для IDE финансовых формул. Данные можно кэшировать на стороне клиента."
        ),
        responses={
            200: FormulaIdeMetaResponseSerializer,
            401: OpenApiResponse(description="Пользователь не авторизован."),
        },
    )
    def get(self, request):
        return Response(get_formula_ide_meta())


class FormulaIdeValidateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=[FORMULA_IDE_TAG],
        summary="Проверить DSL-код формулы",
        description=(
            "Проверяет DSL-код финансовой формулы без выполнения выражения и без доступа "
            "к пользовательским финансовым данным. Возвращает is_valid=true, если ошибок нет. "
            "Ошибки DSL возвращаются в ответе 200 с is_valid=false, чтобы интерфейс мог "
            "показать их в панели редактора."
        ),
        request=FormulaIdeValidationRequestSerializer,
        responses={
            200: FormulaIdeValidationResponseSerializer,
            400: OpenApiResponse(description="Некорректное тело запроса."),
            401: OpenApiResponse(description="Пользователь не авторизован."),
        },
        examples=[
            OpenApiExample(
                "Valid formula request",
                value={"code": "RETURN start_balance + income - expenses;"},
                request_only=True,
            ),
            OpenApiExample(
                "Valid formula response",
                value={"is_valid": True, "errors": []},
                response_only=True,
            ),
            OpenApiExample(
                "Invalid formula response",
                value={
                    "is_valid": False,
                    "errors": [
                        {
                            "id": "missing-return",
                            "line": 1,
                            "message": "В формуле должен быть оператор RETURN.",
                            "severity": "error",
                        }
                    ],
                },
                response_only=True,
            ),
        ],
    )
    def post(self, request):
        serializer = FormulaIdeValidationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = validate_formula_ide_code(code=serializer.validated_data["code"])
        return Response(payload)



class FormulaIdePreviewView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=[FORMULA_IDE_TAG],
        summary="Выполнить предпросмотр формулы",
        description=(
            "Проверяет DSL-код, безопасно выполняет поддерживаемую часть формулы "
            "на финансовых данных текущего пользователя и возвращает строки результата "
            "и точки графика для интерфейса редактора."
        ),
        request=FormulaIdePreviewRequestSerializer,
        responses={
            200: FormulaIdePreviewResponseSerializer,
            400: OpenApiResponse(description="Некорректное тело запроса."),
            401: OpenApiResponse(description="Пользователь не авторизован."),
            422: OpenApiResponse(description="Ошибки DSL или неподдерживаемая конструкция формулы."),
        },
        examples=[
            OpenApiExample(
                "Preview request",
                value={
                    "code": "LET income = SUM(TRANSACTIONS(type: INCOME, date: $period)); RETURN income;",
                    "constructor_blocks": [],
                },
                request_only=True,
            ),
            OpenApiExample(
                "Preview response",
                value={
                    "rows": [
                        {"id": "income", "label": "Итого доход", "value": "125 400 ₽", "highlight": False},
                        {"id": "expense", "label": "Итого расход", "value": "89 200 ₽", "highlight": False},
                        {"id": "net", "label": "Чистый поток", "value": "36 200 ₽", "highlight": True},
                    ],
                    "chart_points": [
                        {"month": "Янв", "value": 12000},
                        {"month": "Фев", "value": 18000},
                    ],
                },
                response_only=True,
            ),
            OpenApiExample(
                "Preview DSL error",
                value={
                    "detail": "В формуле найдены ошибки",
                    "errors": [
                        {
                            "id": "missing-return",
                            "line": 1,
                            "message": "В формуле должен быть оператор RETURN.",
                            "severity": "error",
                        }
                    ],
                    "error": {
                        "code": "FORMULA_VALIDATION_FAILED",
                        "message": "В формуле найдены ошибки",
                        "errors": [
                            {
                                "id": "missing-return",
                                "line": 1,
                                "message": "В формуле должен быть оператор RETURN.",
                                "severity": "error",
                            }
                        ],
                    },
                },
                response_only=True,
                status_codes=["422"],
            ),
        ],
    )
    def post(self, request):
        serializer = FormulaIdePreviewRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            payload = build_formula_preview(
                user=request.user,
                code=serializer.validated_data["code"],
                constructor_blocks=serializer.validated_data.get("constructor_blocks", []),
            )
        except FormulaEvaluationError as exc:
            errors = [diagnostic.to_dict() for diagnostic in exc.diagnostics]
            return Response(
                build_formula_validation_failed_payload(errors),
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        return Response(payload)
