from django.urls import path
from apps.users.auth_views import (
    ForgotPasswordView,
    BudgetWiseTokenRefreshView,
    LoginView,
    RegisterView,
    ResetPasswordView,
    VerifyEmailView,
)


app_name = "auth"

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("token/refresh/", BudgetWiseTokenRefreshView.as_view(), name="token-refresh"),
    path("verify-email/", VerifyEmailView.as_view(), name="verify-email"),
    path("reset-password/", ResetPasswordView.as_view(), name="reset-password"),
    path(
        "forgot-password/check/",
        ForgotPasswordView.as_view(),
        name="forgot-password-check",
    ),
]
