import logging

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.models import update_last_login
from django.contrib.auth.password_validation import validate_password
from django.core.signing import BadSignature, SignatureExpired
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import (
    AuthenticationFailed,
    PermissionDenied,
    ValidationError,
)
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.auth.email_confirmation import (
    EMAIL_ALREADY_CONFIRMED_MESSAGE,
    EMAIL_CONFIRMATION_ACCEPTED_MESSAGE,
    EMAIL_CONFIRMATION_PURPOSE,
    load_email_confirmation_token,
    request_email_confirmation,
)
from apps.users.auth.exceptions import (
    PasswordResetTokenAlreadyUsed,
    PasswordResetTokenExpired,
    PasswordResetTokenInvalid,
)
from apps.users.models import PasswordResetToken
from apps.users.auth.password_reset import (
    get_password_reset_token_record,
    send_password_reset_email,
)
from apps.users.auth.verification import (
    EMAIL_NOT_VERIFIED_CODE,
    EMAIL_NOT_VERIFIED_MESSAGE,
    email_verification_required,
    ensure_verified_contact,
    has_verified_contact,
    is_email_verified,
    is_phone_verified,
)
from apps.users.models import UserProfileAuditAction
from apps.users.profile.audit import log_profile_audit_event


User = get_user_model()

logger = logging.getLogger("apps")


PASSWORD_RESET_REQUEST_ACCEPTED_MESSAGE = (
    "Если аккаунт с таким email существует, "
    "мы отправили ссылку для восстановления пароля."
)

PASSWORD_RESET_SUCCESS_MESSAGE = (
    "Пароль успешно изменён. Теперь можно войти с новым паролем."
)


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
    isEmailVerified = serializers.BooleanField(read_only=True)
    emailVerificationRequired = serializers.BooleanField(read_only=True)
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

        email_verification_enabled = settings.EMAIL_VERIFICATION_ENABLED

        user = User(
            username=username,
            email=email,
            is_active=True,
            email_verified=not email_verification_enabled,
            email_verified_at=timezone.now() if not email_verification_enabled else None,
        )
        user.set_password(password)
        user.save()

        if email_verification_enabled:
            try:
                request_email_confirmation(user, force=True)
            except Exception:
                logger.exception(
                    "User registered, but email confirmation sending failed. user_id=%s",
                    user.id,
                )

        return user

    def to_representation(self, instance):
        if settings.EMAIL_VERIFICATION_ENABLED:
            detail = (
                "Пользователь зарегистрирован. "
                "Для защиты аккаунта подтвердите email."
            )
        else:
            detail = "Пользователь зарегистрирован. Теперь можно войти в аккаунт."

        return {
            "id": instance.id,
            "username": instance.username,
            "email": instance.email,
            "is_active": instance.is_active,
            "isEmailVerified": is_email_verified(instance),
            "emailVerificationRequired": email_verification_required(instance),
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

        attrs["user"] = user
        return attrs

    def save(self, **kwargs):
        user = self.validated_data["user"]
        self._already_verified = bool(user.email_verified)

        if user.email_verified:
            return user

        user.is_active = True
        user.email_verified = True
        user.email_verified_at = timezone.now()
        user.save(update_fields=["is_active", "email_verified", "email_verified_at"])

        return user

    def to_representation(self, instance):
        detail = (
            EMAIL_ALREADY_CONFIRMED_MESSAGE
            if getattr(self, "_already_verified", False)
            else "Email подтверждён."
        )

        return {
            "id": instance.id,
            "email": instance.email,
            "is_active": instance.is_active,
            "isEmailVerified": bool(instance.email_verified),
            "emailVerificationRequired": email_verification_required(instance),
            "detail": detail,
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

        ensure_verified_contact(user)

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
            raise PasswordResetTokenInvalid()

        if token_record.is_used:
            raise PasswordResetTokenAlreadyUsed()

        if token_record.is_expired:
            raise PasswordResetTokenExpired()

        ensure_verified_contact(token_record.user)

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
                raise PasswordResetTokenAlreadyUsed()

            if locked_token_record.is_expired:
                raise PasswordResetTokenExpired()

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


class ResendEmailVerificationSerializer(serializers.Serializer):
    detail = serializers.CharField(read_only=True)
    queued = serializers.BooleanField(read_only=True)

    def save(self, **kwargs):
        request = self.context["request"]
        user = request.user

        result = request_email_confirmation(user, force=False)
        return {
            "detail": result.get("detail") or EMAIL_CONFIRMATION_ACCEPTED_MESSAGE,
            "queued": bool(result.get("queued", False)),
        }

    def to_representation(self, instance):
        return instance


class ChangePasswordSerializer(serializers.Serializer):
    currentPassword = serializers.CharField(write_only=True, trim_whitespace=False)
    newPassword = serializers.CharField(write_only=True, trim_whitespace=False, min_length=8)
    newPasswordConfirm = serializers.CharField(write_only=True, trim_whitespace=False, min_length=8)
    detail = serializers.CharField(read_only=True)

    def validate(self, attrs):
        request = self.context["request"]
        user = request.user

        ensure_verified_contact(user)

        current_password = attrs.get("currentPassword")
        new_password = attrs.get("newPassword")
        new_password_confirm = attrs.get("newPasswordConfirm")

        if not user.check_password(current_password):
            raise ValidationError(
                {
                    "currentPassword": [
                        serializers.ErrorDetail(
                            "Неверный текущий пароль.",
                            code="invalid_password",
                        )
                    ]
                }
            )

        if new_password != new_password_confirm:
            raise ValidationError(
                {
                    "newPasswordConfirm": [
                        serializers.ErrorDetail(
                            "Пароли не совпадают.",
                            code="password_mismatch",
                        )
                    ]
                }
            )

        validate_password(new_password, user=user)
        return attrs

    def save(self, **kwargs):
        user = self.context["request"].user
        user.set_password(self.validated_data["newPassword"])
        user.save(update_fields=["password"])
        return {"detail": "Пароль успешно изменён."}

    def to_representation(self, instance):
        return instance


class ChangeEmailSerializer(serializers.Serializer):
    newEmail = serializers.EmailField(write_only=True)
    currentPassword = serializers.CharField(write_only=True, trim_whitespace=False)

    id = serializers.IntegerField(read_only=True)
    email = serializers.EmailField(read_only=True)
    isEmailVerified = serializers.BooleanField(read_only=True)
    emailVerificationRequired = serializers.BooleanField(read_only=True)
    detail = serializers.CharField(read_only=True)

    def validate_newEmail(self, value: str) -> str:
        normalized_email = value.strip().lower()

        user = self.context["request"].user
        if normalized_email == str(user.email).lower():
            raise serializers.ValidationError(
                "Новый email совпадает с текущим.",
                code="same_email",
            )

        if User.objects.filter(email__iexact=normalized_email).exclude(pk=user.pk).exists():
            raise serializers.ValidationError(
                "Пользователь с таким email уже существует.",
                code="unique",
            )

        return normalized_email

    def validate(self, attrs):
        user = self.context["request"].user
        ensure_verified_contact(user)

        if not user.check_password(attrs.get("currentPassword")):
            raise ValidationError(
                {
                    "currentPassword": [
                        serializers.ErrorDetail(
                            "Неверный текущий пароль.",
                            code="invalid_password",
                        )
                    ]
                }
            )

        return attrs

    def save(self, **kwargs):
        request = self.context["request"]
        user = request.user
        old_email = user.email
        new_email = self.validated_data["newEmail"]

        with transaction.atomic():
            locked_user = User.objects.select_for_update().get(pk=user.pk)
            locked_user.email = new_email
            locked_user.email_verified = False
            locked_user.email_verified_at = None
            locked_user.save(update_fields=["email", "email_verified", "email_verified_at"])

            log_profile_audit_event(
                user=locked_user,
                action=UserProfileAuditAction.EMAIL_CHANGED,
                changed_fields=["email"],
                old_values={"email": old_email},
                new_values={"email": new_email},
                metadata={"source": "auth_change_email_api"},
                request=request,
            )

        try:
            request_email_confirmation(locked_user, force=True)
        except Exception:
            logger.exception(
                "Email changed, but email confirmation sending failed. user_id=%s",
                locked_user.id,
            )

        return locked_user

    def to_representation(self, instance):
        return {
            "id": instance.id,
            "email": instance.email,
            "isEmailVerified": is_email_verified(instance),
            "emailVerificationRequired": email_verification_required(instance),
            "detail": "Email изменён. Подтвердите новый email по ссылке из письма.",
        }


class LoginUserSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(read_only=True)
    email = serializers.EmailField(read_only=True)
    first_name = serializers.CharField(read_only=True, allow_blank=True)
    last_name = serializers.CharField(read_only=True, allow_blank=True)
    role = serializers.CharField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    isEmailVerified = serializers.BooleanField(read_only=True)
    isPhoneVerified = serializers.BooleanField(read_only=True)
    emailVerificationRequired = serializers.BooleanField(read_only=True)
    hasVerifiedContact = serializers.BooleanField(read_only=True)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(write_only=True)
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    access = serializers.CharField(read_only=True)
    refresh = serializers.CharField(read_only=True)
    user = LoginUserSerializer(read_only=True)

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
                "isEmailVerified": is_email_verified(authenticated_user),
                "isPhoneVerified": is_phone_verified(authenticated_user),
                "emailVerificationRequired": email_verification_required(authenticated_user),
                "hasVerifiedContact": has_verified_contact(authenticated_user),
            },
        }

    def _get_role(self, user) -> str:
        if user.is_superuser:
            return "admin"

        if user.is_staff:
            return "staff"

        return "user"

LOGOUT_SUCCESS_MESSAGE = "Выход выполнен. Refresh token добавлен в blacklist."


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField(write_only=True, trim_whitespace=False)
    detail = serializers.CharField(read_only=True)

    default_error_messages = {
        "invalid_token": "Недействительный refresh token.",
    }

    def validate_refresh(self, value):
        try:
            self.refresh_token = RefreshToken(value)
        except TokenError:
            raise serializers.ValidationError(
                serializers.ErrorDetail(
                    self.error_messages["invalid_token"],
                    code="invalid_token",
                )
            )

        return value

    def save(self, **kwargs):
        refresh_token = getattr(self, "refresh_token", None)

        if refresh_token is None:
            try:
                refresh_token = RefreshToken(self.validated_data["refresh"])
            except TokenError:
                raise ValidationError(
                    {
                        "refresh": [
                            serializers.ErrorDetail(
                                self.error_messages["invalid_token"],
                                code="invalid_token",
                            )
                        ]
                    }
                )

        try:
            refresh_token.blacklist()
        except AttributeError:
            logger.exception(
                "JWT logout failed because token blacklist app is not available."
            )
            raise ValidationError(
                {
                    "refresh": [
                        serializers.ErrorDetail(
                            self.error_messages["invalid_token"],
                            code="invalid_token",
                        )
                    ]
                }
            )
        except TokenError:
            raise ValidationError(
                {
                    "refresh": [
                        serializers.ErrorDetail(
                            self.error_messages["invalid_token"],
                            code="invalid_token",
                        )
                    ]
                }
            )

        request = self.context.get("request")

        logger.info(
            "User logged out. user_id=%s client_ip=%s",
            getattr(getattr(request, "user", None), "id", None),
            self._get_client_ip(request),
        )

        return {
            "detail": LOGOUT_SUCCESS_MESSAGE,
        }

    def to_representation(self, instance):
        return {
            "detail": LOGOUT_SUCCESS_MESSAGE,
        }

    def _get_client_ip(self, request) -> str | None:
        if request is None:
            return None

        forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")

        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        return request.META.get("REMOTE_ADDR")

