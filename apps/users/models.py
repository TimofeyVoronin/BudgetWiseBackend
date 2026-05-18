from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    email = models.EmailField(unique=True)

    def __str__(self) -> str:
        return self.email or self.username


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