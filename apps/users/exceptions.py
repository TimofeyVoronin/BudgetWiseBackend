from rest_framework import status
from rest_framework.exceptions import APIException


class PasswordResetTokenInvalid(APIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "Недействительная ссылка восстановления пароля."
    default_code = "invalid_token"


class PasswordResetTokenExpired(APIException):
    status_code = status.HTTP_410_GONE
    default_detail = "Срок действия ссылки восстановления пароля истёк."
    default_code = "token_expired"


class PasswordResetTokenAlreadyUsed(APIException):
    status_code = status.HTTP_410_GONE
    default_detail = "Ссылка восстановления пароля уже использована."
    default_code = "token_already_used"