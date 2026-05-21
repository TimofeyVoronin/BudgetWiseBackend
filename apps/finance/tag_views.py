from __future__ import annotations

from django.db.models import Q
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiTypes,
    extend_schema,
    extend_schema_view,
)
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.common.domain_errors import DomainConflictError

from apps.finance.models import Tag
from apps.finance.tag_serializers import (
    DeleteTagConflictResponseSerializer,
    DeleteTagResponseSerializer,
    MoveTagGroupSerializer,
    RenameTagResponseSerializer,
    RenameTagSerializer,
    SetTagVisibilitySerializer,
    TagSerializer,
    TagsGroupsResponseSerializer,
    TagsListResponseSerializer,
    TagsMetaResponseSerializer,
    TagsSelectOptionsResponseSerializer,
    ValidateTagResponseSerializer,
    ValidateTagSerializer,
    get_tag_group_payload,
    get_tags_meta_payload,
    serializer_errors_to_field_errors,
    validate_tag_form,
)
from apps.finance.tags import (
    MAX_TAG_SEARCH_LENGTH,
    TAG_SORT_FIELDS,
    TAG_SORT_ORDERS,
    build_tags_summary,
    get_accessible_tag_groups,
    get_accessible_tags,
    get_tag_operations_count,
)


@extend_schema_view(
    list=extend_schema(
        tags=["finance-tags"],
        summary="Получить список тегов операций",
        description=(
            "Возвращает теги текущего пользователя и системные теги. "
            "Список используется на странице централизованного управления "
            "тегами операций, в фильтрах и формах выбора тегов. "
            "Ответ содержит строки тегов, сводку и список групп."
        ),
        parameters=[
            OpenApiParameter(
                "search",
                OpenApiTypes.STR,
                description="Поиск по названию тега, группе или описанию.",
            ),
            OpenApiParameter(
                "groupId",
                OpenApiTypes.INT,
                description="ID группы тегов. Для тегов без группы передайте null или none.",
            ),
            OpenApiParameter(
                "tagIds",
                OpenApiTypes.STR,
                description="Список ID тегов через запятую, например 1,2,3.",
            ),
            OpenApiParameter(
                "onlyWithOperations",
                OpenApiTypes.BOOL,
                description="true - вернуть только теги, связанные хотя бы с одной операцией.",
            ),
            OpenApiParameter(
                "includeHidden",
                OpenApiTypes.BOOL,
                description="true - включить теги, скрытые из форм операций.",
            ),
            OpenApiParameter(
                "sortBy",
                OpenApiTypes.STR,
                description=(
                    "Поле сортировки: name, operationsCount, createdAt, "
                    "updatedAt или isVisible."
                ),
            ),
            OpenApiParameter(
                "sortOrder",
                OpenApiTypes.STR,
                description=(
                    "Порядок сортировки: asc, desc, asc-nulls-first, "
                    "desc-nulls-first, asc-nulls-last, desc-nulls-last."
                ),
            ),
        ],
        responses={200: TagsListResponseSerializer},
        examples=[
            OpenApiExample(
                "Список тегов",
                value={
                    "items": [
                        {
                            "id": 1,
                            "name": "Продукты",
                            "groupId": 1,
                            "groupName": "Покупки",
                            "color": "#66BB6A",
                            "icon": "cart",
                            "operationsCount": 0,
                            "createdAt": "2026-05-21T10:00:00+0300",
                            "updatedAt": "2026-05-21T10:00:00+0300",
                            "isVisible": True,
                            "isSystem": False,
                            "description": "Повседневные покупки продуктов",
                        }
                    ],
                    "summary": {
                        "totalCount": 1,
                        "withOperationsCount": 0,
                        "withoutOperationsCount": 1,
                    },
                    "groups": [
                        {"id": None, "name": "Без группы"},
                        {"id": 1, "name": "Покупки"},
                    ],
                },
                response_only=True,
            )
        ],
    ),
    create=extend_schema(
        tags=["finance-tags"],
        summary="Создать тег операции",
        description=(
            "Создаёт пользовательский тег для операций. Название тега должно "
            "быть уникальным в пределах пользователя с учётом регистра и лишних пробелов."
        ),
        request=TagSerializer,
        responses={201: TagSerializer},
        examples=[
            OpenApiExample(
                "Создание тега",
                value={
                    "name": "Продукты",
                    "groupId": 1,
                    "color": "#66BB6A",
                    "icon": "cart",
                    "isVisible": True,
                    "description": "Повседневные покупки продуктов",
                },
                request_only=True,
            )
        ],
    ),
    retrieve=extend_schema(
        tags=["finance-tags"],
        summary="Получить тег операции",
        description="Возвращает пользовательский или системный тег по ID.",
        responses={200: TagSerializer},
    ),
    update=extend_schema(
        tags=["finance-tags"],
        summary="Полностью обновить тег операции",
        description="Полностью обновляет пользовательский тег операции.",
        request=TagSerializer,
        responses={200: TagSerializer},
    ),
    partial_update=extend_schema(
        tags=["finance-tags"],
        summary="Частично обновить тег операции",
        description=(
            "Частично обновляет пользовательский тег: название, группу, цвет, "
            "иконку, видимость в формах и описание."
        ),
        request=TagSerializer,
        responses={200: TagSerializer},
    ),
    destroy=extend_schema(
        tags=["finance-tags"],
        summary="Удалить тег операции",
        description=(
            "Удаляет пользовательский тег, если он не используется в операциях. "
            "Если тег связан с операциями, API возвращает 409 Conflict и предлагает "
            "скрыть тег из форм вместо удаления."
        ),
        responses={
            200: DeleteTagResponseSerializer,
            409: DeleteTagConflictResponseSerializer,
        },
    ),
)
class TagViewSet(viewsets.ModelViewSet):
    serializer_class = TagSerializer
    permission_classes = [IsAuthenticated]
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
        queryset = get_accessible_tags(self.request.user)

        # Для detail/action endpoints нельзя скрывать is_visible=False теги.
        # Иначе после PATCH /visibility/ false тег становится недоступен
        # для повторного редактирования и обратного PATCH /visibility/ true.
        if self.action != "list":
            return queryset.order_by("name", "id")

        query_params = self.request.query_params

        search = query_params.get("search")
        if search:
            if len(search) > MAX_TAG_SEARCH_LENGTH:
                raise ValidationError(
                    {
                        "search": [
                            f"Поиск не может быть длиннее {MAX_TAG_SEARCH_LENGTH} символов."
                        ]
                    }
                )

            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(description__icontains=search)
                | Q(group__name__icontains=search)
            )

        group_id = query_params.get("groupId") or query_params.get("group_id")
        if group_id not in (None, ""):
            normalized_group_id = str(group_id).strip().lower()

            if normalized_group_id in {"null", "none", "without", "without_group"}:
                queryset = queryset.filter(group__isnull=True)
            else:
                try:
                    queryset = queryset.filter(group_id=int(group_id))
                except (TypeError, ValueError) as exc:
                    raise ValidationError(
                        {"groupId": ["ID группы должен быть целым числом."]}
                    ) from exc

        tag_ids = self._get_int_list_query_param("tagIds", "tag_ids")
        if tag_ids:
            queryset = queryset.filter(pk__in=tag_ids)

        include_hidden = self._get_bool_query_param("includeHidden", "include_hidden")
        if include_hidden is not True:
            queryset = queryset.filter(is_visible=True)

        only_with_operations = self._get_bool_query_param(
            "onlyWithOperations",
            "only_with_operations",
        )
        if only_with_operations is True:
            queryset = queryset.filter(operations_count__gt=0)

        sort_by = query_params.get("sortBy") or query_params.get("sort_by") or "name"
        sort_order = query_params.get("sortOrder") or query_params.get("sort_order") or "asc"

        if sort_by not in TAG_SORT_FIELDS:
            raise ValidationError(
                {
                    "sortBy": [
                        "Допустимые значения: name, operationsCount, createdAt, updatedAt, isVisible."
                    ]
                }
            )

        if sort_order not in TAG_SORT_ORDERS:
            raise ValidationError(
                {
                    "sortOrder": [
                        (
                            "Допустимые значения: asc, desc, asc-nulls-first, "
                            "desc-nulls-first, asc-nulls-last, desc-nulls-last."
                        )
                    ]
                }
            )

        ordering_field = TAG_SORT_FIELDS[sort_by]
        if sort_order.startswith("desc"):
            ordering_field = f"-{ordering_field}"

        return queryset.order_by(ordering_field, "id")

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)

        return Response(
            {
                "items": serializer.data,
                "summary": build_tags_summary(queryset),
                "groups": get_tag_group_payload(request.user, include_empty_group=True),
            }
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance_id = instance.pk

        if instance.is_system:
            raise PermissionDenied("Системный тег нельзя удалить.")

        operations_count = get_tag_operations_count(instance)

        if operations_count > 0:
            raise DomainConflictError(
                code="tag_has_operations",
                message=(
                    "Тег нельзя удалить, так как он используется в операциях. "
                    "Скройте тег из форм, если он больше не нужен для новых операций."
                ),
                detail={
                    "code": "HAS_OPERATIONS",
                    "message": "Тег используется в операциях.",
                    "operationsCount": operations_count,
                    "canHide": True,
                },
            )

        self.perform_destroy(instance)

        return Response(
            {
                "deleted": True,
                "id": instance_id,
            },
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        tags=["finance-tags"],
        summary="Получить группы тегов",
        description="Возвращает системные и пользовательские группы тегов для фильтров и форм.",
        responses={200: TagsGroupsResponseSerializer},
    )
    @action(detail=False, methods=["get"], url_path="groups")
    def groups(self, request):
        return Response(
            {
                "groups": get_tag_group_payload(request.user, include_empty_group=True),
            }
        )

    @extend_schema(
        tags=["finance-tags"],
        summary="Получить теги для селектов",
        description=(
            "Возвращает сокращённый список видимых тегов для форм операций, "
            "шаблонов и фильтров."
        ),
        responses={200: TagsSelectOptionsResponseSerializer},
    )
    @action(detail=False, methods=["get"], url_path="select-options")
    def select_options(self, request):
        queryset = get_accessible_tags(request.user).filter(is_visible=True).order_by(
            "name",
            "id",
        )

        return Response(
            {
                "options": [
                    {
                        "title": tag.name,
                        "value": tag.pk,
                        "color": tag.color,
                        "icon": tag.icon,
                    }
                    for tag in queryset
                ]
            }
        )

    @extend_schema(
        tags=["finance-tags"],
        summary="Получить справочники тегов",
        description="Возвращает группы, цвета и иконки для формы создания и редактирования тега.",
        responses={200: TagsMetaResponseSerializer},
    )
    @action(detail=False, methods=["get"], url_path="meta")
    def meta(self, request):
        return Response(get_tags_meta_payload(request.user))

    @extend_schema(
        tags=["finance-tags"],
        summary="Проверить форму тега",
        description=(
            "Проверяет форму создания или редактирования тега без сохранения. "
            "Используется фронтом для отображения ошибок до отправки основной формы."
        ),
        request=ValidateTagSerializer,
        responses={200: ValidateTagResponseSerializer},
    )
    @action(detail=False, methods=["post"], url_path="validate")
    def validate_form(self, request):
        serializer = ValidateTagSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                {
                    "ok": False,
                    "fieldErrors": serializer_errors_to_field_errors(serializer.errors),
                },
                status=status.HTTP_200_OK,
            )

        field_errors = validate_tag_form(
            user=request.user,
            data=serializer.validated_data,
        )

        return Response(
            {
                "ok": not bool(field_errors),
                "fieldErrors": field_errors,
            }
        )

    @extend_schema(
        tags=["finance-tags"],
        summary="Переименовать тег",
        description="Обновляет только название пользовательского тега.",
        request=RenameTagSerializer,
        responses={200: RenameTagResponseSerializer},
    )
    @action(detail=True, methods=["patch"], url_path="rename")
    def rename(self, request, pk=None):
        tag = self.get_object()
        serializer = RenameTagSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        update_serializer = self.get_serializer(
            tag,
            data={"name": serializer.validated_data["name"]},
            partial=True,
        )
        update_serializer.is_valid(raise_exception=True)
        tag = update_serializer.save()

        return Response(
            {
                "tag": self.get_serializer(tag).data,
                "operationsCount": int(getattr(tag, "operations_count", 0) or 0),
            }
        )

    @extend_schema(
        tags=["finance-tags"],
        summary="Переместить тег в группу",
        description="Обновляет только группу пользовательского тега.",
        request=MoveTagGroupSerializer,
        responses={200: TagSerializer},
    )
    @action(detail=True, methods=["patch"], url_path="group")
    def move_group(self, request, pk=None):
        tag = self.get_object()
        serializer = MoveTagGroupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        group_id = serializer.validated_data.get("groupId")
        group = None

        if group_id is not None:
            try:
                group = get_accessible_tag_groups(request.user).get(pk=group_id)
            except Exception as exc:
                raise ValidationError(
                    {"groupId": ["Выберите существующую группу тегов."]}
                ) from exc

        update_serializer = self.get_serializer(
            tag,
            data={"groupId": group.pk if group else None},
            partial=True,
        )
        update_serializer.is_valid(raise_exception=True)
        tag = update_serializer.save()

        return Response(self.get_serializer(tag).data)

    @extend_schema(
        tags=["finance-tags"],
        summary="Изменить видимость тега",
        description="Скрывает или показывает пользовательский тег в формах операций и фильтрах.",
        request=SetTagVisibilitySerializer,
        responses={200: TagSerializer},
    )
    @action(detail=True, methods=["patch"], url_path="visibility")
    def visibility(self, request, pk=None):
        tag = self.get_object()
        serializer = SetTagVisibilitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        update_serializer = self.get_serializer(
            tag,
            data={"isVisible": serializer.validated_data["isVisible"]},
            partial=True,
        )
        update_serializer.is_valid(raise_exception=True)
        tag = update_serializer.save()

        return Response(self.get_serializer(tag).data)

    def _get_bool_query_param(self, *names: str) -> bool | None:
        for name in names:
            value = self.request.query_params.get(name)

            if value not in (None, ""):
                normalized_value = str(value).strip().lower()

                if normalized_value in {"true", "1", "yes"}:
                    return True

                if normalized_value in {"false", "0", "no"}:
                    return False

                raise ValidationError(
                    {names[0]: ["Значение должно быть true или false."]}
                )

        return None

    def _get_int_list_query_param(self, *names: str) -> list[int]:
        raw_values = []

        for name in names:
            for raw_value in self.request.query_params.getlist(name):
                raw_values.extend(
                    value.strip()
                    for value in str(raw_value).split(",")
                    if value.strip()
                )

            for raw_value in self.request.query_params.getlist(f"{name}[]"):
                raw_values.extend(
                    value.strip()
                    for value in str(raw_value).split(",")
                    if value.strip()
                )

        result = []

        for raw_value in raw_values:
            try:
                result.append(int(raw_value))
            except (TypeError, ValueError) as exc:
                raise ValidationError(
                    {names[0]: ["Значения фильтра должны быть целыми числами."]}
                ) from exc

        return result
