from django.urls import path
from apps.users.auth.views import (
    ChangeEmailView,
    ChangePasswordView,
    ForgotPasswordView,
    BudgetWiseTokenRefreshView,
    LoginView,
    LogoutView,
    RegisterView,
    ResendEmailVerificationView,
    ResetPasswordView,
    VerifyEmailView,
)


app_name = "auth"

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("token/refresh/", BudgetWiseTokenRefreshView.as_view(), name="token-refresh"),
    path("verify-email/", VerifyEmailView.as_view(), name="verify-email"),
    path(
        "verify-email/resend/",
        ResendEmailVerificationView.as_view(),
        name="verify-email-resend",
    ),
    path("change-password/", ChangePasswordView.as_view(), name="change-password"),
    path("change-email/", ChangeEmailView.as_view(), name="change-email"),
    path("reset-password/", ResetPasswordView.as_view(), name="reset-password"),
    path(
        "forgot-password/check/",
        ForgotPasswordView.as_view(),
        name="forgot-password-check",
    ),
]
