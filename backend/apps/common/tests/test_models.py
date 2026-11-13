import time

import pytest

from apps.common.models import AuditLog
from apps.profiles.models import TalentProfile
from apps.profiles.tests.factories import TalentProfileFactory

pytestmark = pytest.mark.django_db


class TestTimeStampedModel:
    def test_sets_created_and_updates_updated(self):
        profile = TalentProfileFactory()
        created, updated = profile.created_at, profile.updated_at
        assert created is not None and updated is not None
        time.sleep(0.01)
        profile.bio = "Changed"
        profile.save()
        profile.refresh_from_db()
        assert profile.created_at == created
        assert profile.updated_at > updated


class TestSoftDeleteModel:
    def test_delete_hides_row_but_keeps_it(self):
        profile = TalentProfileFactory()
        assert profile.delete() == (1, {"profiles.TalentProfile": 1})
        assert profile.is_deleted
        assert not TalentProfile.objects.filter(pk=profile.pk).exists()
        assert TalentProfile.all_objects.filter(pk=profile.pk).exists()

    def test_restore(self):
        profile = TalentProfileFactory()
        profile.delete()
        profile.restore()
        assert not profile.is_deleted
        assert TalentProfile.objects.filter(pk=profile.pk).exists()

    def test_hard_delete_removes_row(self):
        profile = TalentProfileFactory()
        profile.hard_delete()
        assert not TalentProfile.all_objects.filter(pk=profile.pk).exists()

    def test_queryset_delete_is_soft_and_alive_dead_filters(self):
        kept, gone = TalentProfileFactory(), TalentProfileFactory()
        assert TalentProfile.objects.filter(pk=gone.pk).delete() == 1
        assert list(TalentProfile.all_objects.alive()) == [kept]
        assert list(TalentProfile.all_objects.dead()) == [gone]

    def test_queryset_hard_delete(self):
        profile = TalentProfileFactory()
        TalentProfile.all_objects.filter(pk=profile.pk).hard_delete()
        assert not TalentProfile.all_objects.exists()

    def test_related_access_still_sees_deleted_profile(self):
        profile = TalentProfileFactory()
        profile.delete()
        assert type(profile.user).objects.get(pk=profile.user_id).talent_profile == profile


class TestAuditLogIsAppendOnly:
    def make(self):
        return AuditLog.objects.create(action="x.y", object_type="a.b", object_id="1")

    def test_str(self):
        assert str(self.make()) == "x.y a.b:1"

    def test_cannot_update_instance(self):
        entry = self.make()
        entry.action = "changed"
        with pytest.raises(TypeError, match="append-only"):
            entry.save()

    def test_cannot_delete_instance(self):
        with pytest.raises(TypeError, match="append-only"):
            self.make().delete()

    def test_cannot_bulk_update_or_delete(self):
        self.make()
        with pytest.raises(TypeError):
            AuditLog.objects.update(action="changed")
        with pytest.raises(TypeError):
            AuditLog.objects.all().delete()
