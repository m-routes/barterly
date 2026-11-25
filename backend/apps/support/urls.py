from django.urls import path

from apps.support import views

app_name = "support"

urlpatterns = [
    path("support/tickets/", views.TicketListView.as_view(), name="tickets"),
    path("support/tickets/<uuid:ticket_id>/", views.TicketDetailView.as_view(), name="ticket"),
    path(
        "support/tickets/<uuid:ticket_id>/messages/",
        views.TicketReplyView.as_view(),
        name="ticket-reply",
    ),
]
