from django.urls import include, path
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([AllowAny])
def api_root(request):
    return Response(
        {
            "service": "BudgetWiseBackend API",
            "version": "v1",
            "endpoints": {
                "users": "/api/v1/users/",
                "finance": "/api/v1/finance/",
                "schema": "/api/schema/",
                "docs": "/api/docs/",
                "health": "/health/",
            },
        }
    )


urlpatterns = [
    path("", api_root, name="api-root"),
    path("users/", include("apps.users.urls")),
    path("finance/", include("apps.finance.urls")),
]