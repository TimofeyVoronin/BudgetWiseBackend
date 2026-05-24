from __future__ import annotations

from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.finance.models import (
    Receipt,
    ReceiptAuditAction,
    ReceiptAuditStatus,
    ReceiptStatus,
)
from apps.finance.receipts.audit import log_receipt_audit_event
from apps.finance.receipts.duplicates import check_receipt_duplicate, register_receipt_from_qr
from apps.finance.receipts.provider import ReceiptProviderError, get_receipt_provider_client
from apps.finance.receipts.qr import ReceiptQRParseError, parse_receipt_qr
from apps.finance.receipts.serializers import (
    CreateReceiptTransactionsResponseSerializer,
    CreateReceiptTransactionsSerializer,
    ReceiptQRImportQuerySerializer,
    ReceiptQRImportResponseSerializer,
    build_receipt_qr_import_response,
    build_receipt_transactions_response,
)
from apps.finance.receipts.transactions import (
    ReceiptTransactionCreationError,
    create_transactions_from_receipt,
)


class ReceiptImportByQRView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["finance-receipts"],
        operation_id="finance_receipts_qr_retrieve",
        summary="Получить чек по QR-коду",
        description=(
            "Принимает исходную строку QR-кода чека, проверяет её, защищает импорт от дублей "
            "и возвращает зарегистрированный чек. Если fetchProvider=true, backend дополнительно "
            "пытается получить расширенные данные у внешнего сервиса проверки чеков. Даже если "
            "провайдер временно недоступен или не настроен, корректный QR-код сохраняется со статусом parsed, "
            "а frontend получает понятный ответ с providerStatus=failed."
        ),
        parameters=[
            OpenApiParameter(
                name="qrRaw",
                type=str,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Исходная строка QR-кода чека. Значение нужно передавать URL-encoded.",
            ),
            OpenApiParameter(
                name="fetchProvider",
                type=bool,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Получать ли расширенные данные чека у внешнего провайдера. По умолчанию true.",
            ),
        ],
        responses={
            200: ReceiptQRImportResponseSerializer,
            400: {"$ref": "#/components/schemas/ApiErrorResponse"},
            401: {"$ref": "#/components/schemas/ApiErrorResponse"},
        },
        examples=[
            OpenApiExample(
                "QR-код без запроса к провайдеру",
                value={
                    "qrRaw": "t=20240522T1421&s=270.00&fn=9280440300891234&i=12345&fp=987654321&n=1",
                    "fetchProvider": False,
                },
                request_only=True,
            ),
            OpenApiExample(
                "Ответ при успешной регистрации",
                value={
                    "receipt": {
                        "id": 1,
                        "status": "parsed",
                        "store_name": "",
                        "seller_inn": "",
                        "receipt_datetime": "2024-05-22T14:21:00+07:00",
                        "total_amount": "270.00",
                        "fiscal_drive_number": "9280440300891234",
                        "fiscal_document_number": "12345",
                        "fiscal_sign": "987654321",
                        "transactionsCount": 0,
                        "items": [],
                    },
                    "created": True,
                    "isDuplicate": False,
                    "providerStatus": "skipped",
                    "providerError": None,
                },
                response_only=True,
            ),
        ],
    )
    def get(self, request):
        serializer = ReceiptQRImportQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        qr_raw = serializer.validated_data["qrRaw"]
        fetch_provider = serializer.validated_data.get("fetchProvider", True)

        try:
            qr_data = parse_receipt_qr(qr_raw)
        except ReceiptQRParseError as exc:
            raise ValidationError(exc.field_errors or {"qrRaw": exc.message}, code=exc.code) from exc

        duplicate_check = check_receipt_duplicate(request.user, qr_data)
        if duplicate_check.existing_receipt is not None:
            result = register_receipt_from_qr(user=request.user, qr_data=qr_data)
            response_data = build_receipt_qr_import_response(
                receipt=result.receipt,
                created=result.created,
                is_duplicate=result.is_duplicate,
                provider_status="skipped",
                provider_error=None,
            )
            return Response(response_data, status=status.HTTP_200_OK)

        provider_details = None
        provider_status = "skipped"
        provider_error = None

        if fetch_provider:
            try:
                provider_details = get_receipt_provider_client().fetch_by_qr(qr_data)
                provider_status = "fetched"
            except ReceiptProviderError as exc:
                provider_status = "failed"
                provider_error = {
                    "code": exc.code,
                    "message": exc.message,
                    "fieldErrors": exc.field_errors,
                }

        result = register_receipt_from_qr(
            user=request.user,
            qr_data=qr_data,
            provider_details=provider_details,
            status=ReceiptStatus.FETCHED if provider_details is not None else ReceiptStatus.PARSED,
        )

        if provider_error is not None:
            log_receipt_audit_event(
                receipt=result.receipt,
                action=ReceiptAuditAction.PROVIDER_FETCH_FAILED,
                status=ReceiptAuditStatus.ERROR,
                message=provider_error["message"],
                metadata={
                    "code": provider_error["code"],
                    "fieldErrors": provider_error["fieldErrors"],
                },
            )

        response_data = build_receipt_qr_import_response(
            receipt=result.receipt,
            created=result.created,
            is_duplicate=result.is_duplicate,
            provider_status=provider_status,
            provider_error=provider_error,
        )
        return Response(response_data, status=status.HTTP_200_OK)


class ReceiptCreateTransactionsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["finance-receipts"],
        summary="Создать операции из чека",
        description=(
            "Создаёт одну или несколько финансовых операций из импортированного чека. "
            "В режиме single создаётся одна операция на всю сумму чека. "
            "В режиме by_items создаются отдельные операции по выбранным позициям. "
            "Можно передать ID уже сохранённых позиций чека или ручные позиции с name/quantity/price/amount. "
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
                "Операции по сохранённым позициям",
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
            OpenApiExample(
                "Операции по ручным позициям",
                value={
                    "accountId": 1,
                    "mode": "by_items",
                    "items": [
                        {"name": "Молоко", "quantity": "1.000", "price": "90.00", "amount": "90.00", "categoryId": 2},
                        {"name": "Хлеб", "quantity": "1.000", "price": "60.00", "amount": "60.00", "categoryId": 2},
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
