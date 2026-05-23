from __future__ import annotations

from decimal import Decimal

from django.db import transaction
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

from apps.common.domain_errors import DomainConflictError
from apps.finance.currencies.services import (
    CATALOG_BY_CODE,
    DEFAULT_CURRENCY_CODE,
    DEFAULT_RATE_BY_CODE,
    build_catalog_items,
    build_currencies_summary,
    filter_user_currencies_queryset,
    get_currency_usage_count,
    get_user_currencies,
    normalize_currency_code,
    parse_bool,
    set_primary_currency,
    validate_custom_currency_payload,
)
from apps.finance.currencies.serializers import (
    AddCurrencyFromCatalogSerializer,
    CheckCurrencyCodeResponseSerializer,
    CreateCustomCurrencySerializer,
    CurrenciesCatalogResponseSerializer,
    CurrenciesListResponseSerializer,
    CurrenciesSelectOptionsResponseSerializer,
    CurrencyListRowSerializer,
    DeleteCurrencyConflictResponseSerializer,
    DeleteCurrencyResponseSerializer,
    SetCurrencyVisibilitySerializer,
    UpdateCurrencySerializer,
    ValidateCustomCurrencyResponseSerializer,
    ValidateCustomCurrencySerializer,
    build_select_options_payload,
)
from apps.finance.models import Currency, UserCurrency
from apps.finance.currencies.rates import refresh_user_currency_rates
from apps.finance.permissions import IsObjectOwner


CURRENCY_LIST_PARAMETERS = [
    OpenApiParameter("search", OpenApiTypes.STR, description="Поиск по коду, названию или символу валюты."),
    OpenApiParameter("isVisible", OpenApiTypes.BOOL, description="Фильтр видимости валюты в интерфейсе."),
    OpenApiParameter("isCustom", OpenApiTypes.BOOL, description="Фильтр пользовательских валют."),
    OpenApiParameter("onlyUsed", OpenApiTypes.BOOL, description="true - вернуть только валюты, используемые в данных пользователя."),
    OpenApiParameter("ordering", OpenApiTypes.STR, description="Сортировка: code, name, rateToPrimary, isPrimary, isVisible, isCustom, createdAt."),
]


@extend_schema_view(
    list=extend_schema(
        tags=["finance-currencies"],
        summary="Получить список валют пользователя",
        description=(
            "Возвращает валюты, доступные пользователю, включая системные и "
            "пользовательские валюты. Ответ содержит список и сводку для "
            "страницы управления валютами. Основная валюта может быть только одна."
        ),
        parameters=CURRENCY_LIST_PARAMETERS,
        responses={200: CurrenciesListResponseSerializer},
        examples=[
            OpenApiExample(
                "Список валют",
                value={
                    "items": [
                        {
                            "id": 1,
                            "code": "RUB",
                            "name": "Российский рубль",
                            "symbol": "₽",
                            "rateToPrimary": 1.0,
                            "isPrimary": True,
                            "isVisible": True,
                            "isCustom": False,
                            "operationsCount": 3,
                            "flagIcon": "rub",
                        }
                    ],
                    "summary": {
                        "totalCount": 10,
                        "primaryCode": "RUB",
                        "hiddenCount": 2,
                    },
                },
                response_only=True,
            )
        ],
    ),
    retrieve=extend_schema(
        tags=["finance-currencies"],
        summary="Получить валюту пользователя",
        responses={200: CurrencyListRowSerializer, 404: OpenApiTypes.OBJECT},
    ),
    create=extend_schema(
        tags=["finance-currencies"],
        summary="Создать пользовательскую валюту",
        description="Alias для POST /currencies/custom/. Создаёт пользовательскую валюту текущего пользователя.",
        request=CreateCustomCurrencySerializer,
        responses={201: CurrencyListRowSerializer, 400: OpenApiTypes.OBJECT},
    ),
    partial_update=extend_schema(
        tags=["finance-currencies"],
        summary="Обновить пользовательскую валюту",
        description=(
            "Обновляет название, символ и видимость пользовательской валюты. "
            "Системные валюты можно только скрывать или делать основными через специальные actions."
        ),
        request=UpdateCurrencySerializer,
        responses={200: CurrencyListRowSerializer, 400: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    ),
    update=extend_schema(
        tags=["finance-currencies"],
        summary="Полностью обновить пользовательскую валюту",
        request=UpdateCurrencySerializer,
        responses={200: CurrencyListRowSerializer, 400: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    ),
    destroy=extend_schema(
        tags=["finance-currencies"],
        summary="Удалить пользовательскую валюту",
        description=(
            "Удаляет только пользовательскую валюту, которая не является основной и не используется "
            "в счетах, бюджетах, операциях или шаблонах. Системную валюту можно скрыть, но нельзя удалить."
        ),
        responses={
            200: DeleteCurrencyResponseSerializer,
            409: DeleteCurrencyConflictResponseSerializer,
            404: OpenApiTypes.OBJECT,
        },
    ),
)
class CurrencyViewSet(viewsets.ModelViewSet):
    serializer_class = CurrencyListRowSerializer
    permission_classes = [IsAuthenticated, IsObjectOwner]
    lookup_value_regex = r"\d+"
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return UserCurrency.objects.none()

        queryset = get_user_currencies(self.request.user)

        if self.action == "list":
            return filter_user_currencies_queryset(queryset, self.request)

        return queryset

    def list(self, request, *args, **kwargs):
        get_user_currencies(request.user)
        refresh_user_currency_rates(request.user)
        queryset = filter_user_currencies_queryset(
            get_user_currencies(request.user),
            request,
        )
        serializer = self.get_serializer(queryset, many=True)

        return Response(
            {
                "items": serializer.data,
                "summary": build_currencies_summary(queryset),
            }
        )

    def create(self, request, *args, **kwargs):
        serializer = CreateCustomCurrencySerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        user_currency = self._create_custom_currency(serializer.validated_data)
        return Response(self.get_serializer(user_currency).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = UpdateCurrencySerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        self._update_currency(instance, serializer.validated_data)
        instance.refresh_from_db()
        return Response(self.get_serializer(instance).data)

    def update(self, request, *args, **kwargs):
        return self.partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self._ensure_can_delete(instance)
        currency_id = str(instance.pk)
        instance.delete()
        return Response({"deleted": True, "id": currency_id})

    @extend_schema(
        tags=["finance-currencies"],
        summary="Получить видимые валюты для select-полей",
        responses={200: CurrenciesSelectOptionsResponseSerializer},
    )
    @action(detail=False, methods=["get"], url_path="select-options")
    def select_options(self, request):
        return Response(build_select_options_payload(request.user))

    @extend_schema(
        tags=["finance-currencies"],
        summary="Получить каталог валют",
        parameters=[
            OpenApiParameter("search", OpenApiTypes.STR, description="Поиск по коду, названию или символу."),
            OpenApiParameter("excludeAdded", OpenApiTypes.BOOL, description="Исключить валюты, уже добавленные пользователю."),
        ],
        responses={200: CurrenciesCatalogResponseSerializer},
    )
    @action(detail=False, methods=["get"], url_path="catalog")
    def catalog(self, request):
        exclude_added = parse_bool(
            request.query_params.get("excludeAdded", request.query_params.get("exclude_added")),
            default=False,
        )
        items = build_catalog_items(
            request.user,
            search=request.query_params.get("search", ""),
            exclude_added=exclude_added,
        )
        return Response({"items": items})

    @extend_schema(
        tags=["finance-currencies"],
        summary="Добавить валюту из каталога",
        request=AddCurrencyFromCatalogSerializer,
        responses={201: CurrencyListRowSerializer, 400: OpenApiTypes.OBJECT},
    )
    @action(detail=False, methods=["post"], url_path="from-catalog")
    def from_catalog(self, request):
        serializer = AddCurrencyFromCatalogSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        code = serializer.validated_data["code"]
        item = CATALOG_BY_CODE[code]

        currency, _ = Currency.objects.update_or_create(
            code=code,
            defaults={
                "name": item["name"],
                "symbol": item["symbol"],
                "flag_icon": item["flagIcon"],
                "decimal_places": item["decimalPlaces"],
                "is_system": True,
                "is_popular": bool(item.get("popular", False)),
            },
        )
        user_currency, created = UserCurrency.objects.update_or_create(
            user=request.user,
            currency=currency,
            defaults={
                "is_visible": True,
                "is_custom": False,
                "rate_to_primary": DEFAULT_RATE_BY_CODE.get(code, Decimal("1.00000000")),
            },
        )
        refresh_user_currency_rates(request.user, force=True)
        user_currency.refresh_from_db()
        return Response(
            self.get_serializer(user_currency).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @extend_schema(
        tags=["finance-currencies"],
        summary="Создать пользовательскую валюту",
        request=CreateCustomCurrencySerializer,
        responses={201: CurrencyListRowSerializer, 400: OpenApiTypes.OBJECT},
    )
    @action(detail=False, methods=["post"], url_path="custom")
    def custom(self, request):
        serializer = CreateCustomCurrencySerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        user_currency = self._create_custom_currency(serializer.validated_data)
        return Response(self.get_serializer(user_currency).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        tags=["finance-currencies"],
        summary="Проверить код пользовательской валюты",
        parameters=[
            OpenApiParameter("code", OpenApiTypes.STR, description="Код валюты."),
            OpenApiParameter("excludeId", OpenApiTypes.INT, description="ID валюты пользователя при редактировании."),
        ],
        responses={200: CheckCurrencyCodeResponseSerializer},
    )
    @action(detail=False, methods=["get"], url_path="check-code")
    def check_code(self, request):
        code = normalize_currency_code(request.query_params.get("code", ""))
        exclude_id = request.query_params.get("excludeId") or request.query_params.get("exclude_id")
        validation = validate_custom_currency_payload(
            code=code,
            name="Валюта",
            symbol="¤",
            exclude_id=exclude_id,
            user=request.user,
        )
        code_error = validation["fieldErrors"].get("code")
        if code_error:
            return Response({"available": False, "message": code_error})
        return Response({"available": True})

    @extend_schema(
        tags=["finance-currencies"],
        summary="Проверить форму пользовательской валюты",
        request=ValidateCustomCurrencySerializer,
        responses={200: ValidateCustomCurrencyResponseSerializer},
    )
    @action(detail=False, methods=["post"], url_path="validate-custom")
    def validate_custom(self, request):
        serializer = ValidateCustomCurrencySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validation = validate_custom_currency_payload(
            code=serializer.validated_data.get("code"),
            name=serializer.validated_data.get("name"),
            symbol=serializer.validated_data.get("symbol"),
            exclude_id=serializer.validated_data.get("excludeId"),
            user=request.user,
        )
        return Response(
            {
                "ok": not bool(validation["fieldErrors"]),
                "fieldErrors": validation["fieldErrors"],
            }
        )

    @extend_schema(
        tags=["finance-currencies"],
        summary="Сделать валюту основной",
        responses={200: CurrenciesListResponseSerializer, 404: OpenApiTypes.OBJECT},
    )
    @action(detail=True, methods=["patch"], url_path="set-primary")
    def set_primary(self, request, pk=None):
        user_currency = self.get_object()
        set_primary_currency(request.user, user_currency)
        queryset = get_user_currencies(request.user)
        return Response(
            {
                "items": self.get_serializer(queryset, many=True).data,
                "summary": build_currencies_summary(queryset),
            }
        )

    @extend_schema(
        tags=["finance-currencies"],
        summary="Изменить видимость валюты",
        request=SetCurrencyVisibilitySerializer,
        responses={200: CurrencyListRowSerializer, 400: OpenApiTypes.OBJECT, 409: DeleteCurrencyConflictResponseSerializer},
    )
    @action(detail=True, methods=["patch"], url_path="visibility")
    def visibility(self, request, pk=None):
        user_currency = self.get_object()
        serializer = SetCurrencyVisibilitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        is_visible = serializer.validated_data["isVisible"]

        if user_currency.is_primary and not is_visible:
            raise DomainConflictError(
                code="IS_PRIMARY",
                message="Основную валюту нельзя скрыть.",
                field_errors={"isVisible": ["Основную валюту нельзя скрыть."]},
            )

        user_currency.is_visible = is_visible
        user_currency.save(update_fields=["is_visible", "updated_at"])
        return Response(self.get_serializer(user_currency).data)

    def _create_custom_currency(self, attrs: dict) -> UserCurrency:
        code = normalize_currency_code(attrs["code"])
        if code in CATALOG_BY_CODE:
            raise ValidationError({"code": ["Эта валюта уже есть в системном каталоге. Добавьте её из каталога."]})

        with transaction.atomic():
            currency, _ = Currency.objects.get_or_create(
                code=code,
                defaults={
                    "name": attrs["name"],
                    "symbol": attrs["symbol"],
                    "flag_icon": code.lower(),
                    "decimal_places": 2,
                    "is_system": False,
                    "is_popular": False,
                },
            )
            user_currency = UserCurrency.objects.create(
                user=self.request.user,
                currency=currency,
                custom_name=attrs["name"],
                custom_symbol=attrs["symbol"],
                is_visible=attrs.get("isVisible", True),
                is_custom=True,
                rate_to_primary=Decimal("1.00000000"),
            )
        return user_currency

    def _update_currency(self, instance: UserCurrency, attrs: dict) -> None:
        if not instance.is_custom and ("name" in attrs or "symbol" in attrs):
            raise ValidationError(
                {
                    "general": [
                        "Системную валюту нельзя редактировать. Можно изменить только её видимость."
                    ]
                }
            )

        if instance.is_primary and attrs.get("isVisible") is False:
            raise DomainConflictError(
                code="IS_PRIMARY",
                message="Основную валюту нельзя скрыть.",
                field_errors={"isVisible": ["Основную валюту нельзя скрыть."]},
            )

        update_fields = []
        if "name" in attrs:
            instance.custom_name = attrs["name"]
            update_fields.append("custom_name")
        if "symbol" in attrs:
            instance.custom_symbol = attrs["symbol"]
            update_fields.append("custom_symbol")
        if "isVisible" in attrs:
            instance.is_visible = attrs["isVisible"]
            update_fields.append("is_visible")

        if update_fields:
            update_fields.append("updated_at")
            instance.save(update_fields=update_fields)

    def _ensure_can_delete(self, instance: UserCurrency) -> None:
        if instance.is_primary:
            raise DomainConflictError(
                code="IS_PRIMARY",
                message="Основную валюту нельзя удалить.",
                detail={"canHide": False},
            )

        usage_count = get_currency_usage_count(instance.user, instance.code)
        if usage_count > 0:
            raise DomainConflictError(
                code="HAS_OPERATIONS",
                message="Валюта используется в данных пользователя. Её можно скрыть, но нельзя удалить.",
                detail={"operationsCount": usage_count, "canHide": True},
            )

        if not instance.is_custom:
            raise DomainConflictError(
                code="VALIDATION_FAILED",
                message="Системную валюту нельзя удалить. Её можно скрыть в интерфейсе.",
                detail={"operationsCount": usage_count, "canHide": True},
            )
