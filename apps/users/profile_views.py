from django.core.files.storage import default_storage
from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework.generics import GenericAPIView
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.users.profile_serializers import (
    CurrentUserSerializer,
    UserProfileAvatarDeleteResponseSerializer,
    UserProfileAvatarResponseSerializer,
    UserProfileAvatarUploadSerializer,
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


class UserProfileAvatarView(GenericAPIView):
    serializer_class = UserProfileAvatarUploadSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def _get_avatar_url(self, request) -> str | None:
        return UserProfileMeSerializer(
            request.user,
            context={"request": request},
        ).data["avatarUrl"]

    @extend_schema(
        tags=["users-profile"],
        operation_id="profile_me_avatar_upload",
        summary="Загрузить или заменить аватар текущего пользователя",
        description=(
            "Загружает аватар текущего пользователя через multipart/form-data. "
            "Поддерживаются JPEG, PNG и WebP. При успешной загрузке старый файл "
            "аватара удаляется из локального media storage."
        ),
        request=UserProfileAvatarUploadSerializer,
        responses={200: UserProfileAvatarResponseSerializer},
        examples=[
            OpenApiExample(
                "Успешный ответ",
                value={
                    "avatarUrl": "http://localhost:8000/media/avatars/user_1/avatar.jpg",
                    "message": "Аватар обновлён.",
                },
                response_only=True,
            )
        ],
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        old_avatar_name = user.avatar.name if user.avatar else ""

        user.avatar = serializer.validated_data["avatar"]
        user.save(update_fields=["avatar"])

        _delete_storage_file_if_unused(old_avatar_name, user.avatar.name)

        return Response(
            {
                "avatarUrl": self._get_avatar_url(request),
                "message": "Аватар обновлён.",
            }
        )

    @extend_schema(
        tags=["users-profile"],
        operation_id="profile_me_avatar_delete",
        summary="Удалить аватар текущего пользователя",
        description=(
            "Удаляет файл аватара из локального media storage и очищает ссылку "
            "на аватар в профиле текущего пользователя."
        ),
        responses={200: UserProfileAvatarDeleteResponseSerializer},
        examples=[
            OpenApiExample(
                "Успешный ответ",
                value={"deleted": True, "avatarUrl": None},
                response_only=True,
            )
        ],
    )
    def delete(self, request, *args, **kwargs):
        user = request.user
        avatar_name = user.avatar.name if user.avatar else ""

        if avatar_name:
            user.avatar = None
            user.save(update_fields=["avatar"])
            _delete_storage_file_if_unused(avatar_name, "")

        return Response({"deleted": True, "avatarUrl": None})


def _delete_storage_file_if_unused(file_name: str, current_file_name: str) -> None:
    if not file_name or file_name == current_file_name:
        return

    if default_storage.exists(file_name):
        default_storage.delete(file_name)
