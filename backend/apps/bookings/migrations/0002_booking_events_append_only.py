"""Make bookings_bookingevent append-only in the database itself.

A trigger rejects every UPDATE and DELETE, whoever the database user is (the app's own
user included), so the history of a booking can't be rewritten even with raw SQL.
"""

from django.db import migrations

FORWARD = """
CREATE FUNCTION bookings_event_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'bookings_bookingevent is append-only (% refused)', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER bookings_event_no_update
    BEFORE UPDATE ON bookings_bookingevent
    FOR EACH ROW EXECUTE FUNCTION bookings_event_append_only();

CREATE TRIGGER bookings_event_no_delete
    BEFORE DELETE ON bookings_bookingevent
    FOR EACH ROW EXECUTE FUNCTION bookings_event_append_only();
"""

REVERSE = """
DROP TRIGGER IF EXISTS bookings_event_no_delete ON bookings_bookingevent;
DROP TRIGGER IF EXISTS bookings_event_no_update ON bookings_bookingevent;
DROP FUNCTION IF EXISTS bookings_event_append_only();
"""


class Migration(migrations.Migration):
    dependencies = [("bookings", "0001_initial")]

    operations = [migrations.RunSQL(FORWARD, REVERSE)]
