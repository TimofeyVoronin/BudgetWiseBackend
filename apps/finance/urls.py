from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.finance.views import CategoryViewSet, TransactionViewSet


app_name = "finance"

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("transactions", TransactionViewSet, basename="transaction")

urlpatterns = [
    path("", include(router.urls)),
]