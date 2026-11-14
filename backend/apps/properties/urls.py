from django.urls import path

from apps.properties import views

app_name = "properties"

urlpatterns = [
    path("properties/", views.PropertyListCreateView.as_view(), name="list"),
    path("properties/<uuid:property_id>/", views.PropertyDetailView.as_view(), name="detail"),
    path(
        "properties/<uuid:property_id>/photos/",
        views.PropertyPhotoListView.as_view(),
        name="photos",
    ),
    path(
        "properties/<uuid:property_id>/photos/<uuid:photo_id>/",
        views.PropertyPhotoDetailView.as_view(),
        name="photo",
    ),
    path(
        "properties/<uuid:property_id>/verification/",
        views.PropertyVerificationView.as_view(),
        name="verification",
    ),
    path(
        "properties/<uuid:property_id>/public/",
        views.PublicPropertyView.as_view(),
        name="public",
    ),
]
