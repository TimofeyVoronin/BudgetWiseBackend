from django.urls import include, path

from apps.common.api_root_views import APIRootView
from apps.users.profile.views import HomeGreetingView


urlpatterns = [
    path("", APIRootView.as_view(), name="api-root"),
    path("auth/", include("apps.users.auth.urls")),
    path("me/", HomeGreetingView.as_view(), name="home-greeting"),
    path("profile/", include("apps.users.profile.urls")),
    path("settings/app/", include("apps.users.app_settings.urls")),
    path("users/", include("apps.users.urls")),
    path("finance/", include("apps.finance.urls")),
]
