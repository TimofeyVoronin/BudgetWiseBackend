from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.users.profile_serializers import CurrentUserSerializer


class CurrentUserView(GenericAPIView):
    serializer_class = CurrentUserSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["users"],
        operation_id="users_me_retrieve",
        summary="Получить данные текущего пользователя",
        description=(
            "Возвращает профиль авторизованного пользователя. "
            "Endpoint используется фронтом для получения данных текущей сессии "
            "после входа, обновления страницы или проверки access token."
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
        summary="Частично обновить данные текущего пользователя",
        description=(
            "Частично обновляет профиль текущего пользователя. "
            "Подходит для изменения имени, фамилии и других разрешённых "
            "пользовательских полей."
        ),
        request=CurrentUserSerializer,
        responses={200: CurrentUserSerializer},
        examples=[
            OpenApiExample(
                "Обновление профиля",
                value={
                    "first_name": "Timofey",
                    "last_name": "Backend",
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
