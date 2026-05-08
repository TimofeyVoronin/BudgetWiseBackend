from rest_framework.permissions import BasePermission


class IsObjectOwner(BasePermission):
    message = "У вас нет доступа к этому объекту."

    def has_object_permission(self, request, view, obj):
        return hasattr(obj, "user_id") and obj.user_id == request.user.id