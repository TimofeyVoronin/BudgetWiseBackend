import logging

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.models import update_last_login
from django.contrib.auth.password_validation import validate_password
from django.core.signing import BadSignature, SignatureExpired
from django.db import transaction
from django.utils import timezone

from drf_spectacular.utils import OpenApiTypes, extend_schema_field
from rest_framework import serializers
from rest_framework.exceptions import (
    AuthenticationFailed,
    PermissionDenied,
    ValidationError,
)
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.email_confirmation import (
    EMAIL_CONFIRMATION_PURPOSE,
    load_email_confirmation_token,
    send_email_confirmation,
)
from apps.users.models import PasswordResetToken
from apps.users.password_reset import (
    get_password_reset_token_record,
    send_password_reset_email,
)


User = get_user_model()

logger = logging.getLogger("apps")


PASSWORD_RESET_REQUEST_ACCEPTED_MESSAGE = (
    "Если аккаунт с таким email существует, "
    "мы отправили ссылку для восстановления пароля."
)

PASSWORD_RESET_SUCCESS_MESSAGE = (
    "Пароль успешно изменён. Теперь можно войти с новым паролем."
)


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


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField(write_only=True)
    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        min_length=8,
    )
    password_confirm = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        min_length=8,
    )

    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    detail = serializers.CharField(read_only=True)

    def validate_email(self, email):
        normalized_email = email.strip().lower()

        if User.objects.filter(email__iexact=normalized_email).exists():
            raise serializers.ValidationError(
                "Пользователь с таким email уже существует.",
                code="unique",
            )

        return normalized_email

    def validate(self, attrs):
        password = attrs.get("password")
        password_confirm = attrs.get("password_confirm")

        if password != password_confirm:
            raise serializers.ValidationError(
                {
                    "password_confirm": [
                        serializers.ErrorDetail(
                            "Пароли не совпадают.",
                            code="password_mismatch",
                        )
                    ]
                }
            )

        validate_password(password)

        return attrs

    def create(self, validated_data):
        email = validated_data["email"]
        password = validated_data["password"]

        username = self._generate_username(email)

        require_email_confirmation = settings.REGISTRATION_REQUIRE_EMAIL_CONFIRMATION

        user = User(
            username=username,
            email=email,
            is_active=not require_email_confirmation,
        )
        user.set_password(password)
        user.save()

        if require_email_confirmation:
            send_email_confirmation(user)

        return user

    def to_representation(self, instance):
        if settings.REGISTRATION_REQUIRE_EMAIL_CONFIRMATION:
            detail = (
                "Пользователь зарегистрирован. "
                "Для активации аккаунта подтвердите email."
            )
        else:
            detail = "Пользователь зарегистрирован. Теперь можно войти в аккаунт."

        return {
            "id": instance.id,
            "username": instance.username,
            "email": instance.email,
            "is_active": instance.is_active,
            "detail": detail,
        }

    def _generate_username(self, email: str) -> str:
        base_username = email.split("@")[0]
        base_username = "".join(
            char for char in base_username if char.isalnum() or char in "._+-"
        )
        base_username = base_username[:140] or "user"

        username = base_username
        counter = 1

        while User.objects.filter(username=username).exists():
            suffix = f"_{counter}"
            username = f"{base_username[:150 - len(suffix)]}{suffix}"
            counter += 1

        return username


class VerifyEmailSerializer(serializers.Serializer):
    token = serializers.CharField(write_only=True, trim_whitespace=False)

    id = serializers.IntegerField(read_only=True)
    email = serializers.EmailField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    detail = serializers.CharField(read_only=True)

    def validate(self, attrs):
        token = attrs["token"]

        try:
            payload = load_email_confirmation_token(token)
        except SignatureExpired:
            raise ValidationError(
                {
                    "token": [
                        serializers.ErrorDetail(
                            "Срок действия ссылки подтверждения истёк.",
                            code="token_expired",
                        )
                    ]
                }
            )
        except BadSignature:
            raise ValidationError(
                {
                    "token": [
                        serializers.ErrorDetail(
                            "Недействительная ссылка подтверждения email.",
                            code="invalid_token",
                        )
                    ]
                }
            )

        if payload.get("purpose") != EMAIL_CONFIRMATION_PURPOSE:
            raise ValidationError(
                {
                    "token": [
                        serializers.ErrorDetail(
                            "Недействительная ссылка подтверждения email.",
                            code="invalid_token",
                        )
                    ]
                }
            )

        user = User.objects.filter(id=payload.get("user_id")).first()

        if user is None:
            raise ValidationError(
                {
                    "token": [
                        serializers.ErrorDetail(
                            "Недействительная ссылка подтверждения email.",
                            code="invalid_token",
                        )
                    ]
                }
            )

        token_email = str(payload.get("email", "")).lower()
        user_email = str(user.email).lower()

        if token_email != user_email:
            raise ValidationError(
                {
                    "token": [
                        serializers.ErrorDetail(
                            "Недействительная ссылка подтверждения email.",
                            code="invalid_token",
                        )
                    ]
                }
            )

        if user.is_active:
            raise ValidationError(
                {
                    "token": [
                        serializers.ErrorDetail(
                            "Email уже подтверждён.",
                            code="token_already_used",
                        )
                    ]
                }
            )

        attrs["user"] = user
        return attrs

    def save(self, **kwargs):
        user = self.validated_data["user"]
        user.is_active = True
        user.save(update_fields=["is_active"])

        return user

    def to_representation(self, instance):
        return {
            "id": instance.id,
            "email": instance.email,
            "is_active": instance.is_active,
            "detail": "Email подтверждён. Аккаунт активирован.",
        }


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField(write_only=True)
    detail = serializers.CharField(read_only=True)

    def validate_email(self, email):
        return email.strip().lower()

    def save(self, **kwargs):
        request = self.context.get("request")
        email = self.validated_data["email"]

        user = (
            User.objects
            .filter(email__iexact=email, is_active=True)
            .first()
        )

        if user is None:
            logger.info(
                (
                    "Password reset requested for non-existing or inactive account. "
                    "client_ip=%s"
                ),
                self._get_client_ip(request),
            )
            return {
                "detail": PASSWORD_RESET_REQUEST_ACCEPTED_MESSAGE,
            }

        try:
            send_password_reset_email(user=user, request=request)
        except Exception:
            logger.exception(
                (
                    "Password reset request accepted, but email sending failed. "
                    "user_id=%s client_ip=%s"
                ),
                user.id,
                self._get_client_ip(request),
            )

        return {
            "detail": PASSWORD_RESET_REQUEST_ACCEPTED_MESSAGE,
        }

    def to_representation(self, instance):
        return {
            "detail": PASSWORD_RESET_REQUEST_ACCEPTED_MESSAGE,
        }

    def _get_client_ip(self, request) -> str | None:
        if request is None:
            return None

        forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")

        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        return request.META.get("REMOTE_ADDR")


class ResetPasswordSerializer(serializers.Serializer):
    token = serializers.CharField(write_only=True, trim_whitespace=False)
    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        min_length=8,
    )
    password_confirm = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        min_length=8,
    )

    detail = serializers.CharField(read_only=True)

    def validate(self, attrs):
        token = attrs.get("token")
        password = attrs.get("password")
        password_confirm = attrs.get("password_confirm")

        if password != password_confirm:
            raise serializers.ValidationError(
                {
                    "password_confirm": [
                        serializers.ErrorDetail(
                            "Пароли не совпадают.",
                            code="password_mismatch",
                        )
                    ]
                }
            )

        token_record = get_password_reset_token_record(token)

        if token_record is None:
            raise serializers.ValidationError(
                {
                    "token": [
                        serializers.ErrorDetail(
                            "Недействительная ссылка восстановления пароля.",
                            code="invalid_token",
                        )
                    ]
                }
            )

        if token_record.is_used:
            raise serializers.ValidationError(
                {
                    "token": [
                        serializers.ErrorDetail(
                            "Ссылка восстановления пароля уже использована.",
                            code="token_already_used",
                        )
                    ]
                }
            )

        if token_record.is_expired:
            raise serializers.ValidationError(
                {
                    "token": [
                        serializers.ErrorDetail(
                            "Срок действия ссылки восстановления пароля истёк.",
                            code="token_expired",
                        )
                    ]
                }
            )

        validate_password(password, user=token_record.user)

        attrs["token_record"] = token_record
        return attrs

    def save(self, **kwargs):
        token_record = self.validated_data["token_record"]
        password = self.validated_data["password"]
        request = self.context.get("request")

        with transaction.atomic():
            locked_token_record = (
                PasswordResetToken.objects
                .select_for_update()
                .select_related("user")
                .get(pk=token_record.pk)
            )

            if locked_token_record.is_used:
                raise serializers.ValidationError(
                    {
                        "token": [
                            serializers.ErrorDetail(
                                "Ссылка восстановления пароля уже использована.",
                                code="token_already_used",
                            )
                        ]
                    }
                )

            if locked_token_record.is_expired:
                raise serializers.ValidationError(
                    {
                        "token": [
                            serializers.ErrorDetail(
                                "Срок действия ссылки восстановления пароля истёк.",
                                code="token_expired",
                            )
                        ]
                    }
                )

            user = locked_token_record.user
            user.set_password(password)
            user.save(update_fields=["password"])

            now = timezone.now()

            locked_token_record.used_at = now
            locked_token_record.save(update_fields=["used_at"])

            invalidated_tokens_count = (
                PasswordResetToken.objects
                .filter(
                    user=user,
                    used_at__isnull=True,
                )
                .exclude(pk=locked_token_record.pk)
                .update(used_at=now)
            )

        logger.info(
            (
                "Password reset completed. "
                "user_id=%s token_id=%s invalidated_tokens_count=%s client_ip=%s"
            ),
            user.id,
            locked_token_record.id,
            invalidated_tokens_count,
            self._get_client_ip(request),
        )

        return {
            "detail": PASSWORD_RESET_SUCCESS_MESSAGE,
        }

    def _get_client_ip(self, request) -> str | None:
        if request is None:
            return None

        forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")

        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        return request.META.get("REMOTE_ADDR")


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