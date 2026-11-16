"""Keep the agreement record honest in the database itself.

- A version's terms, template and the people involved never change. Its PDF fields may
  be filled in once (when the PDF is drawn up) and never changed after.
- Signatures are append-only: no UPDATE, no DELETE.
- Versions can't be deleted.

The triggers apply whoever the database user is, the app's own user included.
"""

from django.db import migrations

FORWARD = """
CREATE FUNCTION agreements_version_frozen() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'agreements_agreementversion rows are kept (DELETE refused)';
    END IF;
    IF NEW.terms IS DISTINCT FROM OLD.terms
        OR NEW.terms_sha256 IS DISTINCT FROM OLD.terms_sha256
        OR NEW.agreement_id IS DISTINCT FROM OLD.agreement_id
        OR NEW.number IS DISTINCT FROM OLD.number
        OR NEW.offer_id IS DISTINCT FROM OLD.offer_id
        OR NEW.proposed_by_id IS DISTINCT FROM OLD.proposed_by_id
        OR NEW.change_reason IS DISTINCT FROM OLD.change_reason
        OR NEW.changed_fields IS DISTINCT FROM OLD.changed_fields
        OR NEW.template IS DISTINCT FROM OLD.template
        OR NEW.template_sha256 IS DISTINCT FROM OLD.template_sha256
        OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'An agreement version''s terms are frozen (UPDATE refused)';
    END IF;
    IF OLD.pdf_sha256 <> '' AND (
        NEW.pdf_sha256 IS DISTINCT FROM OLD.pdf_sha256
        OR NEW.pdf_key IS DISTINCT FROM OLD.pdf_key
        OR NEW.pdf_size IS DISTINCT FROM OLD.pdf_size
        OR NEW.rendered_at IS DISTINCT FROM OLD.rendered_at) THEN
        RAISE EXCEPTION 'An agreement version''s PDF is fixed once drawn up (UPDATE refused)';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER agreements_version_no_change
    BEFORE UPDATE OR DELETE ON agreements_agreementversion
    FOR EACH ROW EXECUTE FUNCTION agreements_version_frozen();

CREATE FUNCTION agreements_signature_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'agreements_signature is append-only (% refused)', TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER agreements_signature_no_change
    BEFORE UPDATE OR DELETE ON agreements_signature
    FOR EACH ROW EXECUTE FUNCTION agreements_signature_append_only();
"""

BACKWARD = """
DROP TRIGGER IF EXISTS agreements_signature_no_change ON agreements_signature;
DROP FUNCTION IF EXISTS agreements_signature_append_only();
DROP TRIGGER IF EXISTS agreements_version_no_change ON agreements_agreementversion;
DROP FUNCTION IF EXISTS agreements_version_frozen();
"""


class Migration(migrations.Migration):
    dependencies = [("agreements", "0001_initial")]

    operations = [migrations.RunSQL(FORWARD, BACKWARD)]
