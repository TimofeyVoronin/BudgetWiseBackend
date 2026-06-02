import re

from django.conf import settings
from django.contrib.auth import get_user_model
from drf_spectacular.utils import OpenApiTypes, extend_schema_field
from rest_framework import serializers

from apps.users.auth.verification import (
    email_verification_enabled,
    ensure_verified_contact,
    is_email_verified,
    is_phone_verified,
)


User = get_user_model()

PHONE_PATTERN = re.compile(r"^\+?[0-9][0-9\s()\-]{6,30}$")
NAME_PATTERN = re.compile(r"^[A-Za-zА-Яа-яЁё\-\s]+$")
CITY_PATTERN = re.compile(r"^[A-Za-zА-Яа-яЁё0-9\-\s.,()]+$")


class HomeGreetingSerializer(serializers.Serializer):
    phrase = serializers.CharField(read_only=True)
    userName = serializers.CharField(read_only=True)


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
            "middle_name",
            "phone",
            "city",
            "bio",
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

    def validate(self, attrs):
        self._validate_phone_change(attrs)
        return attrs

    def _validate_phone_change(self, attrs) -> None:
        if self.instance is None or "phone" not in attrs:
            return

        old_phone = (self.instance.phone or "").strip()
        new_phone = (attrs.get("phone") or "").strip()

        if old_phone == new_phone:
            return

        if not old_phone:
            return

        ensure_verified_contact(self.instance)


class UserProfileMeSerializer(serializers.ModelSerializer):
    firstName = serializers.CharField(
        source="first_name",
        required=False,
        allow_blank=True,
        max_length=150,
        help_text="Имя пользователя. Необязательное поле.",
    )
    lastName = serializers.CharField(
        source="last_name",
        required=False,
        allow_blank=True,
        max_length=150,
        help_text="Фамилия пользователя. Необязательное поле.",
    )
    middleName = serializers.CharField(
        source="middle_name",
        required=False,
        allow_blank=True,
        max_length=150,
        help_text="Отчество пользователя. Необязательное поле.",
    )
    fullName = serializers.SerializerMethodField(
        help_text="ФИО пользователя в формате: фамилия, имя, отчество.",
    )
    phone = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=32,
        help_text="Номер телефона. Поле необязательное.",
    )
    city = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=120,
        help_text="Город пользователя. Поле необязательное.",
    )
    bio = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=500,
        help_text="Краткое описание профиля. До 500 символов.",
    )
    avatarUrl = serializers.SerializerMethodField(
        help_text="Абсолютный URL аватара пользователя или null, если аватар не загружен.",
    )
    isEmailVerified = serializers.SerializerMethodField(
        help_text=(
            "Статус подтверждения email. Если подтверждение email выключено, "
            "значение показывает, что отдельная проверка сейчас не применяется."
        ),
    )
    isPhoneVerified = serializers.SerializerMethodField(
        help_text="Статус подтверждения телефона. Сейчас подтверждение телефона не подключено.",
    )
    emailVerificationEnabled = serializers.SerializerMethodField(
        help_text="Включён ли flow подтверждения email при регистрации.",
    )
    phoneVerificationEnabled = serializers.SerializerMethodField(
        help_text="Включено ли подтверждение телефона.",
    )
    createdAt = serializers.DateTimeField(
        source="date_joined",
        read_only=True,
        help_text="Дата регистрации пользователя.",
    )
    updatedAt = serializers.SerializerMethodField(
        help_text=(
            "Дата последнего обновления профиля. Пока отдельное поле updated_at "
            "не хранится, поэтому возвращается null."
        ),
    )

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "firstName",
            "lastName",
            "middleName",
            "fullName",
            "phone",
            "city",
            "bio",
            "avatarUrl",
            "isEmailVerified",
            "isPhoneVerified",
            "emailVerificationEnabled",
            "phoneVerificationEnabled",
            "createdAt",
            "updatedAt",
        ]
        read_only_fields = [
            "id",
            "username",
            "email",
            "fullName",
            "avatarUrl",
            "isEmailVerified",
            "isPhoneVerified",
            "emailVerificationEnabled",
            "phoneVerificationEnabled",
            "createdAt",
            "updatedAt",
        ]

    @extend_schema_field(OpenApiTypes.STR)
    def get_fullName(self, obj) -> str:
        return obj.full_name

    @extend_schema_field(OpenApiTypes.URI)
    def get_avatarUrl(self, obj) -> str | None:
        if not getattr(obj, "avatar", None):
            return None

        try:
            avatar_url = obj.avatar.url
        except ValueError:
            return None

        request = self.context.get("request")
        if request is not None:
            return request.build_absolute_uri(avatar_url)

        return avatar_url

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_isEmailVerified(self, obj) -> bool:
        return is_email_verified(obj)

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_isPhoneVerified(self, obj) -> bool:
        return is_phone_verified(obj)

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_emailVerificationEnabled(self, obj) -> bool:
        return email_verification_enabled()

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_phoneVerificationEnabled(self, obj) -> bool:
        return False

    @extend_schema_field(OpenApiTypes.DATETIME)
    def get_updatedAt(self, obj):
        return None

    def validate_firstName(self, value: str) -> str:
        return _validate_name(value, "Имя")

    def validate_lastName(self, value: str) -> str:
        return _validate_name(value, "Фамилия")

    def validate_middleName(self, value: str) -> str:
        return _validate_name(value, "Отчество")

    def validate_phone(self, value: str) -> str:
        value = value.strip()

        if not value:
            return ""

        if not PHONE_PATTERN.match(value):
            raise serializers.ValidationError(
                "Телефон должен содержать 7-31 символ: цифры, пробелы, скобки, дефисы и опциональный + в начале.",
                code="invalid_phone",
            )

        return value

    def validate_city(self, value: str) -> str:
        value = value.strip()

        if not value:
            return ""

        if not CITY_PATTERN.match(value):
            raise serializers.ValidationError(
                "Город может содержать буквы, цифры, пробелы и символы - . , ( ).",
                code="invalid_city",
            )

        return value

    def validate_bio(self, value: str) -> str:
        return value.strip()

    def validate(self, attrs):
        self._validate_phone_change(attrs)
        return attrs

    def _validate_phone_change(self, attrs) -> None:
        if self.instance is None or "phone" not in attrs:
            return

        old_phone = (self.instance.phone or "").strip()
        new_phone = (attrs.get("phone") or "").strip()

        if old_phone == new_phone:
            return

        if not old_phone:
            return

        ensure_verified_contact(self.instance)


def _validate_name(value: str, field_title: str) -> str:
    value = value.strip()

    if not value:
        return ""

    if not NAME_PATTERN.match(value):
        raise serializers.ValidationError(
            f"{field_title} может содержать только буквы, пробелы и дефис.",
            code="invalid_name",
        )

    return value


ALLOWED_AVATAR_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}

ALLOWED_AVATAR_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}


class UserProfileAvatarUploadSerializer(serializers.Serializer):
    avatar = serializers.FileField(
        required=True,
        help_text=(
            "Файл аватара пользователя. Поддерживаются JPEG, PNG и WebP. "
            "Максимальный размер задаётся настройкой USER_PROFILE_AVATAR_MAX_SIZE_BYTES."
        ),
    )

    def validate_avatar(self, value):
        max_size = settings.USER_PROFILE_AVATAR_MAX_SIZE_BYTES
        if value.size > max_size:
            max_size_mb = max_size // (1024 * 1024)
            raise serializers.ValidationError(
                f"Размер аватара не должен превышать {max_size_mb} МБ.",
                code="avatar_too_large",
            )

        content_type = getattr(value, "content_type", "") or ""
        if content_type not in ALLOWED_AVATAR_CONTENT_TYPES:
            raise serializers.ValidationError(
                "Аватар должен быть изображением JPEG, PNG или WebP.",
                code="unsupported_avatar_type",
            )

        extension = value.name.rsplit(".", 1)[-1].lower() if "." in value.name else ""
        if extension not in ALLOWED_AVATAR_EXTENSIONS:
            raise serializers.ValidationError(
                "Расширение файла должно быть .jpg, .jpeg, .png или .webp.",
                code="unsupported_avatar_extension",
            )

        return value


class UserProfileAvatarResponseSerializer(serializers.Serializer):
    avatarUrl = serializers.URLField(
        allow_null=True,
        required=False,
        help_text="Абсолютный URL нового аватара пользователя.",
    )
    message = serializers.CharField(
        required=False,
        help_text="Короткое сообщение о результате операции.",
    )


class UserProfileAvatarDeleteResponseSerializer(serializers.Serializer):
    deleted = serializers.BooleanField(
        help_text="Флаг успешного удаления аватара.",
    )
    avatarUrl = serializers.URLField(
        allow_null=True,
        required=False,
        help_text="После удаления всегда null.",
    )
