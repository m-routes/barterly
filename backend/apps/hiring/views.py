from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import extend_schema
from rest_framework import exceptions, generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.applications.models import Application
from apps.common.permissions import IsTalent, IsVendor
from apps.common.serializers import ErrorSerializer
from apps.gigs.models import Gig
from apps.hiring import autoreject, services
from apps.hiring.interview_serializers import InterviewSerializer
from apps.hiring.models import ApplicationNote, SavedApplicantFilter
from apps.hiring.serializers import (
    BulkResultSerializer,
    BulkSerializer,
    NoteInSerializer,
    NoteSerializer,
    PickSlotSerializer,
    ProposeInterviewSerializer,
    ReasonSerializer,
    RulesSerializer,
    SavedFilterSerializer,
    TagsSerializer,
    reasons,
)

TAG = ["hiring"]
ERRORS = {401: ErrorSerializer, 403: ErrorSerializer, 404: ErrorSerializer}


class Refused(exceptions.APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "hiring_refused"


def vendor_application(user, application_id) -> Application:
    return generics.get_object_or_404(
        Application.objects.select_related("gig"), pk=application_id, gig__vendor=user
    )


def vendor_gig(user, gig_id) -> Gig:
    return generics.get_object_or_404(Gig, pk=gig_id, vendor=user)


class RejectionReasonsView(APIView):
    permission_classes = [IsVendor]

    @extend_schema(
        operation_id="hiring_rejection_reasons",
        summary="Rejection reasons to choose from",
        responses={200: ReasonSerializer(many=True), **ERRORS},
        tags=TAG,
    )
    def get(self, request: Request) -> Response:
        return Response(ReasonSerializer(reasons(), many=True).data)


class BulkView(APIView):
    permission_classes = [IsVendor]

    @extend_schema(
        operation_id="hiring_bulk",
        summary="Shortlist or reject many applicants",
        description=(
            "Each application is changed on its own; the results say which worked and "
            "why the others didn't (e.g. already rejected). Rejecting needs a reason_code."
        ),
        request=BulkSerializer,
        responses={200: BulkResultSerializer(many=True), **ERRORS},
        tags=TAG,
    )
    def post(self, request: Request, gig_id) -> Response:
        gig = vendor_gig(request.user, gig_id)
        serializer = BulkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        results = services.bulk(
            gig,
            data["application_ids"],
            data["action"],
            vendor=request.user,
            code=data.get("reason_code", ""),
            message=data.get("message", ""),
            request=request,
        )
        return Response(BulkResultSerializer([r.__dict__ for r in results], many=True).data)


class NotesView(APIView):
    permission_classes = [IsVendor]

    @extend_schema(
        operation_id="hiring_notes_list",
        summary="My private notes on an applicant",
        description="Only the gig's vendor sees these. The applicant never does.",
        responses={200: NoteSerializer(many=True), **ERRORS},
        tags=TAG,
    )
    def get(self, request: Request, application_id) -> Response:
        application = vendor_application(request.user, application_id)
        notes = application.private_notes.select_related("author")
        return Response(NoteSerializer(notes, many=True).data)

    @extend_schema(
        operation_id="hiring_notes_create",
        summary="Add a private note",
        request=NoteSerializer,
        responses={201: NoteSerializer, 400: ErrorSerializer, **ERRORS},
        tags=TAG,
    )
    def post(self, request: Request, application_id) -> Response:
        application = vendor_application(request.user, application_id)
        serializer = NoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            note = services.add_note(
                application, author=request.user, body=serializer.validated_data["body"]
            )
        except services.HiringError as exc:
            raise exceptions.ValidationError({"body": [str(exc)]}) from exc
        return Response(NoteSerializer(note).data, status=status.HTTP_201_CREATED)


class NoteDetailView(APIView):
    permission_classes = [IsVendor]

    @extend_schema(
        operation_id="hiring_notes_delete",
        summary="Delete my private note",
        responses={204: None, **ERRORS},
        tags=TAG,
    )
    def delete(self, request: Request, application_id, note_id) -> Response:
        application = vendor_application(request.user, application_id)
        note = generics.get_object_or_404(
            ApplicationNote, pk=note_id, application=application, author=request.user
        )
        note.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TagsView(APIView):
    permission_classes = [IsVendor]

    @extend_schema(
        operation_id="hiring_tags_set",
        summary="Set my private tags on an applicant",
        description="Replaces the tags. Lower-cased; at most 10. The applicant never sees them.",
        request=TagsSerializer,
        responses={200: TagsSerializer, 400: ErrorSerializer, **ERRORS},
        tags=TAG,
    )
    def put(self, request: Request, application_id) -> Response:
        application = vendor_application(request.user, application_id)
        serializer = TagsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            tags = services.set_tags(application, serializer.validated_data["tags"])
        except services.HiringError as exc:
            raise exceptions.ValidationError({"tags": [str(exc)]}) from exc
        return Response({"tags": tags})


class SavedFiltersView(generics.ListCreateAPIView):
    permission_classes = [IsVendor]
    serializer_class = SavedFilterSerializer
    pagination_class = None

    def get_queryset(self):
        return SavedApplicantFilter.objects.filter(vendor=self.request.user)

    def perform_create(self, serializer):
        if self.get_queryset().filter(name=serializer.validated_data["name"]).exists():
            raise exceptions.ValidationError(
                {"name": ["You already have a filter with that name."]}
            )
        serializer.save(vendor=self.request.user)

    @extend_schema(
        operation_id="hiring_filters_list", summary="My saved applicant filters", tags=TAG
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)

    @extend_schema(
        operation_id="hiring_filters_create", summary="Save an applicant filter", tags=TAG
    )
    def post(self, request: Request, *args, **kwargs) -> Response:
        return super().post(request, *args, **kwargs)


class SavedFilterDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsVendor]
    serializer_class = SavedFilterSerializer
    lookup_url_kwarg = "filter_id"
    http_method_names = ["get", "patch", "delete", "options"]

    def get_queryset(self):
        return SavedApplicantFilter.objects.filter(vendor=self.request.user)

    @extend_schema(operation_id="hiring_filters_retrieve", summary="One saved filter", tags=TAG)
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)

    @extend_schema(
        operation_id="hiring_filters_update", summary="Rename or change a filter", tags=TAG
    )
    def patch(self, request: Request, *args, **kwargs) -> Response:
        return super().patch(request, *args, **kwargs)

    @extend_schema(operation_id="hiring_filters_delete", summary="Delete a saved filter", tags=TAG)
    def delete(self, request: Request, *args, **kwargs) -> Response:
        return super().delete(request, *args, **kwargs)


class AutoRejectRulesView(APIView):
    permission_classes = [IsVendor]

    @extend_schema(
        operation_id="hiring_rules_retrieve",
        summary="A gig's auto-reject rules",
        responses={200: RulesSerializer, **ERRORS},
        tags=TAG,
    )
    def get(self, request: Request, gig_id) -> Response:
        gig = vendor_gig(request.user, gig_id)
        return Response({"rules": gig.auto_reject_rules})

    @extend_schema(
        operation_id="hiring_rules_set",
        summary="Set a gig's auto-reject rules",
        description=(
            "Checked when someone applies: an application that misses a rule is rejected "
            "at once, and the applicant is told which requirement they missed. Types: "
            "language (languages), skill (skills), min_followers (value), min_stay_days "
            "(value)."
        ),
        request=RulesSerializer,
        responses={200: RulesSerializer, 400: ErrorSerializer, **ERRORS},
        tags=TAG,
    )
    def put(self, request: Request, gig_id) -> Response:
        gig = vendor_gig(request.user, gig_id)
        serializer = RulesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            rules = autoreject.clean_rules(request.data.get("rules", []))
        except DjangoValidationError as exc:
            raise exceptions.ValidationError({"rules": exc.messages}) from exc
        gig.auto_reject_rules = rules
        gig.save(update_fields=["auto_reject_rules", "updated_at"])
        return Response({"rules": rules})


class InterviewView(APIView):
    permission_classes = [IsAuthenticated]

    def _application(self, request, application_id) -> Application:
        application = generics.get_object_or_404(
            Application.objects.select_related("gig"), pk=application_id
        )
        if request.user.pk not in (application.talent_id, application.gig.vendor_id):
            raise exceptions.NotFound("No such application.")
        return application

    @extend_schema(
        operation_id="hiring_interview_retrieve",
        summary="The interview being arranged (applicant or vendor)",
        description="Times are UTC (ISO 8601) with India-time text alongside.",
        responses={200: InterviewSerializer, **ERRORS},
        tags=TAG,
    )
    def get(self, request: Request, application_id) -> Response:
        interview = services.active_interview(self._application(request, application_id))
        if interview is None:
            raise exceptions.NotFound("No interview is being arranged.")
        return Response(InterviewSerializer(interview).data)

    @extend_schema(
        operation_id="hiring_interview_propose",
        summary="Propose interview times (vendor)",
        description=(
            "Up to three times, at least an hour ahead and within 60 days, plus a video "
            "link. Moves the application to the interview stage if it isn't there yet, "
            "and replaces an interview still being arranged."
        ),
        request=ProposeInterviewSerializer,
        responses={201: InterviewSerializer, 409: ErrorSerializer, **ERRORS},
        tags=TAG,
    )
    def post(self, request: Request, application_id) -> Response:
        if not IsVendor().has_permission(request, self):
            raise exceptions.PermissionDenied("Only vendors propose interviews.")
        vendor_application(request.user, application_id)
        serializer = ProposeInterviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            interview = services.propose_interview(
                application_id,
                vendor=request.user,
                slots=data["slots"],
                video_link=data["video_link"],
                duration_minutes=data["duration_minutes"],
                note=data.get("note", ""),
                request=request,
            )
        except services.HiringError as exc:
            raise Refused(str(exc)) from exc
        return Response(InterviewSerializer(interview).data, status=status.HTTP_201_CREATED)


class PickSlotView(APIView):
    permission_classes = [IsTalent]

    @extend_schema(
        operation_id="hiring_interview_pick",
        summary="Pick an interview time (applicant)",
        request=PickSlotSerializer,
        responses={200: InterviewSerializer, 409: ErrorSerializer, **ERRORS},
        tags=TAG,
    )
    def post(self, request: Request, application_id) -> Response:
        serializer = PickSlotSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            interview = services.pick_slot(
                application_id,
                serializer.validated_data["slot_id"],
                talent=request.user,
                request=request,
            )
        except Application.DoesNotExist as exc:
            raise exceptions.NotFound("No such application.") from exc
        except services.HiringError as exc:
            raise Refused(str(exc)) from exc
        return Response(InterviewSerializer(interview).data)


class NewTimesView(APIView):
    permission_classes = [IsTalent]

    @extend_schema(
        operation_id="hiring_interview_new_times",
        summary="Ask for other interview times (applicant)",
        request=NoteInSerializer,
        responses={200: InterviewSerializer, 409: ErrorSerializer, **ERRORS},
        tags=TAG,
    )
    def post(self, request: Request, application_id) -> Response:
        serializer = NoteInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            interview = services.request_new_times(
                application_id,
                talent=request.user,
                note=serializer.validated_data.get("note", ""),
                request=request,
            )
        except Application.DoesNotExist as exc:
            raise exceptions.NotFound("No such application.") from exc
        except services.HiringError as exc:
            raise Refused(str(exc)) from exc
        return Response(InterviewSerializer(interview).data)


class CancelInterviewView(APIView):
    permission_classes = [IsVendor]

    @extend_schema(
        operation_id="hiring_interview_cancel",
        summary="Cancel the interview (vendor)",
        request=NoteInSerializer,
        responses={200: InterviewSerializer, 409: ErrorSerializer, **ERRORS},
        tags=TAG,
    )
    def post(self, request: Request, application_id) -> Response:
        serializer = NoteInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            interview = services.cancel_interview(
                application_id,
                vendor=request.user,
                reason=serializer.validated_data.get("note", ""),
                request=request,
            )
        except Application.DoesNotExist as exc:
            raise exceptions.NotFound("No such application.") from exc
        except services.HiringError as exc:
            raise Refused(str(exc)) from exc
        return Response(InterviewSerializer(interview).data)
