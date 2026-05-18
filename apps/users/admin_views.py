from django.contrib.auth import get_user_model
from django.db.models import Q
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiTypes,
    extend_schema,
    extend_schema_view,
)
from rest_framework import status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from apps.common.validation import get_bool_query_param, validate_ordering
from apps.users.admin_serializers import UserSerializer


User = get_user_model()


@extend_schema_view(
    list=extend_schema(
        tags=["users"],
        summary="Получить список пользователей",
        description=(
            "Возвращает список пользователей с фильтрацией и сортировкой. "
            "Endpoint доступен только администраторам."
        ),
        parameters=[
            OpenApiParameter(
                "is_active",
                OpenApiTypes.BOOL,
                description="Фильтр по активности пользователя.",
            ),
            OpenApiParameter(
                "is_staff",
                OpenApiTypes.BOOL,
                description="Фильтр по признаку staff-пользователя.",
            ),
            OpenApiParameter(
                "is_superuser",
                OpenApiTypes.BOOL,
                description="Фильтр по признаку superuser.",
            ),
            OpenApiParameter(
                "search",
                OpenApiTypes.STR,
                description="Поиск по username или email.",
            ),
            OpenApiParameter(
                "ordering",
                OpenApiTypes.STR,
                description=(
                    "Сортировка. Поддерживаются поля: id, username, email, "
                    "date_joined. Для сортировки по убыванию используйте префикс '-'."
                ),
            ),
        ],
        responses={200: UserSerializer(many=True)},
        examples=[
            OpenApiExample(
                "Список пользователей",
                value={
                    "count": 1,
                    "next": None,
                    "previous": None,
                    "results": [
                        {
                            "id": 1,
                            "username": "admin",
                            "email": "admin@example.com",
                            "first_name": "Timofey",
                            "last_name": "Admin",
                            "role": "admin",
                            "is_active": True,
                            "is_staff": True,
                            "is_superuser": True,
                            "date_joined": "2026-05-15T12:00:00+0300",
                        }
                    ],
                },
                response_only=True,
            )
        ],
    ),
    create=extend_schema(
        tags=["users"],
        summary="Создать пользователя",
        description=(
            "Создаёт пользователя через административный endpoint. "
            "Endpoint доступен только администраторам."
        ),
        request=UserSerializer,
        responses={201: UserSerializer},
        examples=[
            OpenApiExample(
                "Создание пользователя",
                value={
                    "username": "demo",
                    "email": "demo@example.com",
                    "first_name": "Demo",
                    "last_name": "User",
                    "role": "user",
                    "is_active": True,
                    "is_staff": False,
                    "is_superuser": False,
                },
                request_only=True,
            )
        ],
    ),
    retrieve=extend_schema(
        tags=["users"],
        summary="Получить пользователя",
        description=(
            "Возвращает данные пользователя по ID. "
            "Endpoint доступен только администраторам."
        ),
        responses={200: UserSerializer},
    ),
    partial_update=extend_schema(
        tags=["users"],
        summary="Частично обновить пользователя",
        description=(
            "Частично обновляет пользователя через административный endpoint. "
            "Endpoint доступен только администраторам."
        ),
        request=UserSerializer,
        responses={200: UserSerializer},
        examples=[
            OpenApiExample(
                "Обновление пользователя",
                value={
                    "first_name": "Updated",
                    "is_active": True,
                },
                request_only=True,
            )
        ],
    ),
    destroy=extend_schema(
        tags=["users"],
        summary="Деактивировать пользователя",
        description=(
            "Не удаляет пользователя физически, а переводит его в is_active=false. "
            "Администратор не может деактивировать собственную учётную запись "
            "через этот endpoint."
        ),
        responses={204: None},
    ),
)
class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    permission_classes = [IsAdminUser]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        queryset = User.objects.all().order_by("id")

        is_active = get_bool_query_param(self.request.query_params, "is_active")
        is_staff = get_bool_query_param(self.request.query_params, "is_staff")
        is_superuser = get_bool_query_param(self.request.query_params, "is_superuser")
        search = self.request.query_params.get("search")
        ordering = validate_ordering(
            self.request.query_params.get("ordering"),
            {
                "id",
                "-id",
                "username",
                "-username",
                "email",
                "-email",
                "date_joined",
                "-date_joined",
            },
        )

        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)

        if is_staff is not None:
            queryset = queryset.filter(is_staff=is_staff)

        if is_superuser is not None:
            queryset = queryset.filter(is_superuser=is_superuser)

        if search:
            queryset = queryset.filter(
                Q(username__icontains=search) | Q(email__icontains=search)
            )

        if ordering:
            queryset = queryset.order_by(ordering)

        return queryset

    def destroy(self, request, *args, **kwargs):
        user = self.get_object()

        if user.id == request.user.id:
            raise ValidationError(
                {
                    "detail": (
                        "Нельзя деактивировать собственную учетную запись "
                        "через этот endpoint."
                    )
                }
            )

        user.is_active = False
        user.save(update_fields=["is_active"])

        return Response(status=status.HTTP_204_NO_CONTENT)
