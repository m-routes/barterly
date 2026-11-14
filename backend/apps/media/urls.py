from django.urls import path

from apps.media.views import ConfirmView, MediaDetailView, UploadUrlView

app_name = "media"

urlpatterns = [
    path("media/upload-url/", UploadUrlView.as_view(), name="upload-url"),
    path("media/confirm/", ConfirmView.as_view(), name="confirm"),
    path("media/<uuid:media_id>/", MediaDetailView.as_view(), name="detail"),
]
