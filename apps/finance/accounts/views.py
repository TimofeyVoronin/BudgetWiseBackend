from decimal import Decimal

from django.db.models import Count, Q, Sum
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiTypes,
    extend_schema,
    extend_schema_view,
)
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.common.errors import DomainConflictError
from apps.common.pagination import StandardResultsSetPagination
from apps.common.validation import validate_choice_query_param
from apps.finance.accounts.serializers import (
    ACCOUNT_BANK_OPTIONS,
    ACCOUNT_TYPE_OPTIONS,
    AccountArchiveSerializer,
    AccountHistoryRowSerializer,
    AccountMetaSerializer,
    AccountSerializer,
    AccountSummarySerializer,
    get_account_meta_payload,
)
from apps.finance.currencies.services import (
    get_user_default_currency_code,
    validate_user_currency_available,
)
from apps.finance.models import Account, AccountType, Transaction, TransactionType
from apps.finance.permissions import IsObjectOwner


ACCOUNT_STATUS_ACTIVE = "active"
ACCOUNT_STATUS_ARCHIVED = "archived"
ACCOUNT_STATUS_ALL = "all"

ACCOUNT_STATUS_VALUES = {
    ACCOUNT_STATUS_ACTIVE,
    ACCOUNT_STATUS_ARCHIVED,
    ACCOUNT_STATUS_ALL,
}


@extend_schema_view(
    list=extend_schema(
        tags=["finance-accounts"],
        summary="Получить список счетов",
        description=(
            "Возвращает счета текущего пользователя с пагинацией, поиском "
            "и фильтрацией по статусу, типу и валюте. Архивные счета не удаляются "
            "из системы и могут быть показаны через status=archived."
        ),
        parameters=[
            OpenApiParameter(
                "page",
                OpenApiTypes.INT,
                description="Номер страницы.",
            ),
            OpenApiParameter(
                "page_size",
                OpenApiTypes.INT,
                description="Размер страницы. По умолчанию 20, максимум 100.",
            ),
            OpenApiParameter(
                "status",
                OpenApiTypes.STR,
                description="Статус счёта: active, archived или all.",
            ),
            OpenApiParameter(
                "type",
                OpenApiTypes.STR,
                description=(
                    "Тип счёта: card, debit, savings, cash, credit или other."
                ),
            ),
            OpenApiParameter(
                "currency",
                OpenApiTypes.STR,
                description="ISO-код валюты, например RUB.",
            ),
            OpenApiParameter(
                "search",
                OpenApiTypes.STR,
                description="Поиск по названию счёта или банку.",
            ),
        ],
        responses={200: AccountSerializer(many=True)},
        examples=[
            OpenApiExample(
                "Список счетов",
                value={
                    "count": 1,
                    "next": None,
                    "previous": None,
                    "results": [
                        {
                            "id": 1,
                            "name": "Текущий",
                            "type": "card",
                            "type_label": "Банковская карта",
                            "typeLabel": "Банковская карта",
                            "bank_name": "Сбербанк",
                            "bankName": "Сбербанк",
                            "currency": "RUB",
                            "initial_balance": "10000.00",
                            "initialBalanceRub": "10000.00",
                            "balance": "45230.50",
                            "balanceRub": "45230.50",
                            "blocked_amount": "0.00",
                            "credit_limit": "0.00",
                            "available_balance": "45230.50",
                            "icon": "card",
                            "color": "#4F46E5",
                            "status": "active",
                            "is_default": True,
                            "isDefault": True,
                            "is_active": True,
                            "is_archived": False,
                            "operations_count": 3,
                            "operationsCount": 3,
                            "comment": "",
                        }
                    ],
                },
                response_only=True,
            )
        ],
    ),
    create=extend_schema(
        tags=["finance-accounts"],
        summary="Создать счёт",
        description=(
            "Создаёт счёт текущего пользователя. Текущий баланс при создании "
            "устанавливается равным начальному балансу. Если счёт отмечен как "
            "основной, остальные основные счета пользователя сбрасываются. "
            "Если currency не передан, используется валюта по умолчанию из настроек приложения; "
            "скрытые валюты нельзя выбирать для нового счёта."
        ),
        request=AccountSerializer,
        responses={201: AccountSerializer},
        examples=[
            OpenApiExample(
                "Создание счёта",
                value={
                    "name": "Текущий",
                    "type": "card",
                    "bankName": "Сбербанк",
                    "currency": "RUB",
                    "initialBalanceRub": "10000.00",
                    "comment": "Основная карта",
                    "isDefault": True,
                },
                request_only=True,
            )
        ],
    ),
    retrieve=extend_schema(
        tags=["finance-accounts"],
        summary="Получить счёт",
        description=(
            "Возвращает счёт текущего пользователя по ID вместе с количеством "
            "операций по этому счёту."
        ),
        responses={200: AccountSerializer},
    ),
    update=extend_schema(
        tags=["finance-accounts"],
        summary="Полностью обновить счёт",
        description=(
            "Полностью обновляет данные счёта. Текущий баланс не передаётся "
            "напрямую через этот endpoint, так как он изменяется операциями."
        ),
        request=AccountSerializer,
        responses={200: AccountSerializer},
    ),
    partial_update=extend_schema(
        tags=["finance-accounts"],
        summary="Частично обновить счёт",
        description=(
            "Частично обновляет данные счёта. Поддерживает frontend-friendly "
            "поля bankName, initialBalanceRub и isDefault."
        ),
        request=AccountSerializer,
        responses={200: AccountSerializer},
    ),
    destroy=extend_schema(
        tags=["finance-accounts"],
        summary="Удалить счёт",
        description=(
            "Удаляет счёт только если по нему нет операций. Если операции есть, "
            "возвращает 409 Conflict. Для обычного скрытия счёта используйте "
            "archive endpoint."
        ),
        responses={
            204: None,
            409: OpenApiTypes.OBJECT,
        },
    ),
)
class AccountViewSet(viewsets.ModelViewSet):
    serializer_class = AccountSerializer
    permission_classes = [IsAuthenticated, IsObjectOwner]
    pagination_class = StandardResultsSetPagination
    lookup_value_regex = r"\d+"
    http_method_names = [
        "get",
        "post",
        "put",
        "patch",
        "delete",
        "head",
        "options",
    ]

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return Account.objects.none()

        queryset = (
            Account.objects
            .filter(user=self.request.user)
            .annotate(operations_count=Count("transactions"))
        )

        if self.action != "list":
            return queryset.order_by("-is_default", "is_archived", "name", "id")

        query_params = self.request.query_params

        raw_status_value = query_params.get("status")

        if raw_status_value in (None, ""):
            status_value = ACCOUNT_STATUS_ACTIVE
        else:
            status_value = validate_choice_query_param(
                query_params,
                "status",
                ACCOUNT_STATUS_VALUES,
            )

        account_type = query_params.get("type")
        currency = query_params.get("currency")
        search = query_params.get("search")

        if status_value == ACCOUNT_STATUS_ACTIVE:
            queryset = queryset.filter(is_active=True, is_archived=False)

        if status_value == ACCOUNT_STATUS_ARCHIVED:
            queryset = queryset.filter(is_archived=True)

        if account_type:
            account_type = validate_choice_query_param(
                query_params,
                "type",
                AccountType.values,
            )
            queryset = queryset.filter(type=account_type)

        if currency:
            currency = validate_user_currency_available(
                self.request.user,
                currency,
                field_name="currency",
                require_visible=False,
            )
            queryset = queryset.filter(currency=currency)

        if search:
            search_value = search.strip()

            if len(search_value) > 100:
                raise ValidationError(
                    {
                        "search": [
                            "Параметр search не может быть длиннее 100 символов."
                        ]
                    }
                )

            if search_value:
                queryset = queryset.filter(
                    Q(name__icontains=search_value)
                    | Q(bank_name__icontains=search_value)
                )

        return queryset.order_by("-is_default", "is_archived", "name", "id")

    def perform_create(self, serializer):
        serializer.save()

    def perform_destroy(self, instance):
        operations_count = instance.transactions.count()

        if operations_count > 0:
            raise DomainConflictError(
                code="account_has_transactions",
                message="Счёт нельзя удалить, так как по нему есть операции.",
                detail={
                    "operations_count": operations_count,
                },
            )

        instance.delete()

    @extend_schema(
        tags=["finance-accounts"],
        summary="Получить сводку по счетам",
        description=(
            "Возвращает общий баланс активных неархивных счетов текущего пользователя, "
            "количество активных счетов и количество счетов в архиве. По умолчанию "
            "используется валюта по умолчанию из настроек приложения."
        ),
        parameters=[
            OpenApiParameter(
                "currency",
                OpenApiTypes.STR,
                description="ISO-код добавленной валюты пользователя. По умолчанию используется валюта из настроек приложения.",
            ),
        ],
        responses={200: AccountSummarySerializer},
        examples=[
            OpenApiExample(
                "Сводка по счетам",
                value={
                    "total_balance": "127450.50",
                    "totalBalanceRub": "127450.50",
                    "active_count": 4,
                    "archived_count": 1,
                    "currency": "RUB",
                },
                response_only=True,
            )
        ],
    )
    @action(
        detail=False,
        methods=["get"],
        url_path="summary",
    )
    def summary(self, request):
        currency = request.query_params.get("currency")
        if currency in (None, ""):
            currency = get_user_default_currency_code(request.user)
        else:
            currency = validate_user_currency_available(
                request.user,
                currency,
                field_name="currency",
                require_visible=False,
            )

        total_balance = (
            Account.objects
            .filter(
                user=request.user,
                currency=currency,
                is_active=True,
                is_archived=False,
            )
            .aggregate(total=Sum("balance"))
            .get("total")
            or Decimal("0.00")
        )
        active_count = Account.objects.filter(
            user=request.user,
            is_active=True,
            is_archived=False,
        ).count()
        archived_count = Account.objects.filter(
            user=request.user,
            is_archived=True,
        ).count()

        data = {
            "total_balance": total_balance,
            "totalBalanceRub": total_balance,
            "active_count": active_count,
            "archived_count": archived_count,
            "currency": currency,
        }

        serializer = AccountSummarySerializer(data)
        return Response(serializer.data)

    @extend_schema(
        tags=["finance-accounts"],
        summary="Получить справочники для формы счёта",
        description=(
            "Возвращает типы счетов, популярные банки, основную валюту и видимые "
            "валюты пользователя для формы создания или редактирования счёта."
        ),
        responses={200: AccountMetaSerializer},
        examples=[
            OpenApiExample(
                "Справочники счетов",
                value={
                    "types": ACCOUNT_TYPE_OPTIONS,
                    "banks": ACCOUNT_BANK_OPTIONS,
                    "currencies": [
                        {"title": "RUB · Российский рубль", "value": "RUB"},
                        {"title": "USD · Доллар США", "value": "USD"},
                    ],
                    "primaryCurrencyCode": "RUB",
                        "defaultCurrencyCode": "RUB",
                },
                response_only=True,
            )
        ],
    )
    @action(
        detail=False,
        methods=["get"],
        url_path="meta",
    )
    def meta(self, request):
        serializer = AccountMetaSerializer(get_account_meta_payload(request.user))
        return Response(serializer.data)

    @extend_schema(
        tags=["finance-accounts"],
        summary="Архивировать или восстановить счёт",
        description=(
            "Переводит счёт в архив или восстанавливает его. Архивный счёт "
            "не участвует в общем балансе и скрывается из списка активных счетов, "
            "но история операций по нему сохраняется."
        ),
        request=AccountArchiveSerializer,
        responses={200: AccountSerializer},
        examples=[
            OpenApiExample(
                "Отправить счёт в архив",
                value={
                    "archived": True,
                },
                request_only=True,
            ),
            OpenApiExample(
                "Восстановить счёт",
                value={
                    "archived": False,
                },
                request_only=True,
            ),
        ],
    )
    @action(
        detail=True,
        methods=["patch"],
        url_path="archive",
    )
    def archive(self, request, pk=None):
        account = self.get_object()

        serializer = AccountArchiveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        archived = serializer.validated_data["archived"]

        account.is_archived = archived
        account.is_active = not archived

        update_fields = ["is_archived", "is_active", "updated_at"]

        if archived and account.is_default:
            account.is_default = False
            update_fields.append("is_default")

        account.save(update_fields=update_fields)

        response_serializer = self.get_serializer(account)
        return Response(response_serializer.data)

    @extend_schema(
        tags=["finance-accounts"],
        summary="Получить историю операций по счёту",
        description=(
            "Возвращает последние операции текущего пользователя по выбранному счёту. "
            "Используется в карточке детального просмотра счёта."
        ),
        parameters=[
            OpenApiParameter(
                "page",
                OpenApiTypes.INT,
                description="Номер страницы.",
            ),
            OpenApiParameter(
                "page_size",
                OpenApiTypes.INT,
                description="Размер страницы. По умолчанию 20, максимум 100.",
            ),
        ],
        responses={200: AccountHistoryRowSerializer(many=True)},
    )
    @action(
        detail=True,
        methods=["get"],
        url_path="history",
    )
    def history(self, request, pk=None):
        account = self.get_object()

        queryset = (
            Transaction.objects
            .filter(
                user=request.user,
                account=account,
            )
            .select_related("category")
            .order_by("-operation_date", "-created_at", "-id")
        )

        page = self.paginate_queryset(queryset)

        if page is not None:
            data = [
                self._build_history_row(transaction)
                for transaction in page
            ]
            serializer = AccountHistoryRowSerializer(data, many=True)
            return self.get_paginated_response(serializer.data)

        data = [
            self._build_history_row(transaction)
            for transaction in queryset
        ]
        serializer = AccountHistoryRowSerializer(data, many=True)
        return Response(serializer.data)

    def _build_history_row(self, transaction: Transaction) -> dict:
        amount = abs(transaction.amount)

        if transaction.type == TransactionType.EXPENSE:
            signed_amount = -amount
        else:
            signed_amount = amount

        return {
            "id": transaction.id,
            "date": transaction.operation_date,
            "description": transaction.description,
            "category_name": transaction.category.name,
            "amount": amount,
            "signed_amount": signed_amount,
            "type": transaction.type,
        }
