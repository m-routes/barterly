from django.urls import path

from apps.gigs import views

app_name = "gigs"

urlpatterns = [
    path("gigs/", views.GigCollectionView.as_view(), name="collection"),
    path("gigs/mine/", views.MyGigsView.as_view(), name="mine"),
    path("gigs/admin/", views.AdminGigListView.as_view(), name="admin-list"),
    path("gigs/<uuid:gig_id>/", views.GigDetailView.as_view(), name="detail"),
    path("gigs/<uuid:gig_id>/public/", views.GigPublicView.as_view(), name="public"),
    path("gigs/<uuid:gig_id>/status/", views.GigStatusView.as_view(), name="status"),
]
