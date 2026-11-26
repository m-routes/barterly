"""Offers: the host sends terms, the talent accepts, declines or asks for one change."""

from drf_spectacular.utils import extend_schema
from rest_framework import exceptions, generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.applications.models import Application
from apps.common.permissions import IsTalent, IsVendor
from apps.common.serializers import ErrorSerializer
from apps.offers import services
from apps.offers import terms as offer_terms
from apps.offers.models import Offer
from apps.offers.serializers import (
    AcceptedSerializer,
    AnswerSerializer,
    CounterSerializer,
    MakeOfferSerializer,
    OfferThreadSerializer,
    raw_object,
    thread,
)

TAG = ["offers"]
ERRORS = {401: ErrorSerializer, 403: ErrorSerializer, 404: ErrorSerializer}


class OfferRefused(exceptions.APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "offer_refused"


def refuse(exc: services.OfferError):
    error = OfferRefused(exc.message)
    error.status_code = exc.status
    return error


def _application(user, application_id) -> Application:
    from django.db.models import Q

    qs = Application.objects.select_related("gig").filter(Q(talent=user) | Q(gig__vendor=user))
    return generics.get_object_or_404(qs, pk=application_id)


def _thread_response(request, application, code=status.HTTP_200_OK) -> Response:
    offers = services.offers_for(application.pk).select_related("counter_of")
    data = OfferThreadSerializer(
        thread(application, request.user, offers), context={"request": request}
    ).data
    return Response(data, status=code)


def _offer_application(user, offer_id) -> Application:
    application_id = (
        Offer.objects.filter(pk=offer_id).values_list("application_id", flat=True).first()
    )
    if application_id is None:
        raise exceptions.NotFound("No such offer.")
    return _application(user, application_id)


class OfferThreadView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="offers_thread",
        summary="Offers on an application",
        description="Every offer and counter, oldest first, for the talent or the host.",
        responses={200: OfferThreadSerializer, **ERRORS},
        tags=TAG,
    )
    def get(self, request: Request, application_id) -> Response:
        return _thread_response(request, _application(request.user, application_id))


class OfferDraftView(APIView):
    permission_classes = [IsVendor]

    @extend_schema(
        operation_id="offers_draft",
        summary="Terms to start an offer from",
        description="The gig's terms with the applicant's dates. Edit them, then make the offer.",
        responses={200: offer_terms.TermsSerializer, **ERRORS},
        tags=TAG,
    )
    def get(self, request: Request, application_id) -> Response:
        application = generics.get_object_or_404(
            Application.objects.select_related("gig"), pk=application_id, gig__vendor=request.user
        )
        return Response(offer_terms.TermsSerializer(offer_terms.draft_for(application)).data)


class MakeOfferView(APIView):
    permission_classes = [IsVendor]

    @extend_schema(
        operation_id="offers_make",
        summary="Make an offer",
        description=(
            "Sends the terms to the applicant, frozen. The application becomes offered and "
            "the talent has 48 hours to accept, decline or ask for one change. Needs an "
            "open slot on a running gig."
        ),
        request=MakeOfferSerializer,
        responses={
            201: OfferThreadSerializer,
            400: ErrorSerializer,
            409: ErrorSerializer,
            **ERRORS,
        },
        tags=TAG,
    )
    def post(self, request: Request, application_id) -> Response:
        terms = raw_object(request.data, "terms")
        message = AnswerSerializer(data={"reason": request.data.get("message", "")})
        message.is_valid(raise_exception=True)
        try:
            services.make_offer(
                application_id,
                vendor=request.user,
                terms=terms,
                message=message.validated_data.get("reason", ""),
                request=request,
            )
        except Application.DoesNotExist as exc:
            raise exceptions.NotFound("No such application.") from exc
        except services.OfferError as exc:
            raise refuse(exc) from exc
        application = _application(request.user, application_id)
        return _thread_response(request, application, status.HTTP_201_CREATED)


class AcceptView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="offers_accept",
        summary="Accept an offer",
        description=(
            "Accept the open offer addressed to you: the talent accepts the host's offer, the "
            "host accepts the talent's counter. Books the slot and draws up version 1 of the "
            "agreement, for both of you to sign."
        ),
        request=None,
        responses={201: AcceptedSerializer, 409: ErrorSerializer, **ERRORS},
        tags=TAG,
    )
    def post(self, request: Request, offer_id) -> Response:
        _offer_application(request.user, offer_id)
        try:
            booking = services.accept(offer_id, user=request.user, request=request)
        except Offer.DoesNotExist as exc:
            raise exceptions.NotFound("No such offer.") from exc
        except services.OfferError as exc:
            raise refuse(exc) from exc
        version = booking.agreement.versions.get(number=1)
        return Response(
            AcceptedSerializer({"booking": booking.pk, "agreement_version": version.pk}).data,
            status=status.HTTP_201_CREATED,
        )


class DeclineView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="offers_decline",
        summary="Decline an offer",
        description=(
            "Say no to the open offer addressed to you. The talent declining ends the "
            "application. The host declining the talent's counter sends the original terms "
            "back as a final offer, which the talent can only accept or decline."
        ),
        request=AnswerSerializer,
        responses={200: OfferThreadSerializer, 409: ErrorSerializer, **ERRORS},
        tags=TAG,
    )
    def post(self, request: Request, offer_id) -> Response:
        application = _offer_application(request.user, offer_id)
        serializer = AnswerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            services.decline(
                offer_id,
                user=request.user,
                reason=serializer.validated_data.get("reason", ""),
                request=request,
            )
        except Offer.DoesNotExist as exc:
            raise exceptions.NotFound("No such offer.") from exc
        except services.OfferError as exc:
            raise refuse(exc) from exc
        application.refresh_from_db()
        return _thread_response(request, application)


class CounterView(APIView):
    permission_classes = [IsTalent]

    @extend_schema(
        operation_id="offers_counter",
        summary="Ask for a change",
        description=(
            "Once per application, the talent proposes different terms: only the dates, "
            "hours, stipend, deliverables and usage rights. The host accepts the change "
            "(which books it) or declines it (the original terms come back as a final offer)."
        ),
        request=CounterSerializer,
        responses={
            201: OfferThreadSerializer,
            400: ErrorSerializer,
            409: ErrorSerializer,
            **ERRORS,
        },
        tags=TAG,
    )
    def post(self, request: Request, offer_id) -> Response:
        application = _offer_application(request.user, offer_id)
        changes = raw_object(request.data, "changes")
        message = AnswerSerializer(data={"reason": request.data.get("message", "")})
        message.is_valid(raise_exception=True)
        try:
            services.counter(
                offer_id,
                talent=request.user,
                changes=changes,
                message=message.validated_data.get("reason", ""),
                request=request,
            )
        except Offer.DoesNotExist as exc:
            raise exceptions.NotFound("No such offer.") from exc
        except services.OfferError as exc:
            raise refuse(exc) from exc
        application.refresh_from_db()
        return _thread_response(request, application, status.HTTP_201_CREATED)
