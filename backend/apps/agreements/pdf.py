"""Drawing up an agreement version as a PDF.

The text comes from a registered template (TEMPLATES): an HTML Django template rendered
with the version's frozen terms, then turned into a PDF by the renderer named in
settings.AGREEMENT_RENDERER (WeasyPrint; tests use apps.agreements.tests.fakes).

Templates are append-only: each version records the template's name and SHA-256, so a
signed PDF can always be traced to the exact wording. To change the wording, add a new
template file and point CURRENT_TEMPLATE at it.
"""

import hashlib
from dataclasses import dataclass
from datetime import date
from functools import cache
from pathlib import Path
from typing import Any, Protocol

from django.conf import settings
from django.template.loader import get_template
from django.utils.module_loading import import_string

from apps.gigs.constants import CompensationModel, DeliverableType, Meals, StayType, StipendPeriod
from apps.offers.terms import (
    CANCELLATION_NOTICE_DAYS,
    CancellationPolicy,
    UsageScope,
    weekly_hour_cap,
)


@dataclass(frozen=True)
class TemplateSpec:
    name: str
    path: str  # under templates/
    # False until a lawyer has reviewed the wording. Unreviewed templates print a
    # placeholder warning on every page's first section.
    reviewed: bool


TEMPLATES = {
    "agreement_v1": TemplateSpec("agreement_v1", "agreements/agreement_v1.html", reviewed=False),
}
CURRENT_TEMPLATE = "agreement_v1"


class Renderer(Protocol):
    def render(self, html: str) -> bytes:
        """HTML in, PDF bytes out."""
        ...


class WeasyPrintRenderer:
    def render(self, html: str) -> bytes:
        from weasyprint import HTML

        return HTML(string=html).write_pdf()


@cache
def _build(path: str) -> Renderer:
    return import_string(path)()


def get_renderer() -> Renderer:
    return _build(settings.AGREEMENT_RENDERER)


@cache
def template_sha256(name: str) -> str:
    spec = TEMPLATES[name]
    source = Path(__file__).parent / "templates" / spec.path
    return hashlib.sha256(source.read_bytes()).hexdigest()


def _label(choices, value: str) -> str:
    return dict(choices.choices).get(value, value)


def context_for(version) -> dict[str, Any]:
    """Everything the template shows, from the version's frozen terms and the booking."""
    from apps.chat.services import display_name

    terms = version.terms
    booking = version.agreement.booking
    gig = booking.gig
    prop = gig.property
    start, end = date.fromisoformat(terms["start_date"]), date.fromisoformat(terms["end_date"])
    usage = terms.get("usage_rights")
    stipend = terms.get("stipend_amount")
    policy = terms["cancellation_policy"]
    return {
        "reference": str(version.agreement_id).split("-")[0].upper(),
        "version_number": version.number,
        "drawn_up": version.created_at,
        "host_name": display_name(booking.vendor),
        "talent_name": display_name(booking.talent),
        "property_name": prop.name,
        "property_city": prop.city,
        "property_state": prop.get_state_display(),
        "gig_title": gig.title,
        "terms": terms,
        "start_date": start,
        "end_date": end,
        "nights": (end - start).days,
        "weekly_cap": weekly_hour_cap(terms),
        "days_off": 7 - int(terms["days_per_week"]),
        "stay_label": _label(StayType, terms["stay_type"]),
        "meals_label": _label(Meals, terms["meals"]),
        "compensation_label": _label(CompensationModel, terms["compensation_model"]),
        "stipend": f"{float(stipend):,.2f}" if stipend else "",
        "stipend_period_label": _label(StipendPeriod, terms.get("stipend_period") or ""),
        "deliverables": [
            {**d, "label": _label(DeliverableType, d["type"])} for d in terms["deliverables"]
        ],
        "usage": {**usage, "scope_label": _label(UsageScope, usage["scope"])} if usage else None,
        "cancellation_label": _label(CancellationPolicy, policy),
        "notice_days": CANCELLATION_NOTICE_DAYS[policy],
        "reviewed": TEMPLATES[version.template].reviewed,
    }


def render_html(version) -> str:
    spec = TEMPLATES[version.template]
    return get_template(spec.path).render(context_for(version))


def render_pdf(version) -> bytes:
    return get_renderer().render(render_html(version))
