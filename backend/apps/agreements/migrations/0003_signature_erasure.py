"""Let account deletion anonymise a signature, and nothing else change it.

Signatures stay append-only. The one exception: inside a transaction that has set
`barterly.erasure` to 'on' (apps.privacy.services.erasure.anonymise does, with
set_config(..., true) so it ends with the transaction), an UPDATE may change the
signer's phone, IP, user agent, device and evidence. Every other column stays fixed,
and DELETE is still refused.
"""

from django.db import migrations

FORWARD = """
CREATE OR REPLACE FUNCTION agreements_signature_append_only() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'UPDATE'
        AND coalesce(current_setting('barterly.erasure', true), '') = 'on'
        AND NEW.id IS NOT DISTINCT FROM OLD.id
        AND NEW.version_id IS NOT DISTINCT FROM OLD.version_id
        AND NEW.party IS NOT DISTINCT FROM OLD.party
        AND NEW.user_id IS NOT DISTINCT FROM OLD.user_id
        AND NEW.provider IS NOT DISTINCT FROM OLD.provider
        AND NEW.provider_reference IS NOT DISTINCT FROM OLD.provider_reference
        AND NEW.document_sha256 IS NOT DISTINCT FROM OLD.document_sha256
        AND NEW.consent_text IS NOT DISTINCT FROM OLD.consent_text
        AND NEW.otp_verified_at IS NOT DISTINCT FROM OLD.otp_verified_at
        AND NEW.signed_at IS NOT DISTINCT FROM OLD.signed_at THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'agreements_signature is append-only (% refused)', TG_OP;
END;
$$ LANGUAGE plpgsql;
"""

BACKWARD = """
CREATE OR REPLACE FUNCTION agreements_signature_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'agreements_signature is append-only (% refused)', TG_OP;
END;
$$ LANGUAGE plpgsql;
"""


class Migration(migrations.Migration):
    dependencies = [("agreements", "0002_agreement_record_frozen")]

    operations = [migrations.RunSQL(FORWARD, BACKWARD)]
