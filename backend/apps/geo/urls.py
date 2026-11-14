from django.urls import path

from apps.geo.views import GeocodeView

app_name = "geo"

urlpatterns = [path("geo/geocode/", GeocodeView.as_view(), name="geocode")]
