"""Make the ledger append-only in the database itself.

Triggers reject every UPDATE and DELETE on money_ledgertransaction and money_ledgerentry,
whoever the database user is, so posted money movements can't be rewritten even with
raw SQL. A mistake is corrected by posting a reversing transaction.
"""

from django.db import migrations

TABLES = ("money_ledgertransaction", "money_ledgerentry")

FORWARD = """
CREATE FUNCTION money_ledger_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION '% is append-only (% refused)', TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$ LANGUAGE plpgsql;
""" + "".join(
    f"""
CREATE TRIGGER {t}_no_update BEFORE UPDATE ON {t}
    FOR EACH ROW EXECUTE FUNCTION money_ledger_append_only();
CREATE TRIGGER {t}_no_delete BEFORE DELETE ON {t}
    FOR EACH ROW EXECUTE FUNCTION money_ledger_append_only();
"""
    for t in TABLES
)

REVERSE = "".join(
    f"""
DROP TRIGGER IF EXISTS {t}_no_delete ON {t};
DROP TRIGGER IF EXISTS {t}_no_update ON {t};
"""
    for t in TABLES
) + "DROP FUNCTION IF EXISTS money_ledger_append_only();"


class Migration(migrations.Migration):
    dependencies = [("money", "0001_initial")]

    operations = [migrations.RunSQL(FORWARD, REVERSE)]
