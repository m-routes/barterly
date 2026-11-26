from django.urls import path

from apps.offers import views

app_name = "offers"

urlpatterns = [
    path(
        "applications/<uuid:application_id>/offers/",
        views.OfferThreadView.as_view(),
        name="thread",
    ),
    path(
        "applications/<uuid:application_id>/offer-draft/",
        views.OfferDraftView.as_view(),
        name="draft",
    ),
    path(
        "applications/<uuid:application_id>/offer/",
        views.MakeOfferView.as_view(),
        name="make",
    ),
    path("offers/<uuid:offer_id>/accept/", views.AcceptView.as_view(), name="accept"),
    path("offers/<uuid:offer_id>/decline/", views.DeclineView.as_view(), name="decline"),
    path("offers/<uuid:offer_id>/counter/", views.CounterView.as_view(), name="counter"),
]
