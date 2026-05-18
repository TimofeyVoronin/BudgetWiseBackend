from django.contrib.auth import get_user_model
from drf_spectacular.utils import OpenApiTypes, extend_schema_field
from rest_framework import serializers


User = get_user_model()


class CurrentUserSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "role",
            "is_active",
            "date_joined",
        ]
        read_only_fields = [
            "id",
            "username",
            "email",
            "role",
            "is_active",
            "date_joined",
        ]

    @extend_schema_field(OpenApiTypes.STR)
    def get_role(self, obj) -> str:
        if obj.is_superuser:
            return "admin"

        if obj.is_staff:
            return "staff"

        return "user"
