import logging
import secrets
from datetime import timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from django.utils.crypto import salted_hmac

from apps.users.models import PasswordResetToken


logger = logging.getLogger("apps")

PASSWORD_RESET_TOKEN_SALT = "budgetwise.password-reset"


def make_password_reset_token_hash(token: str) -> str:
    return salted_hmac(
        PASSWORD_RESET_TOKEN_SALT,
        token,
        secret=settings.SECRET_KEY,
        algorithm="sha256",
    ).hexdigest()


def issue_password_reset_token(user, request=None) -> str:
    raw_token = secrets.token_urlsafe(settings.PASSWORD_RESET_TOKEN_BYTES)
    token_hash = make_password_reset_token_hash(raw_token)

    expires_at = timezone.now() + timedelta(
        seconds=settings.PASSWORD_RESET_TOKEN_TIMEOUT_SECONDS,
    )

    PasswordResetToken.objects.create(
        user=user,
        token_hash=token_hash,
        expires_at=expires_at,
        requested_ip=_get_client_ip(request),
        user_agent=_get_user_agent(request),
    )

    return raw_token


def get_password_reset_token_record(token: str) -> PasswordResetToken | None:
    token_hash = make_password_reset_token_hash(token)

    return (
        PasswordResetToken.objects
        .select_related("user")
        .filter(token_hash=token_hash)
        .first()
    )


def build_password_reset_link(token: str) -> str:
    base_url = settings.FRONTEND_PASSWORD_RESET_URL

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


def send_password_reset_email(user, request=None) -> int:
    token = issue_password_reset_token(user=user, request=request)
    reset_link = build_password_reset_link(token)

    subject = "Восстановление пароля в BudgetWise"
    message = _build_password_reset_email_message(
        username=user.username,
        reset_link=reset_link,
    )

    try:
        sent_count = send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
    except Exception:
        logger.exception(
            (
                "Password reset email sending failed. "
                "user_id=%s client_ip=%s"
            ),
            user.id,
            _get_client_ip(request),
        )
        raise

    logger.info(
        (
            "Password reset email sent. "
            "user_id=%s sent_count=%s client_ip=%s"
        ),
        user.id,
        sent_count,
        _get_client_ip(request),
    )

    return sent_count


def _build_password_reset_email_message(username: str, reset_link: str) -> str:
    timeout_minutes = max(
        settings.PASSWORD_RESET_TOKEN_TIMEOUT_SECONDS // 60,
        1,
    )

    return (
        f"Здравствуйте, {username}!\n\n"
        "Мы получили запрос на восстановление пароля в BudgetWise.\n\n"
        "Чтобы задать новый пароль, перейдите по ссылке:\n\n"
        f"{reset_link}\n\n"
        f"Ссылка действительна {timeout_minutes} минут.\n\n"
        "Если вы не запрашивали восстановление пароля, просто проигнорируйте это письмо."
    )


def _get_client_ip(request) -> str | None:
    if request is None:
        return None

    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")

    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    return request.META.get("REMOTE_ADDR")


def _get_user_agent(request) -> str:
    if request is None:
        return ""

    return request.META.get("HTTP_USER_AGENT", "")