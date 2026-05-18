from django.urls import include, path

from apps.common.api_root_views import APIRootView


urlpatterns = [
    path("", APIRootView.as_view(), name="api-root"),
    path("auth/", include("apps.users.auth_urls")),
    path("users/", include("apps.users.urls")),
    path("finance/", include("apps.finance.urls")),
]
