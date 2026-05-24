from __future__ import annotations

from datetime import time
from urllib.parse import urlparse

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class PwaPushProvider(models.TextChoices):
    WEB_PUSH = "web_push", "Web Push"


class PwaPushSubscription(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="pwa_push_subscriptions",
        verbose_name="Пользователь",
    )
    device_id = models.CharField(
        max_length=120,
        verbose_name="ID устройства",
    )
    provider = models.CharField(
        max_length=30,
        choices=PwaPushProvider.choices,
        default=PwaPushProvider.WEB_PUSH,
        verbose_name="Push-провайдер",
    )
    endpoint = models.URLField(
        max_length=2048,
        verbose_name="Push endpoint",
    )
    p256dh = models.TextField(
        verbose_name="Ключ p256dh",
    )
    auth = models.TextField(
        verbose_name="Auth secret",
    )
    browser = models.CharField(
        max_length=80,
        blank=True,
        verbose_name="Браузер",
    )
    platform = models.CharField(
        max_length=80,
        blank=True,
        verbose_name="Платформа",
    )
    user_agent = models.TextField(
        blank=True,
        verbose_name="User-Agent",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активна",
    )
    last_used_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Последнее использование",
    )
    revoked_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Дата отзыва",
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
        verbose_name = "PWA push-подписка"
        verbose_name_plural = "PWA push-подписки"
        ordering = ["-is_active", "-updated_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "endpoint"],
                name="unique_pwa_push_endpoint_per_user",
            ),
            models.CheckConstraint(
                condition=models.Q(provider__in=PwaPushProvider.values),
                name="pwa_push_provider_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "is_active"], name="idx_pwa_push_user_active"),
            models.Index(fields=["user", "device_id"], name="idx_pwa_push_user_device"),
            models.Index(fields=["user", "updated_at"], name="idx_pwa_push_user_updated"),
        ]

    @property
    def endpoint_host(self) -> str:
        return urlparse(self.endpoint).netloc

    def clean(self) -> None:
        errors = {}

        self.device_id = str(self.device_id or "").strip()
        self.endpoint = str(self.endpoint or "").strip()
        self.p256dh = str(self.p256dh or "").strip()
        self.auth = str(self.auth or "").strip()
        self.browser = str(self.browser or "").strip()[:80]
        self.platform = str(self.platform or "").strip()[:80]
        self.user_agent = str(self.user_agent or "").strip()[:1000]

        if not self.device_id:
            errors["device_id"] = "Укажите ID устройства."

        parsed_endpoint = urlparse(self.endpoint)
        if parsed_endpoint.scheme not in {"https", "http"} or not parsed_endpoint.netloc:
            errors["endpoint"] = "Укажите корректный push endpoint."

        if not self.p256dh:
            errors["p256dh"] = "Укажите ключ p256dh."

        if not self.auth:
            errors["auth"] = "Укажите auth secret."

        if self.provider not in PwaPushProvider.values:
            errors["provider"] = "Недопустимый push-провайдер."

        if self.is_active:
            self.revoked_at = None
        elif self.revoked_at is None:
            self.revoked_at = timezone.now()

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.provider}: user={self.user_id}, device={self.device_id}"


class PwaNotificationSettings(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="pwa_notification_settings",
        verbose_name="Пользователь",
    )
    push_enabled = models.BooleanField(
        default=True,
        verbose_name="Push-уведомления включены",
    )
    sync_conflict = models.BooleanField(
        default=True,
        verbose_name="Уведомлять о конфликтах синхронизации",
    )
    sync_failed = models.BooleanField(
        default=True,
        verbose_name="Уведомлять об ошибках синхронизации",
    )
    budget_limit_warning = models.BooleanField(
        default=True,
        verbose_name="Уведомлять о приближении к лимиту бюджета",
    )
    planned_transaction_due = models.BooleanField(
        default=True,
        verbose_name="Уведомлять о планируемых операциях",
    )
    receipt_imported = models.BooleanField(
        default=True,
        verbose_name="Уведомлять об импорте чека",
    )
    quiet_hours_enabled = models.BooleanField(
        default=False,
        verbose_name="Тихие часы включены",
    )
    quiet_hours_from = models.TimeField(
        default=time(22, 0),
        verbose_name="Начало тихих часов",
    )
    quiet_hours_to = models.TimeField(
        default=time(8, 0),
        verbose_name="Окончание тихих часов",
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
        verbose_name = "PWA настройки уведомлений"
        verbose_name_plural = "PWA настройки уведомлений"
        ordering = ["user_id"]
        indexes = [
            models.Index(fields=["user"], name="idx_pwa_notif_set_user"),
            models.Index(fields=["push_enabled"], name="idx_pwa_notif_push"),
        ]

    def __str__(self) -> str:
        return f"PWA notification settings for user_id={self.user_id}"
