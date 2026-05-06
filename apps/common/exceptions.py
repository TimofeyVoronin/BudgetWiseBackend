from rest_framework.views import exception_handler


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is None:
        return response

    response.data = {
        "success": False,
        "error": {
            "status_code": response.status_code,
            "detail": response.data,
        },
    }

    return response