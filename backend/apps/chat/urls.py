from django.urls import path

from apps.chat import views

app_name = "chat"

C = "conversations/<uuid:conversation_id>/"

urlpatterns = [
    path("conversations/", views.ConversationListView.as_view(), name="list"),
    path("conversations/unread/", views.UnreadView.as_view(), name="unread"),
    path(C, views.ConversationDetailView.as_view(), name="detail"),
    path(f"{C}messages/", views.MessagesView.as_view(), name="messages"),
    path(f"{C}read/", views.ReadView.as_view(), name="read"),
    path(f"{C}block/", views.BlockView.as_view(), name="block"),
    path(
        "applications/<uuid:application_id>/conversation/",
        views.OpenConversationView.as_view(),
        name="open",
    ),
    path("messages/<uuid:message_id>/report/", views.ReportView.as_view(), name="report"),
]
