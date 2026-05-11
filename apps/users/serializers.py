from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.models import update_last_login
from drf_spectacular.utils import OpenApiTypes, extend_schema_field
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework_simplejwt.tokens import RefreshToken


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


class UserSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField(read_only=True)
    password = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=False,
        min_length=8,
    )

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "password",
            "first_name",
            "last_name",
            "role",
            "is_active",
            "is_staff",
            "is_superuser",
            "date_joined",
            "last_login",
        ]
        read_only_fields = [
            "id",
            "role",
            "date_joined",
            "last_login",
        ]

    @extend_schema_field(OpenApiTypes.STR)
    def get_role(self, obj) -> str:
        if obj.is_superuser:
            return "admin"

        if obj.is_staff:
            return "staff"

        return "user"

    def validate_email(self, email):
        queryset = User.objects.filter(email=email)

        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)

        if queryset.exists():
            raise serializers.ValidationError(
                "Пользователь с таким email уже существует."
            )

        return email

    def validate_username(self, username):
        queryset = User.objects.filter(username=username)

        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)

        if queryset.exists():
            raise serializers.ValidationError(
                "Пользователь с таким username уже существует."
            )

        return username

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = User(**validated_data)

        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()

        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)

        for field, value in validated_data.items():
            setattr(instance, field, value)

        if password:
            instance.set_password(password)

        instance.save()
        return instance


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(write_only=True)
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    access = serializers.CharField(read_only=True)
    refresh = serializers.CharField(read_only=True)
    user = serializers.DictField(read_only=True)

    default_error_messages = {
        "invalid_credentials": "Неверный email или пароль.",
        "inactive_user": "Учётная запись неактивна.",
    }

    def validate(self, attrs):
        request = self.context.get("request")

        email = attrs.get("email")
        password = attrs.get("password")

        user = User.objects.filter(email__iexact=email).first()

        if user is None:
            raise AuthenticationFailed(
                self.error_messages["invalid_credentials"],
                code="authentication_failed",
            )

        if user.check_password(password) and not user.is_active:
            raise PermissionDenied(
                self.error_messages["inactive_user"],
                code="permission_denied",
            )

        authenticated_user = authenticate(
            request=request,
            username=user.get_username(),
            password=password,
        )

        if authenticated_user is None:
            raise AuthenticationFailed(
                self.error_messages["invalid_credentials"],
                code="authentication_failed",
            )

        refresh = RefreshToken.for_user(authenticated_user)
        update_last_login(None, authenticated_user)

        return {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": {
                "id": authenticated_user.id,
                "username": authenticated_user.username,
                "email": authenticated_user.email,
                "first_name": authenticated_user.first_name,
                "last_name": authenticated_user.last_name,
                "role": self._get_role(authenticated_user),
                "is_active": authenticated_user.is_active,
            },
        }

    def _get_role(self, user) -> str:
        if user.is_superuser:
            return "admin"

        if user.is_staff:
            return "staff"

        return "user"