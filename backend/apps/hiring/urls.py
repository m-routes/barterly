from django.urls import path

from apps.hiring import views

app_name = "hiring"

A = "applications/<uuid:application_id>/"

urlpatterns = [
    path("hiring/rejection-reasons/", views.RejectionReasonsView.as_view(), name="reasons"),
    path("gigs/<uuid:gig_id>/applications/bulk/", views.BulkView.as_view(), name="bulk"),
    path(
        "gigs/<uuid:gig_id>/auto-reject-rules/", views.AutoRejectRulesView.as_view(), name="rules"
    ),
    path(f"{A}notes/", views.NotesView.as_view(), name="notes"),
    path(f"{A}notes/<uuid:note_id>/", views.NoteDetailView.as_view(), name="note"),
    path(f"{A}tags/", views.TagsView.as_view(), name="tags"),
    path(f"{A}interview/", views.InterviewView.as_view(), name="interview"),
    path(f"{A}interview/pick/", views.PickSlotView.as_view(), name="interview-pick"),
    path(f"{A}interview/new-times/", views.NewTimesView.as_view(), name="interview-new-times"),
    path(f"{A}interview/cancel/", views.CancelInterviewView.as_view(), name="interview-cancel"),
    path("applicant-filters/", views.SavedFiltersView.as_view(), name="filters"),
    path(
        "applicant-filters/<uuid:filter_id>/", views.SavedFilterDetailView.as_view(), name="filter"
    ),
]
