import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


def user_avatar_upload_to(instance, filename: str) -> str:
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"avatars/user_{instance.pk or 'new'}/{uuid.uuid4().hex}.{suffix}"



class User(AbstractUser):
    email = models.EmailField(unique=True)
    middle_name = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="Отчество",
    )
    phone = models.CharField(
        max_length=32,
        blank=True,
        verbose_name="Телефон",
    )
    email_verified = models.BooleanField(
        default=True,
        verbose_name="Email подтверждён",
    )
    email_verified_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Дата подтверждения email",
    )
    email_verification_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Дата последней отправки подтверждения email",
    )
    phone_verified = models.BooleanField(
        default=False,
        verbose_name="Телефон подтверждён",
    )
    phone_verified_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Дата подтверждения телефона",
    )
    city = models.CharField(
        max_length=120,
        blank=True,
        verbose_name="Город",
    )
    bio = models.TextField(
        blank=True,
        verbose_name="Краткое описание",
    )

    avatar = models.FileField(
        upload_to=user_avatar_upload_to,
        null=True,
        blank=True,
        verbose_name="Аватар",
    )
    avatar_url = models.URLField(
        max_length=700,
        blank=True,
        verbose_name="URL аватара",
    )
    avatar_public_id = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Cloudinary public ID аватара",
    )

    def __str__(self) -> str:
        return self.email or self.username

    @property
    def full_name(self) -> str:
        parts = [self.last_name, self.first_name, self.middle_name]
        full_name = " ".join(part for part in parts if part).strip()
        return full_name or self.username or self.email

    @property
    def has_verified_contact(self) -> bool:
        return bool(self.email_verified or self.phone_verified)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["phone"],
                condition=~models.Q(phone=""),
                name="uniq_user_non_empty_phone",
            ),
        ]


class UserProfileAuditAction(models.TextChoices):
    PROFILE_UPDATED = "profile_updated", "Профиль обновлён"
    NAME_CHANGED = "name_changed", "ФИО изменено"
    EMAIL_CHANGED = "email_changed", "Email изменён"
    PHONE_CHANGED = "phone_changed", "Телефон изменён"
    CITY_CHANGED = "city_changed", "Город изменён"
    BIO_CHANGED = "bio_changed", "Описание изменено"
    AVATAR_UPLOADED = "avatar_uploaded", "Аватар загружен"
    AVATAR_DELETED = "avatar_deleted", "Аватар удалён"


class UserProfileAuditLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile_audit_logs",
        verbose_name="Пользователь",
    )
    action = models.CharField(
        max_length=40,
        choices=UserProfileAuditAction.choices,
        verbose_name="Действие",
    )
    changed_fields = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Изменённые поля",
    )
    old_values = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Старые значения",
    )
    new_values = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Новые значения",
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Метаданные",
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name="IP адрес",
    )
    user_agent = models.TextField(
        blank=True,
        verbose_name="User-Agent",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания",
    )

    class Meta:
        verbose_name = "Аудит профиля пользователя"
        verbose_name_plural = "Аудит профилей пользователей"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["user", "created_at"], name="idx_prof_audit_user_time"),
            models.Index(fields=["action"], name="idx_prof_audit_action"),
        ]

    def clean(self) -> None:
        if isinstance(self.action, str):
            self.action = self.action.strip()

        if self.action not in UserProfileAuditAction.values:
            from django.core.exceptions import ValidationError

            raise ValidationError({"action": "Недопустимое действие аудита профиля."})

        if isinstance(self.user_agent, str):
            self.user_agent = self.user_agent.strip()[:1000]

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.action}: user={self.user_id}"


class AppDateFormat(models.TextChoices):
    DD_MM_YYYY = "DD.MM.YYYY", "ДД.ММ.ГГГГ"
    YYYY_MM_DD = "YYYY-MM-DD", "ГГГГ-ММ-ДД"
    MM_DD_YYYY = "MM/DD/YYYY", "ММ/ДД/ГГГГ"


class AppNumberFormat(models.TextChoices):
    RU_RU = "ru-RU", "Русский формат"
    EN_US = "en-US", "Английский формат"


class UserAppSettings(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="app_settings",
        verbose_name="Пользователь",
    )
    timezone = models.CharField(
        max_length=64,
        default="Asia/Krasnoyarsk",
        verbose_name="Часовой пояс",
    )
    date_format = models.CharField(
        max_length=20,
        choices=AppDateFormat.choices,
        default=AppDateFormat.DD_MM_YYYY,
        verbose_name="Формат даты",
    )
    number_format = models.CharField(
        max_length=20,
        choices=AppNumberFormat.choices,
        default=AppNumberFormat.RU_RU,
        verbose_name="Формат чисел",
    )
    default_currency = models.CharField(
        max_length=3,
        default="RUB",
        verbose_name="Валюта по умолчанию",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления",
    )

    class Meta:
        verbose_name = "Настройки приложения пользователя"
        verbose_name_plural = "Настройки приложения пользователей"
        indexes = [
            models.Index(fields=["user"], name="idx_appset_user"),
            models.Index(fields=["default_currency"], name="idx_appset_currency"),
        ]

    def clean(self) -> None:
        self.timezone = str(self.timezone or "").strip()
        self.default_currency = str(self.default_currency or "").strip().upper()

        if self.date_format not in AppDateFormat.values:
            from django.core.exceptions import ValidationError

            raise ValidationError({"date_format": "Недопустимый формат даты."})

        if self.number_format not in AppNumberFormat.values:
            from django.core.exceptions import ValidationError

            raise ValidationError({"number_format": "Недопустимый формат чисел."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"App settings for user_id={self.user_id}"


class PasswordResetToken(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="password_reset_tokens",
        verbose_name="Пользователь",
    )
    token_hash = models.CharField(
        max_length=128,
        unique=True,
        verbose_name="Hash token",
    )
    expires_at = models.DateTimeField(
        verbose_name="Действителен до",
    )
    used_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Использован",
    )
    requested_ip = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name="IP адрес запроса",
    )
    user_agent = models.TextField(
        blank=True,
        verbose_name="User-Agent",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания",
    )

    class Meta:
        verbose_name = "Token восстановления пароля"
        verbose_name_plural = "Tokens восстановления пароля"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["token_hash"]),
            models.Index(fields=["user", "used_at"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self) -> str:
        return f"Password reset token for user_id={self.user_id}"

    @property
    def is_used(self) -> bool:
        return self.used_at is not None

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def can_be_used(self) -> bool:
        return not self.is_used and not self.is_expired

    def mark_used(self) -> None:
        self.used_at = timezone.now()
        self.save(update_fields=["used_at"])


class PhoneVerificationCode(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="phone_verification_codes",
        verbose_name="Пользователь",
    )
    phone = models.CharField(
        max_length=32,
        verbose_name="Телефон",
    )
    code_hash = models.CharField(
        max_length=128,
        verbose_name="Hash кода",
    )
    attempts_count = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="Количество попыток",
    )
    expires_at = models.DateTimeField(
        verbose_name="Действителен до",
    )
    sent_at = models.DateTimeField(
        default=timezone.now,
        verbose_name="Дата отправки",
    )
    confirmed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Дата подтверждения",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания",
    )

    class Meta:
        verbose_name = "Код подтверждения телефона"
        verbose_name_plural = "Коды подтверждения телефона"
        ordering = ["-sent_at", "-id"]
        indexes = [
            models.Index(fields=["user", "phone", "confirmed_at"], name="idx_phone_verif_user_phone"),
            models.Index(fields=["expires_at"], name="idx_phone_verif_expires"),
            models.Index(fields=["sent_at"], name="idx_phone_verif_sent"),
        ]

    def __str__(self) -> str:
        return f"Phone verification for user_id={self.user_id} phone={self.phone}"

    @property
    def is_confirmed(self) -> bool:
        return self.confirmed_at is not None

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def can_be_used(self) -> bool:
        return not self.is_confirmed and not self.is_expired

