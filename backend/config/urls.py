from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

handler404 = "apps.common.views.not_found"
handler500 = "apps.common.views.server_error"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("apps.core.urls")),
    path("api/v1/", include("apps.accounts.urls")),
    path("api/v1/", include("apps.profiles.urls")),
    path("api/v1/", include("apps.media.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
]

if settings.API_DOCS_ENABLED:
    urlpatterns.append(
        path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui")
    )
