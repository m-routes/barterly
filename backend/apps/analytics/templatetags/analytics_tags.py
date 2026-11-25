from django import template

register = template.Library()


def _get(kpi, name):
    return kpi.get(name) if isinstance(kpi, dict) else getattr(kpi, name, None)


def _fmt(value, unit) -> str:
    if value is None:
        return "\u2013"
    if unit == "ratio":
        return f"{value * 100:.1f}%"
    if unit == "hours":
        return f"{value:.1f} h"
    if unit == "stars":
        return f"{value:.2f} ★"
    return f"{value:g}"


@register.filter
def kpi_value(kpi) -> str:
    """A KPI (or a snapshot's dict of one) as people read it: 72.0%, 8.5, 3.1 h."""
    if not kpi:
        return "\u2013"
    return _fmt(_get(kpi, "value"), _get(kpi, "unit"))


@register.filter
def kpi_target(kpi) -> str:
    return _fmt(_get(kpi, "target"), _get(kpi, "unit"))
