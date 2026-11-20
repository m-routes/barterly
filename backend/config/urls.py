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
    path("api/v1/", include("apps.geo.urls")),
    path("api/v1/", include("apps.properties.urls")),
    path("api/v1/", include("apps.verification.urls")),
    path("api/v1/", include("apps.discovery.urls")),
    path("api/v1/", include("apps.gigs.urls")),
    path("api/v1/", include("apps.applications.urls")),
    path("api/v1/", include("apps.bookings.urls")),
    path("api/v1/", include("apps.hiring.urls")),
    path("api/v1/", include("apps.chat.urls")),
    path("api/v1/", include("apps.offers.urls")),
    path("api/v1/", include("apps.agreements.urls")),
    path("api/v1/", include("apps.reliability.urls")),
    path("api/v1/", include("apps.notifications.urls")),
    path("api/v1/", include("apps.billing.urls")),
    path("api/v1/", include("apps.money.urls")),
    path("api/v1/", include("apps.attendance.urls")),
    path("api/v1/", include("apps.deliverables.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
]

if settings.API_DOCS_ENABLED:
    urlpatterns.append(
        path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui")
    )
