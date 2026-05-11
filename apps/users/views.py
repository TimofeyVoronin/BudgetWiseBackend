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
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.validation import get_bool_query_param, validate_ordering
from apps.users.serializers import (
    CurrentUserSerializer,
    LoginSerializer,
    UserSerializer,
)
from apps.users.throttles import LoginRateThrottle


User = get_user_model()


class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]
    serializer_class = LoginSerializer

    @extend_schema(
        tags=["auth"],
        summary="Войти в систему",
        description=(
            "Аутентифицирует пользователя по email и password. "
            "При успешном входе возвращает access token, refresh token "
            "и краткие данные пользователя."
        ),
        request=LoginSerializer,
        responses={200: LoginSerializer},
        examples=[
            OpenApiExample(
                "Пример запроса",
                value={
                    "email": "admin@example.com",
                    "password": "admin-password-123",
                },
                request_only=True,
            ),
            OpenApiExample(
                "Успешный ответ",
                value={
                    "access": "jwt-access-token",
                    "refresh": "jwt-refresh-token",
                    "user": {
                        "id": 1,
                        "username": "admin",
                        "email": "admin@example.com",
                        "first_name": "Timofey",
                        "last_name": "Demo",
                        "role": "admin",
                        "is_active": True,
                    },
                },
                response_only=True,
            ),
        ],
    )
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class CurrentUserView(GenericAPIView):
    serializer_class = CurrentUserSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["users"],
        operation_id="users_me_retrieve",
        summary="Получить данные текущего пользователя",
        responses={200: CurrentUserSerializer},
    )
    def get(self, request):
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

    @extend_schema(
        tags=["users"],
        operation_id="users_me_partial_update",
        summary="Частично обновить данные текущего пользователя",
        request=CurrentUserSerializer,
        responses={200: CurrentUserSerializer},
    )
    def patch(self, request):
        serializer = self.get_serializer(
            request.user,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


@extend_schema_view(
    list=extend_schema(
        tags=["users"],
        summary="Получить список пользователей",
        parameters=[
            OpenApiParameter("is_active", OpenApiTypes.BOOL),
            OpenApiParameter("is_staff", OpenApiTypes.BOOL),
            OpenApiParameter("is_superuser", OpenApiTypes.BOOL),
            OpenApiParameter("search", OpenApiTypes.STR),
            OpenApiParameter("ordering", OpenApiTypes.STR),
        ],
    ),
    create=extend_schema(tags=["users"], summary="Создать пользователя"),
    retrieve=extend_schema(tags=["users"], summary="Получить пользователя"),
    partial_update=extend_schema(
        tags=["users"],
        summary="Частично обновить пользователя",
    ),
    destroy=extend_schema(tags=["users"], summary="Деактивировать пользователя"),
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