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
    RegisterSerializer,
    UserSerializer,
    VerifyEmailSerializer,
    ForgotPasswordSerializer,
    ResetPasswordSerializer,
)
from apps.users.throttles import (
    LoginRateThrottle,
    ForgotPasswordEmailThrottle,
    ForgotPasswordIPThrottle,
)


User = get_user_model()


class RegisterView(APIView):
    permission_classes = [AllowAny]
    serializer_class = RegisterSerializer

    @extend_schema(
        tags=["auth"],
        summary="Зарегистрировать пользователя",
        description=(
            "Создаёт нового неактивного пользователя по email и password. "
            "После регистрации backend отправляет письмо со ссылкой подтверждения email."
        ),
        request=RegisterSerializer,
        responses={201: RegisterSerializer},
        examples=[
            OpenApiExample(
                "Пример запроса",
                value={
                    "email": "user@example.com",
                    "password": "user-password-123",
                    "password_confirm": "user-password-123",
                },
                request_only=True,
            ),
            OpenApiExample(
                "Успешный ответ",
                value={
                    "id": 1,
                    "username": "user",
                    "email": "user@example.com",
                    "is_active": False,
                    "detail": (
                        "Пользователь зарегистрирован. "
                        "Для активации аккаунта подтвердите email."
                    ),
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
        user = serializer.save()

        response_serializer = self.serializer_class(user)

        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class VerifyEmailView(APIView):
    permission_classes = [AllowAny]
    serializer_class = VerifyEmailSerializer

    @extend_schema(
        tags=["auth"],
        summary="Подтвердить email пользователя",
        description=(
            "Проверяет token подтверждения email. "
            "Если token действителен, активирует аккаунт пользователя. "
            "Повторное использование token после активации запрещено."
        ),
        request=VerifyEmailSerializer,
        responses={200: VerifyEmailSerializer},
        examples=[
            OpenApiExample(
                "Пример запроса",
                value={
                    "token": "email-confirmation-token",
                },
                request_only=True,
            ),
            OpenApiExample(
                "Успешный ответ",
                value={
                    "id": 1,
                    "email": "user@example.com",
                    "is_active": True,
                    "detail": "Email подтверждён. Аккаунт активирован.",
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
        user = serializer.save()

        response_serializer = self.serializer_class(user)

        return Response(response_serializer.data, status=status.HTTP_200_OK)


class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]
    serializer_class = ForgotPasswordSerializer
    throttle_classes = [
        ForgotPasswordIPThrottle,
        ForgotPasswordEmailThrottle,
    ]

    @extend_schema(
        tags=["auth"],
        summary="Запросить восстановление пароля",
        description=(
            "Принимает email и, если активный пользователь с таким email существует, "
            "отправляет письмо со ссылкой восстановления пароля. "
            "Ответ всегда одинаковый для существующего и несуществующего email."
        ),
        request=ForgotPasswordSerializer,
        responses={200: ForgotPasswordSerializer},
        examples=[
            OpenApiExample(
                "Пример запроса",
                value={
                    "email": "user@example.com",
                },
                request_only=True,
            ),
            OpenApiExample(
                "Успешный ответ",
                value={
                    "detail": (
                        "Если аккаунт с таким email существует, "
                        "мы отправили ссылку для восстановления пароля."
                    ),
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
        result = serializer.save()

        return Response(result, status=status.HTTP_200_OK)


class ResetPasswordView(APIView):
    permission_classes = [AllowAny]
    serializer_class = ResetPasswordSerializer

    @extend_schema(
        tags=["auth"],
        summary="Сбросить пароль по token",
        description=(
            "Принимает token восстановления пароля и новый пароль. "
            "Проверяет, что token существует, не истёк и не был использован. "
            "После успешной смены пароля token помечается использованным."
        ),
        request=ResetPasswordSerializer,
        responses={200: ResetPasswordSerializer},
        examples=[
            OpenApiExample(
                "Пример запроса",
                value={
                    "token": "password-reset-token",
                    "password": "NewPassword123!",
                    "password_confirm": "NewPassword123!",
                },
                request_only=True,
            ),
            OpenApiExample(
                "Успешный ответ",
                value={
                    "detail": "Пароль успешно изменён. Теперь можно войти с новым паролем.",
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
        result = serializer.save()

        return Response(result, status=status.HTTP_200_OK)


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