"""How many live gigs a vendor's plan allows.

Behind an interface so paid plans can plug in later (code setting GIG_PLAN_POLICY).
For now every vendor is on the unlimited plan.
"""

from dataclasses import dataclass
from functools import cache
from typing import Protocol

from django.conf import settings
from django.utils.module_loading import import_string


@dataclass(frozen=True)
class Plan:
    name: str
    max_live_gigs: int | None  # None: no limit


class PlanPolicy(Protocol):
    def plan_for(self, vendor) -> Plan: ...


class UnlimitedPlanPolicy:
    def plan_for(self, vendor) -> Plan:
        return Plan(name="unlimited", max_live_gigs=None)


@cache
def _build(path: str) -> PlanPolicy:
    return import_string(path)()


def get_plan_policy() -> PlanPolicy:
    return _build(settings.GIG_PLAN_POLICY)
