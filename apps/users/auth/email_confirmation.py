from __future__ import annotations

from datetime import timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.conf import settings
from django.core import signing
from django.core.mail import send_mail
from django.utils import timezone
from rest_framework import serializers


EMAIL_CONFIRMATION_PURPOSE = "email_confirmation"
EMAIL_CONFIRMATION_ACCEPTED_MESSAGE = "Письмо подтверждения email отправлено."
EMAIL_ALREADY_CONFIRMED_MESSAGE = "Email уже подтверждён."


def build_email_confirmation_token(user) -> str:
    payload = {
        "purpose": EMAIL_CONFIRMATION_PURPOSE,
        "user_id": user.id,
        "email": user.email,
    }

    return signing.dumps(
        payload,
        salt=settings.EMAIL_CONFIRMATION_TOKEN_SALT,
        compress=True,
    )


def load_email_confirmation_token(token: str) -> dict:
    return signing.loads(
        token,
        salt=settings.EMAIL_CONFIRMATION_TOKEN_SALT,
        max_age=settings.EMAIL_CONFIRMATION_TOKEN_TIMEOUT_SECONDS,
    )


def build_email_confirmation_link(token: str) -> str:
    base_url = settings.FRONTEND_EMAIL_VERIFY_URL

    url_parts = urlsplit(base_url)
    query_params = dict(parse_qsl(url_parts.query))
    query_params["token"] = token

    return urlunsplit(
        (
            url_parts.scheme,
            url_parts.netloc,
            url_parts.path,
            urlencode(query_params),
            url_parts.fragment,
        )
    )


def send_email_confirmation(user) -> int:
    token = build_email_confirmation_token(user)
    confirmation_link = build_email_confirmation_link(token)

    subject = "Подтверждение email в BudgetWise"

    message = (
        f"Здравствуйте, {user.username}!\n\n"
        "Для подтверждения email в BudgetWise перейдите по ссылке:\n\n"
        f"{confirmation_link}\n\n"
        "Ссылка действительна 24 часа.\n\n"
        "Если вы не регистрировались в BudgetWise, просто проигнорируйте это письмо."
    )

    return send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )


def request_email_confirmation(user, *, force: bool = False) -> dict:
    if not settings.EMAIL_VERIFICATION_ENABLED:
        return {
            "sent": False,
            "queued": False,
            "reason": "email_verification_disabled",
        }

    if user.email_verified:
        return {
            "sent": False,
            "queued": False,
            "reason": "email_already_confirmed",
            "detail": EMAIL_ALREADY_CONFIRMED_MESSAGE,
        }

    now = timezone.now()
    cooldown_seconds = int(settings.EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS)

    if not force and user.email_verification_sent_at:
        next_allowed_at = user.email_verification_sent_at + timedelta(seconds=cooldown_seconds)
        if now < next_allowed_at:
            retry_after_seconds = max(1, int((next_allowed_at - now).total_seconds()))
            raise serializers.ValidationError(
                {
                    "detail": [
                        serializers.ErrorDetail(
                            f"Повторно отправить письмо можно через {retry_after_seconds} сек.",
                            code="email_verification_recently_sent",
                        )
                    ]
                }
            )

    user.email_verification_sent_at = now
    user.save(update_fields=["email_verification_sent_at"])

    if settings.EMAIL_VERIFICATION_SEND_ASYNC:
        from apps.users.tasks import send_email_confirmation_task

        task_result = send_email_confirmation_task.delay(user.id)
        return {
            "sent": False,
            "queued": True,
            "task_id": str(task_result.id),
            "detail": EMAIL_CONFIRMATION_ACCEPTED_MESSAGE,
        }

    sent_count = send_email_confirmation(user)
    return {
        "sent": bool(sent_count),
        "queued": False,
        "detail": EMAIL_CONFIRMATION_ACCEPTED_MESSAGE,
    }
