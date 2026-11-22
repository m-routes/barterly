"""Every table that points at a user must be in the export or left out on purpose, so a
new table can't escape export and erasure unnoticed."""

import pytest
from django.apps import apps
from django.conf import settings

from apps.privacy.services.registry import EXPORT_SECTIONS, UNEXPORTED_LINKS, covered_links


def user_links():
    user_model = apps.get_model(settings.AUTH_USER_MODEL)
    for model in apps.get_models():
        if not model.__module__.startswith("apps."):
            continue
        for f in model._meta.fields:
            if f.is_relation and f.related_model is user_model:
                yield (model._meta.label, f.name)


def test_every_user_link_is_classified():
    missing = sorted(set(user_links()) - covered_links())
    assert missing == [], (
        "Add these to EXPORT_SECTIONS or UNEXPORTED_LINKS in apps/privacy/services/registry.py "
        f"(and handle them in erasure): {missing}"
    )


def test_sections_point_at_real_models_and_fields():
    for section in EXPORT_SECTIONS:
        model = apps.get_model(section.model)
        model._meta.get_field(section.path.split("__")[0])
        for name in section.exclude:
            model._meta.get_field(name)
    for model, field in UNEXPORTED_LINKS:
        apps.get_model(model)._meta.get_field(field)


@pytest.mark.parametrize("name", [s.name for s in EXPORT_SECTIONS])
def test_section_names_are_unique(name):
    assert [s.name for s in EXPORT_SECTIONS].count(name) == 1
