from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.views import TokenRefreshView

from apps.users.auth.serializers import (
    ChangeEmailSerializer,
    ChangePasswordSerializer,
    ForgotPasswordSerializer,
    LoginSerializer,
    LogoutSerializer,
    RegisterSerializer,
    ResendEmailVerificationSerializer,
    ResetPasswordSerializer,
    VerifyEmailSerializer,
)
from apps.users.auth.throttles import (
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
            "Создаёт нового активного пользователя по email и password. "
            "Если email-верификация включена, backend отправляет письмо подтверждения, "
            "но вход в систему остаётся доступным сразу после регистрации."
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
                    "is_active": True,
                    "isEmailVerified": False,
                    "emailVerificationRequired": True,
                    "detail": (
                        "Пользователь зарегистрирован. "
                        "Для защиты аккаунта подтвердите email."
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
            "Если token действителен, подтверждает email пользователя. "
            "Повторное использование token для уже подтверждённого email возвращает успешный ответ."
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
                    "isEmailVerified": True,
                    "emailVerificationRequired": False,
                    "detail": "Email подтверждён.",
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

        return Response(serializer.to_representation(user), status=status.HTTP_200_OK)


class ResendEmailVerificationView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ResendEmailVerificationSerializer

    @extend_schema(
        tags=["auth"],
        summary="Повторно отправить письмо подтверждения email",
        description=(
            "Отправляет новое письмо подтверждения email текущему пользователю. "
            "Если email уже подтверждён, возвращает успешный ответ без отправки письма."
        ),
        request=None,
        responses={200: ResendEmailVerificationSerializer},
        examples=[
            OpenApiExample(
                "Успешный ответ",
                value={
                    "detail": "Письмо подтверждения email отправлено.",
                    "queued": True,
                },
                response_only=True,
            )
        ],
    )
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(context={"request": request})
        result = serializer.save()
        return Response(result, status=status.HTTP_200_OK)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ChangePasswordSerializer

    @extend_schema(
        tags=["auth"],
        summary="Изменить пароль текущего пользователя",
        description=(
            "Меняет пароль авторизованного пользователя. "
            "Для действия нужен подтверждённый email или телефон."
        ),
        request=ChangePasswordSerializer,
        responses={200: ChangePasswordSerializer},
        examples=[
            OpenApiExample(
                "Пример запроса",
                value={
                    "currentPassword": "OldPassword123!",
                    "newPassword": "NewPassword123!",
                    "newPasswordConfirm": "NewPassword123!",
                },
                request_only=True,
            ),
            OpenApiExample(
                "Успешный ответ",
                value={"detail": "Пароль успешно изменён."},
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


class ChangeEmailView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ChangeEmailSerializer

    @extend_schema(
        tags=["auth"],
        summary="Изменить email текущего пользователя",
        description=(
            "Меняет email текущего пользователя после проверки текущего пароля. "
            "Для действия нужен подтверждённый email или телефон. "
            "После смены email подтверждение сбрасывается и отправляется новое письмо."
        ),
        request=ChangeEmailSerializer,
        responses={200: ChangeEmailSerializer},
        examples=[
            OpenApiExample(
                "Пример запроса",
                value={
                    "newEmail": "new-email@example.com",
                    "currentPassword": "Password123!",
                },
                request_only=True,
            ),
            OpenApiExample(
                "Успешный ответ",
                value={
                    "id": 1,
                    "email": "new-email@example.com",
                    "isEmailVerified": False,
                    "emailVerificationRequired": True,
                    "detail": "Email изменён. Подтвердите новый email по ссылке из письма.",
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


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LogoutSerializer

    @extend_schema(
        tags=["auth"],
        summary="Выйти из системы",
        description=(
            "Завершает пользовательскую сессию на сервере. "
            "Принимает refresh token и добавляет его в blacklist, "
            "после чего этот refresh token нельзя использовать для обновления access token. "
            "Access token остаётся действительным до истечения своего короткого срока жизни."
        ),
        request=LogoutSerializer,
        responses={200: LogoutSerializer},
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
                    "detail": "Выход выполнен. Refresh token добавлен в blacklist.",
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
