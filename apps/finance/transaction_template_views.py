from __future__ import annotations

from django.core.paginator import EmptyPage, Paginator
from django.db import transaction as db_transaction
from django.db.models import F
from django.utils import timezone
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

from apps.finance.accounting import create_transaction_with_balance_update
from apps.finance.models import (
    TransactionTemplate,
    TransactionTemplateStatus,
)
from apps.finance.permissions import IsObjectOwner
from apps.finance.transaction_serializers import TransactionSerializer
from apps.finance.transaction_template_serializers import (
    TransactionTemplateActionResponseSerializer,
    TransactionTemplateApplyDraftSerializer,
    TransactionTemplateApplyResponseSerializer,
    TransactionTemplateApplySerializer,
    TransactionTemplateCheckNameResponseSerializer,
    TransactionTemplateDeleteResponseSerializer,
    TransactionTemplateListResponseSerializer,
    TransactionTemplateMetaResponseSerializer,
    TransactionTemplateSerializer,
    TransactionTemplateValidateResponseSerializer,
    TransactionTemplateValidateSerializer,
    build_apply_draft_payload,
    serializer_errors_to_field_errors,
    validate_transaction_template_form,
)
from apps.finance.transaction_templates import (
    DEFAULT_TEMPLATE_PAGE_SIZE,
    MAX_TEMPLATE_PAGE_SIZE,
    build_transaction_templates_summary,
    filter_transaction_templates_queryset,
    get_accessible_transaction_templates,
    get_positive_int_query_param,
    get_transaction_templates_meta_payload,
    transaction_template_duplicate_exists,
)


TEMPLATE_LIST_PARAMETERS = [
    OpenApiParameter("search", OpenApiTypes.STR, description="Поиск по названию, примечанию, категории, счёту или тегу."),
    OpenApiParameter("status", OpenApiTypes.STR, description="Статус шаблона: active или archived."),
    OpenApiParameter("categories", OpenApiTypes.STR, description="ID категорий через запятую."),
    OpenApiParameter("accounts", OpenApiTypes.STR, description="ID счетов через запятую."),
    OpenApiParameter("tagIds", OpenApiTypes.STR, description="ID тегов через запятую."),
    OpenApiParameter("tagQuery", OpenApiTypes.STR, description="Поиск по названию тега."),
    OpenApiParameter("sortBy", OpenApiTypes.STR, description="Поле сортировки: name, useCount, lastUsedAt, createdAt, updatedAt."),
    OpenApiParameter("sortOrder", OpenApiTypes.STR, description="Направление сортировки: asc или desc."),
    OpenApiParameter("ordering", OpenApiTypes.STR, description="Backend-сортировка, например -useCount,name."),
    OpenApiParameter("page", OpenApiTypes.INT, description="Номер страницы."),
    OpenApiParameter("perPage", OpenApiTypes.INT, description="Размер страницы. Alias: page_size, limit."),
]


@extend_schema_view(
    list=extend_schema(
        tags=["finance-transaction-templates"],
        summary="Получить список шаблонов операций",
        description=(
            "Возвращает сохранённые шаблоны операций текущего пользователя. "
            "Ответ содержит items, summary и pagination для страницы шаблонов."
        ),
        parameters=TEMPLATE_LIST_PARAMETERS,
        responses={200: TransactionTemplateListResponseSerializer, 400: OpenApiTypes.OBJECT},
        examples=[
            OpenApiExample(
                "Список шаблонов",
                value={
                    "items": [
                        {
                            "id": 1,
                            "name": "Обед в офисе",
                            "kind": "expense",
                            "amountRub": 450.0,
                            "currency": "RUB",
                            "categoryId": 2,
                            "categoryName": "Продукты",
                            "categoryIcon": "cart",
                            "categoryColor": "#66BB6A",
                            "accountId": 1,
                            "accountName": "Основная карта",
                            "tags": [
                                {
                                    "id": 3,
                                    "name": "обед",
                                    "groupId": None,
                                    "groupName": "Без группы",
                                    "color": "#66BB6A",
                                    "icon": "cart",
                                    "isVisible": True,
                                }
                            ],
                            "note": "Рабочий обед",
                            "status": "active",
                            "isDefault": False,
                            "useCount": 5,
                            "lastUsedAt": "2026-05-21T16:00:00+0300",
                            "icon": "cart",
                            "iconTone": "warning",
                        }
                    ],
                    "summary": {
                        "totalCount": 1,
                        "frequentCount": 1,
                        "lastUsedLabel": "Сегодня",
                    },
                    "pagination": {
                        "page": 1,
                        "perPage": 20,
                        "totalItems": 1,
                        "totalPages": 1,
                    },
                },
                response_only=True,
            )
        ],
    ),
    create=extend_schema(
        tags=["finance-transaction-templates"],
        summary="Создать шаблон операции",
        description=(
            "Создаёт шаблон операции. Счёт, категория и теги должны принадлежать "
            "текущему пользователю, категория должна соответствовать типу шаблона."
        ),
        request=TransactionTemplateSerializer,
        responses={201: TransactionTemplateSerializer, 400: OpenApiTypes.OBJECT},
        examples=[
            OpenApiExample(
                "Создание шаблона",
                value={
                    "name": "Кофе",
                    "kind": "expense",
                    "amountRub": 180.0,
                    "accountId": 1,
                    "categoryId": 2,
                    "tagIds": [3],
                    "note": "Кофе перед работой",
                },
                request_only=True,
            )
        ],
    ),
    retrieve=extend_schema(
        tags=["finance-transaction-templates"],
        summary="Получить шаблон операции",
        responses={200: TransactionTemplateSerializer, 404: OpenApiTypes.OBJECT},
    ),
    partial_update=extend_schema(
        tags=["finance-transaction-templates"],
        summary="Обновить шаблон операции",
        request=TransactionTemplateSerializer,
        responses={200: TransactionTemplateSerializer, 400: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    ),
    update=extend_schema(
        tags=["finance-transaction-templates"],
        summary="Полностью обновить шаблон операции",
        request=TransactionTemplateSerializer,
        responses={200: TransactionTemplateSerializer, 400: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    ),
    destroy=extend_schema(
        tags=["finance-transaction-templates"],
        summary="Удалить шаблон операции",
        responses={200: TransactionTemplateDeleteResponseSerializer, 404: OpenApiTypes.OBJECT},
    ),
)
class TransactionTemplateViewSet(viewsets.ModelViewSet):
    serializer_class = TransactionTemplateSerializer
    permission_classes = [IsAuthenticated, IsObjectOwner]
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
        queryset = get_accessible_transaction_templates(self.request.user)

        if self.action == "list":
            return filter_transaction_templates_queryset(queryset, self.request)

        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        total_items = queryset.count()
        page = get_positive_int_query_param(request.query_params, "page", default=1)
        per_page = get_positive_int_query_param(
            request.query_params,
            "perPage",
            "page_size",
            "limit",
            default=DEFAULT_TEMPLATE_PAGE_SIZE,
        )
        per_page = min(per_page, MAX_TEMPLATE_PAGE_SIZE)
        paginator = Paginator(queryset, per_page)

        try:
            page_obj = paginator.page(page)
        except EmptyPage as exc:
            raise ValidationError({"page": ["Страница находится вне диапазона."]}) from exc

        serializer = self.get_serializer(page_obj.object_list, many=True)

        return Response(
            {
                "items": serializer.data,
                "summary": build_transaction_templates_summary(queryset),
                "pagination": {
                    "page": page,
                    "perPage": per_page,
                    "totalItems": total_items,
                    "totalPages": paginator.num_pages or 1,
                },
            }
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        template_id = instance.pk
        instance.delete()
        return Response({"deleted": True, "id": template_id})

    @extend_schema(
        tags=["finance-transaction-templates"],
        summary="Архивировать шаблон операции",
        responses={200: TransactionTemplateActionResponseSerializer, 404: OpenApiTypes.OBJECT},
    )
    @action(detail=True, methods=["post"], url_path="archive")
    def archive(self, request, pk=None):
        template = self.get_object()
        template.status = TransactionTemplateStatus.ARCHIVED
        template.is_default = False
        template.save(update_fields=["status", "is_default", "updated_at"])
        return Response({"template": self.get_serializer(template).data})

    @extend_schema(
        tags=["finance-transaction-templates"],
        summary="Восстановить шаблон операции из архива",
        responses={200: TransactionTemplateActionResponseSerializer, 400: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    @action(detail=True, methods=["post"], url_path="restore")
    def restore(self, request, pk=None):
        template = self.get_object()

        if transaction_template_duplicate_exists(
            user=request.user,
            name=template.name,
            exclude_id=template.pk,
        ):
            raise ValidationError(
                {"name": ["Активный шаблон с таким названием уже существует."]}
            )

        template.status = TransactionTemplateStatus.ACTIVE
        template.save(update_fields=["status", "updated_at"])
        return Response({"template": self.get_serializer(template).data})

    @extend_schema(
        tags=["finance-transaction-templates"],
        summary="Дублировать шаблон операции",
        description="Создаёт активную копию шаблона с новым названием.",
        responses={201: TransactionTemplateSerializer, 400: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    @action(detail=True, methods=["post"], url_path="duplicate")
    def duplicate(self, request, pk=None):
        source = self.get_object()
        base_name = f"{source.name} копия"
        name = base_name
        index = 2

        while transaction_template_duplicate_exists(user=request.user, name=name):
            name = f"{base_name} {index}"
            index += 1

        duplicate = TransactionTemplate.objects.create(
            user=request.user,
            name=name,
            kind=source.kind,
            amount=source.amount,
            currency=source.currency,
            account=source.account,
            category=source.category,
            note=source.note,
            status=TransactionTemplateStatus.ACTIVE,
            is_default=False,
        )
        duplicate.tags.set(source.tags.all())

        return Response(
            self.get_serializer(duplicate).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        tags=["finance-transaction-templates"],
        summary="Получить черновик операции по шаблону",
        description=(
            "Возвращает данные, которые фронт может подставить в форму новой операции. "
            "Архивные шаблоны нельзя применить."
        ),
        responses={200: TransactionTemplateApplyDraftSerializer, 400: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    @action(detail=True, methods=["get"], url_path="apply-draft")
    def apply_draft(self, request, pk=None):
        template = self.get_object()

        if template.status == TransactionTemplateStatus.ARCHIVED:
            raise ValidationError(
                {"template": ["Архивный шаблон нельзя применить."]}
            )

        return Response(build_apply_draft_payload(template))

    @extend_schema(
        tags=["finance-transaction-templates"],
        summary="Применить шаблон операции",
        description=(
            "Создаёт финансовую операцию на основе шаблона. Можно переопределить "
            "дату, сумму, счёт, категорию, теги и примечание. После успешного "
            "создания операции обновляет useCount и lastUsedAt шаблона."
        ),
        request=TransactionTemplateApplySerializer,
        responses={200: TransactionTemplateApplyResponseSerializer, 400: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
        examples=[
            OpenApiExample(
                "Применение шаблона",
                value={
                    "operationDate": "2026-05-21",
                    "amountRub": 450.0,
                    "note": "Обед в офисе #обед",
                },
                request_only=True,
            )
        ],
    )
    @action(detail=True, methods=["post"], url_path="apply")
    def apply(self, request, pk=None):
        template = self.get_object()
        serializer = TransactionTemplateApplySerializer(
            data=request.data,
            context={"request": request, "template": template},
        )
        serializer.is_valid(raise_exception=True)
        transaction_serializer = self._build_transaction_serializer_from_template(
            template=template,
            apply_data=serializer.validated_data,
        )
        transaction_serializer.is_valid(raise_exception=True)

        with db_transaction.atomic():
            transaction = create_transaction_with_balance_update(transaction_serializer)
            TransactionTemplate.objects.filter(pk=template.pk).update(
                use_count=F("use_count") + 1,
                last_used_at=timezone.now(),
            )
            template.refresh_from_db()

        return Response(
            {
                "template": self.get_serializer(template).data,
                "transaction": TransactionSerializer(
                    transaction,
                    context={"request": request},
                ).data,
            }
        )

    def _build_transaction_serializer_from_template(self, *, template, apply_data):
        account = apply_data.get("accountId", template.account)
        category = apply_data.get("categoryId", template.category)
        tag_ids = apply_data.get("tagIds")
        tags = apply_data.get("_tags", None)
        description = apply_data.get("description")

        if description in (None, ""):
            description = apply_data.get("note")

        if description in (None, ""):
            description = template.note or template.name

        if tag_ids is None:
            tag_ids = list(template.tags.values_list("id", flat=True))
        elif tags is not None:
            tag_ids = [tag.pk for tag in tags]

        payload = {
            "account": account.pk,
            "category": category.pk,
            "type": template.kind,
            "amount": str(apply_data.get("amountRub", template.amount)),
            "description": description,
            "operation_date": apply_data.get("operationDate", timezone.localdate()).isoformat(),
            "tagIds": tag_ids,
        }

        return TransactionSerializer(
            data=payload,
            context={"request": self.request},
        )

    @extend_schema(
        tags=["finance-transaction-templates"],
        summary="Получить справочники для формы шаблона",
        responses={200: TransactionTemplateMetaResponseSerializer},
    )
    @action(detail=False, methods=["get"], url_path="meta")
    def meta(self, request):
        return Response(get_transaction_templates_meta_payload(request.user))

    @extend_schema(
        tags=["finance-transaction-templates"],
        summary="Проверить уникальность названия шаблона",
        parameters=[
            OpenApiParameter("name", OpenApiTypes.STR, description="Название шаблона."),
            OpenApiParameter("excludeId", OpenApiTypes.INT, description="ID шаблона, который нужно исключить при редактировании."),
        ],
        responses={200: TransactionTemplateCheckNameResponseSerializer, 400: OpenApiTypes.OBJECT},
    )
    @action(detail=False, methods=["get"], url_path="check-name")
    def check_name(self, request):
        name = request.query_params.get("name", "").strip()
        exclude_id = request.query_params.get("excludeId") or request.query_params.get("exclude_id")

        if not name:
            raise ValidationError({"name": ["Передайте название шаблона."]})

        try:
            exclude_id = int(exclude_id) if exclude_id not in (None, "") else None
        except (TypeError, ValueError) as exc:
            raise ValidationError({"excludeId": ["excludeId должен быть целым числом."]}) from exc

        is_duplicate = transaction_template_duplicate_exists(
            user=request.user,
            name=name,
            exclude_id=exclude_id,
        )

        if is_duplicate:
            return Response(
                {
                    "available": False,
                    "message": "Активный шаблон с таким названием уже существует.",
                }
            )

        return Response({"available": True})

    @extend_schema(
        tags=["finance-transaction-templates"],
        summary="Проверить форму шаблона без сохранения",
        request=TransactionTemplateValidateSerializer,
        responses={200: TransactionTemplateValidateResponseSerializer},
    )
    @action(detail=False, methods=["post"], url_path="validate")
    def validate_form(self, request):
        serializer = TransactionTemplateValidateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        errors = validate_transaction_template_form(
            user=request.user,
            data=serializer.validated_data,
        )

        return Response(
            {
                "ok": not bool(errors),
                "fieldErrors": errors,
            }
        )
