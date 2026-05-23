from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.conf import settings
from django.core import signing
from django.core.mail import send_mail


EMAIL_CONFIRMATION_PURPOSE = "email_confirmation"


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
        "Для завершения регистрации в BudgetWise подтвердите email по ссылке:\n\n"
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