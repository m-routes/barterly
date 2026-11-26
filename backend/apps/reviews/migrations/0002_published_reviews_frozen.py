"""A published review can't be edited, in the database itself: a trigger refuses any
UPDATE that changes its rating, scores, text, author or subject once it has been
published (moderation may still change its status, to remove it). A reply's text can't
change either. Neither can be deleted."""

from django.db import migrations

FORWARD = """
CREATE FUNCTION reviews_review_frozen() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'reviews are never deleted' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF OLD.published_at IS NOT NULL AND (
        NEW.rating IS DISTINCT FROM OLD.rating
        OR NEW.communication IS DISTINCT FROM OLD.communication
        OR NEW.accuracy IS DISTINCT FROM OLD.accuracy
        OR NEW.safety IS DISTINCT FROM OLD.safety
        OR NEW.reliability IS DISTINCT FROM OLD.reliability
        OR NEW.text IS DISTINCT FROM OLD.text
        OR NEW.author_id IS DISTINCT FROM OLD.author_id
        OR NEW.subject_id IS DISTINCT FROM OLD.subject_id
        OR NEW.booking_id IS DISTINCT FROM OLD.booking_id
        OR NEW.published_at IS DISTINCT FROM OLD.published_at
    ) THEN
        RAISE EXCEPTION 'a published review can''t be edited'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER reviews_review_frozen
    BEFORE UPDATE OR DELETE ON reviews_review
    FOR EACH ROW EXECUTE FUNCTION reviews_review_frozen();

CREATE FUNCTION reviews_reply_frozen() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' OR NEW.text IS DISTINCT FROM OLD.text
        OR NEW.review_id IS DISTINCT FROM OLD.review_id THEN
        RAISE EXCEPTION 'a reply can''t be edited or deleted'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER reviews_reply_frozen
    BEFORE UPDATE OR DELETE ON reviews_reply
    FOR EACH ROW EXECUTE FUNCTION reviews_reply_frozen();
"""

REVERSE = """
DROP TRIGGER IF EXISTS reviews_reply_frozen ON reviews_reply;
DROP FUNCTION IF EXISTS reviews_reply_frozen();
DROP TRIGGER IF EXISTS reviews_review_frozen ON reviews_review;
DROP FUNCTION IF EXISTS reviews_review_frozen();
"""


class Migration(migrations.Migration):
    dependencies = [("reviews", "0001_initial")]

    operations = [migrations.RunSQL(FORWARD, REVERSE)]
