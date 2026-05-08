from django.urls import include, path

from apps.common.views import APIRootView


urlpatterns = [
    path("", APIRootView.as_view(), name="api-root"),
    path("users/", include("apps.users.urls")),
    path("finance/", include("apps.finance.urls")),
]