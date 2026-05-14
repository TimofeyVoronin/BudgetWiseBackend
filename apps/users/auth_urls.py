from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from apps.users.views import (
    ForgotPasswordView,
    LoginView,
    RegisterView,
    VerifyEmailView,
)


app_name = "auth"

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("verify-email/", VerifyEmailView.as_view(), name="verify-email"),
    path(
        "forgot-password/check/",
        ForgotPasswordView.as_view(),
        name="forgot-password-check",
    ),
]