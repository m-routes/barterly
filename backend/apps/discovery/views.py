from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import exceptions, generics
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.utils.urls import replace_query_param

from apps.common.permissions import IsTalent
from apps.common.serializers import ErrorSerializer
from apps.discovery.filters import DiscoveryQuerySerializer
from apps.discovery.models import SavedSearch
from apps.discovery.serializers import GigCardSerializer, GigPageSerializer, SavedSearchSerializer
from apps.discovery.services import InvalidCursor, search

TAG = ["discovery"]


def discover(request: Request) -> Response:
    """GET /api/v1/gigs/ for talent (wired from apps.gigs.views.GigCollectionView)."""
    query = DiscoveryQuerySerializer(data=request.query_params)
    query.is_valid(raise_exception=True)
    try:
        page = search(request.user, query.validated_data, cursor=request.query_params.get("cursor"))
    except InvalidCursor as exc:
        raise exceptions.ValidationError({"cursor": [str(exc)]}) from exc
    scored = {item.gig.pk: item for item in page.results}
    cards = GigCardSerializer(
        [item.gig for item in page.results], many=True, context={"scored": scored}
    ).data
    next_url = (
        replace_query_param(request.build_absolute_uri(), "cursor", page.next_cursor)
        if page.next_cursor
        else None
    )
    return Response({"results": cards, "next_cursor": page.next_cursor, "next": next_url})


DISCOVER_SCHEMA = extend_schema(
    operation_id="gigs_discover",
    summary="Find gigs (talent)",
    description=(
        "Live gigs still taking applications that you're eligible for (languages, minimum "
        "followers), filtered by your choices, then sorted. `best_fit` orders by a 0-100 "
        "fit score (skills 30, reliability 25, ratings 20, audience quality 15, distance "
        "and availability 10); `fit.breakdown` explains it, and components without data "
        "use a neutral 0.5. Distances use each property's approximate location. Pass "
        "`next_cursor` back as `cursor` for the next page."
    ),
    parameters=[DiscoveryQuerySerializer],
    responses={
        200: GigPageSerializer,
        400: ErrorSerializer,
        401: ErrorSerializer,
        403: ErrorSerializer,
    },
    tags=TAG,
)


class _Mine:
    permission_classes = [IsTalent]
    serializer_class = SavedSearchSerializer
    pagination_class = None

    def get_queryset(self):
        return SavedSearch.objects.filter(talent=self.request.user)


@extend_schema_view(
    get=extend_schema(operation_id="saved_searches_list", summary="My saved searches", tags=TAG),
    post=extend_schema(
        operation_id="saved_searches_create",
        summary="Save a search",
        description=(
            "Alerts cover gigs published from now on: one notification per run that "
            "finds new matches."
        ),
        tags=TAG,
    ),
)
class SavedSearchListView(_Mine, generics.ListCreateAPIView):
    def perform_create(self, serializer):
        serializer.save(talent=self.request.user, last_checked_at=timezone.now())


@extend_schema_view(
    get=extend_schema(operation_id="saved_searches_retrieve", summary="A saved search", tags=TAG),
    patch=extend_schema(
        operation_id="saved_searches_update", summary="Change a saved search", tags=TAG
    ),
    delete=extend_schema(
        operation_id="saved_searches_destroy", summary="Delete a saved search", tags=TAG
    ),
)
class SavedSearchDetailView(_Mine, generics.RetrieveUpdateDestroyAPIView):
    lookup_url_kwarg = "search_id"
    http_method_names = ["get", "patch", "delete", "options"]
