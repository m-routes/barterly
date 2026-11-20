from django import template

from apps.money.wallet import rupees as _rupees

register = template.Library()


@register.filter
def rupees(paise) -> str:
    """Whole paise as rupees with two decimals: 123456 → 1234.56."""
    return _rupees(int(paise or 0))
