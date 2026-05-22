from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.users.profile_serializers import (
    CurrentUserSerializer,
    UserProfileMeSerializer,
)


class CurrentUserView(GenericAPIView):
    serializer_class = CurrentUserSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["users"],
        operation_id="users_me_retrieve",
        summary="Получить данные текущего пользователя",
        description=(
            "Возвращает краткий профиль авторизованного пользователя. "
            "Endpoint используется фронтом для получения данных текущей сессии "
            "после входа, обновления страницы или проверки access token. "
            "Для полной страницы профиля используйте GET /api/v1/profile/me/."
        ),
        responses={200: CurrentUserSerializer},
        examples=[
            OpenApiExample(
                "Успешный ответ",
                value={
                    "id": 1,
                    "username": "timofey",
                    "email": "timofey@example.com",
                    "first_name": "Timofey",
                    "last_name": "Demo",
                    "middle_name": "",
                    "phone": "",
                    "city": "",
                    "bio": "",
                    "role": "user",
                    "is_active": True,
                    "date_joined": "2026-05-15T12:00:00+0300",
                },
                response_only=True,
            )
        ],
    )
    def get(self, request):
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

    @extend_schema(
        tags=["users"],
        operation_id="users_me_partial_update",
        summary="Частично обновить краткие данные текущего пользователя",
        description=(
            "Частично обновляет краткий профиль текущего пользователя. "
            "Для полной страницы профиля и camelCase-контракта используйте "
            "PUT/PATCH /api/v1/profile/me/."
        ),
        request=CurrentUserSerializer,
        responses={200: CurrentUserSerializer},
        examples=[
            OpenApiExample(
                "Обновление профиля",
                value={
                    "first_name": "Timofey",
                    "last_name": "Backend",
                    "middle_name": "",
                    "phone": "+79990000000",
                    "city": "Красноярск",
                    "bio": "Backend Python Developer",
                },
                request_only=True,
            ),
            OpenApiExample(
                "Успешный ответ",
                value={
                    "id": 1,
                    "username": "timofey",
                    "email": "timofey@example.com",
                    "first_name": "Timofey",
                    "last_name": "Backend",
                    "middle_name": "",
                    "phone": "+79990000000",
                    "city": "Красноярск",
                    "bio": "Backend Python Developer",
                    "role": "user",
                    "is_active": True,
                    "date_joined": "2026-05-15T12:00:00+0300",
                },
                response_only=True,
            ),
        ],
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


class UserProfileMeView(GenericAPIView):
    serializer_class = UserProfileMeSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["users-profile"],
        operation_id="profile_me_retrieve",
        summary="Получить полный профиль текущего пользователя",
        description=(
            "Возвращает данные для страницы профиля: ФИО, email, телефон, город, "
            "краткое описание и статусы подтверждения контактных данных. "
            "Email и username являются read-only. Подтверждение email уже есть в системе, "
            "но может быть выключено настройкой REGISTRATION_REQUIRE_EMAIL_CONFIRMATION."
        ),
        responses={200: UserProfileMeSerializer},
        examples=[
            OpenApiExample(
                "Успешный ответ",
                value={
                    "id": 1,
                    "username": "timofey",
                    "email": "timofey@example.com",
                    "firstName": "Тимофей",
                    "lastName": "Воронин",
                    "middleName": "Викторович",
                    "fullName": "Воронин Тимофей Викторович",
                    "phone": "+79990000000",
                    "city": "Красноярск",
                    "bio": "Backend Python Developer",
                    "avatarUrl": None,
                    "isEmailVerified": False,
                    "isPhoneVerified": False,
                    "emailVerificationEnabled": False,
                    "phoneVerificationEnabled": False,
                    "createdAt": "2026-05-15T12:00:00+0300",
                    "updatedAt": None,
                },
                response_only=True,
            )
        ],
    )
    def get(self, request, *args, **kwargs):
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

    @extend_schema(
        tags=["users-profile"],
        operation_id="profile_me_update",
        summary="Полностью обновить профиль текущего пользователя",
        description=(
            "Обновляет редактируемые поля профиля. Все поля формы необязательные, "
            "поэтому endpoint можно использовать как безопасный PUT для страницы профиля. "
            "Email и username через этот endpoint не меняются."
        ),
        request=UserProfileMeSerializer,
        responses={200: UserProfileMeSerializer},
        examples=[
            OpenApiExample(
                "Пример запроса",
                value={
                    "firstName": "Тимофей",
                    "lastName": "Воронин",
                    "middleName": "Викторович",
                    "phone": "+79990000000",
                    "city": "Красноярск",
                    "bio": "Backend Python Developer",
                },
                request_only=True,
            )
        ],
    )
    def put(self, request, *args, **kwargs):
        serializer = self.get_serializer(
            request.user,
            data=request.data,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @extend_schema(
        tags=["users-profile"],
        operation_id="profile_me_partial_update",
        summary="Частично обновить профиль текущего пользователя",
        description=(
            "Частично обновляет редактируемые поля профиля: имя, фамилию, отчество, "
            "телефон, город и краткое описание. Email и username через этот endpoint "
            "не меняются."
        ),
        request=UserProfileMeSerializer,
        responses={200: UserProfileMeSerializer},
        examples=[
            OpenApiExample(
                "Пример запроса",
                value={
                    "city": "Красноярск",
                    "phone": "+79990000000",
                },
                request_only=True,
            )
        ],
    )
    def patch(self, request, *args, **kwargs):
        serializer = self.get_serializer(
            request.user,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
