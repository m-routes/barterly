from django.urls import path

from apps.reliability import views

app_name = "reliability"

urlpatterns = [
    path("reliability/me/", views.MyReliabilityView.as_view(), name="me"),
]
