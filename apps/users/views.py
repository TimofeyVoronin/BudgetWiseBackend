from django.contrib.auth import get_user_model
from rest_framework import status, viewsets
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.serializers import CurrentUserSerializer, UserSerializer


User = get_user_model()


class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = CurrentUserSerializer(request.user)
        return Response(serializer.data)

    def patch(self, request):
        serializer = CurrentUserSerializer(
            request.user,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    permission_classes = [IsAdminUser]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        queryset = User.objects.all().order_by("id")

        is_active = self._get_bool_query_param("is_active")
        is_staff = self._get_bool_query_param("is_staff")
        is_superuser = self._get_bool_query_param("is_superuser")
        search = self.request.query_params.get("search")
        ordering = self.request.query_params.get("ordering")

        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)

        if is_staff is not None:
            queryset = queryset.filter(is_staff=is_staff)

        if is_superuser is not None:
            queryset = queryset.filter(is_superuser=is_superuser)

        if search:
            queryset = queryset.filter(username__icontains=search) | queryset.filter(
                email__icontains=search
            )

        if ordering:
            allowed_ordering = {
                "id",
                "-id",
                "username",
                "-username",
                "email",
                "-email",
                "date_joined",
                "-date_joined",
            }

            if ordering in allowed_ordering:
                queryset = queryset.order_by(ordering)

        return queryset

    def destroy(self, request, *args, **kwargs):
        user = self.get_object()

        if user.id == request.user.id:
            return Response(
                {
                    "detail": "Нельзя деактивировать собственную учетную запись через этот endpoint."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.is_active = False
        user.save(update_fields=["is_active"])

        return Response(status=status.HTTP_204_NO_CONTENT)

    def _get_bool_query_param(self, name: str):
        value = self.request.query_params.get(name)

        if value in (None, ""):
            return None

        if value in ("true", "True", "1"):
            return True

        if value in ("false", "False", "0"):
            return False

        return None