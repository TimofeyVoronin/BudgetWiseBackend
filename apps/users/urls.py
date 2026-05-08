from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.users.views import CurrentUserView, UserViewSet


app_name = "users"

router = DefaultRouter()
router.register("", UserViewSet, basename="user")

urlpatterns = [
    path("me/", CurrentUserView.as_view(), name="current-user"),
    path("", include(router.urls)),
]