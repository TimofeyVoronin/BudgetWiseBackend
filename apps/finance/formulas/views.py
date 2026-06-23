from __future__ import annotations

from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.finance.formulas.constants import FORMULA_IDE_TAG
from apps.finance.formulas.serializers import (
    FormulaIdeMetaResponseSerializer,
    FormulaIdeStateResponseSerializer,
    FormulaIdeStateSaveResponseSerializer,
    FormulaIdeStateUpdateSerializer,
)
from apps.finance.formulas.services import (
    get_formula_ide_meta,
    get_formula_ide_state,
    save_formula_ide_state,
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
