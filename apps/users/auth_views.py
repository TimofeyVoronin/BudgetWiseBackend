from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.views import TokenRefreshView

from apps.users.auth_serializers import (
    ForgotPasswordSerializer,
    LoginSerializer,
    RegisterSerializer,
    ResetPasswordSerializer,
    VerifyEmailSerializer,
)
from apps.users.throttles import (
    ForgotPasswordEmailThrottle,
    ForgotPasswordIPThrottle,
    LoginRateThrottle,
)


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


class BudgetWiseTokenRefreshView(TokenRefreshView):
    permission_classes = [AllowAny]
    serializer_class = TokenRefreshSerializer

    @extend_schema(
        tags=["auth"],
        summary="Обновить JWT access token",
        description=(
            "Принимает refresh token и возвращает новую пару JWT-токенов. "
            "Используется клиентом для продления сессии без повторного ввода email и password."
        ),
        request=TokenRefreshSerializer,
        responses={200: TokenRefreshSerializer},
        examples=[
            OpenApiExample(
                "Пример запроса",
                value={
                    "refresh": "jwt-refresh-token",
                },
                request_only=True,
            ),
            OpenApiExample(
                "Успешный ответ",
                value={
                    "access": "new-jwt-access-token",
                    "refresh": "rotated-jwt-refresh-token",
                },
                response_only=True,
            ),
        ],
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)
