from __future__ import annotations

from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.finance.models import Receipt
from apps.finance.receipt_transaction_serializers import (
    CreateReceiptTransactionsResponseSerializer,
    CreateReceiptTransactionsSerializer,
    build_receipt_transactions_response,
)
from apps.finance.receipt_transactions import (
    ReceiptTransactionCreationError,
    create_transactions_from_receipt,
)


class ReceiptCreateTransactionsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["finance-receipts"],
        summary="Создать операции из чека",
        description=(
            "Создаёт одну или несколько финансовых операций из импортированного чека. "
            "В режиме single создаётся одна операция на всю сумму чека. "
            "В режиме by_items создаются отдельные операции по выбранным позициям. "
            "После успешного создания чек получает статус imported, повторное создание операций запрещено."
        ),
        request=CreateReceiptTransactionsSerializer,
        responses={
            201: CreateReceiptTransactionsResponseSerializer,
            400: {"$ref": "#/components/schemas/ApiErrorResponse"},
            404: {"$ref": "#/components/schemas/ApiErrorResponse"},
        },
        examples=[
            OpenApiExample(
                "Одна операция на весь чек",
                value={
                    "accountId": 1,
                    "mode": "single",
                    "categoryId": 2,
                    "description": "Пятёрочка · чек от 22.05.2026",
                },
                request_only=True,
            ),
            OpenApiExample(
                "Операции по позициям",
                value={
                    "accountId": 1,
                    "mode": "by_items",
                    "items": [
                        {"receiptItemId": 10, "categoryId": 2},
                        {"receiptItemId": 11, "categoryId": 3},
                    ],
                },
                request_only=True,
            ),
        ],
    )
    def post(self, request, receipt_id: int):
        try:
            receipt = (
                Receipt.objects
                .select_related("user")
                .prefetch_related("items__suggested_category")
                .get(pk=receipt_id, user=request.user)
            )
        except Receipt.DoesNotExist as exc:
            raise NotFound("Чек не найден.") from exc

        serializer = CreateReceiptTransactionsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            result = create_transactions_from_receipt(
                user=request.user,
                receipt=receipt,
                account=serializer.get_account(request.user),
                mode=serializer.validated_data["mode"],
                category=serializer.get_category(request.user),
                items=serializer.get_item_inputs(),
                description=serializer.validated_data.get("description", ""),
            )
        except ReceiptTransactionCreationError as exc:
            raise ValidationError(exc.field_errors or {"detail": exc.message}, code=exc.code) from exc

        response_data = build_receipt_transactions_response(
            receipt=result.receipt,
            mode=result.mode,
            transactions=result.transactions,
        )
        return Response(response_data, status=status.HTTP_201_CREATED)
