"""Django-level 404/500 handlers. API paths get the JSON error shape; others the default page."""

from django.http import JsonResponse
from django.views import defaults

from apps.common.exceptions import SERVER_ERROR_MESSAGE, error_body


def _is_api(request) -> bool:
    return request.path.startswith("/api/")


def not_found(request, exception=None):
    if _is_api(request):
        return JsonResponse(error_body("not_found", "Not found."), status=404)
    return defaults.page_not_found(request, exception)


def server_error(request):
    if _is_api(request):
        return JsonResponse(error_body("server_error", SERVER_ERROR_MESSAGE), status=500)
    return defaults.server_error(request)
