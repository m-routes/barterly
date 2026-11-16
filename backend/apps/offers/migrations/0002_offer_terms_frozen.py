"""Freeze an offer's terms in the database itself.

Once written, an offer's terms, their hash and who sent it can't change, and offers
can't be deleted, whoever the database user is. Only its status (and when and why it
changed) may move on.
"""

from django.db import migrations

FORWARD = """
CREATE FUNCTION offers_offer_frozen() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'offers_offer rows are kept (DELETE refused)';
    END IF;
    IF NEW.terms IS DISTINCT FROM OLD.terms
        OR NEW.terms_sha256 IS DISTINCT FROM OLD.terms_sha256
        OR NEW.application_id IS DISTINCT FROM OLD.application_id
        OR NEW.revision IS DISTINCT FROM OLD.revision
        OR NEW.proposed_by IS DISTINCT FROM OLD.proposed_by
        OR NEW.created_by_id IS DISTINCT FROM OLD.created_by_id
        OR NEW.counter_of_id IS DISTINCT FROM OLD.counter_of_id
        OR NEW.final IS DISTINCT FROM OLD.final
        OR NEW.message IS DISTINCT FROM OLD.message
        OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'An offer''s terms are frozen (UPDATE of a frozen column refused)';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER offers_offer_no_change
    BEFORE UPDATE OR DELETE ON offers_offer
    FOR EACH ROW EXECUTE FUNCTION offers_offer_frozen();
"""

BACKWARD = """
DROP TRIGGER IF EXISTS offers_offer_no_change ON offers_offer;
DROP FUNCTION IF EXISTS offers_offer_frozen();
"""


class Migration(migrations.Migration):
    dependencies = [("offers", "0001_initial")]

    operations = [migrations.RunSQL(FORWARD, BACKWARD)]
