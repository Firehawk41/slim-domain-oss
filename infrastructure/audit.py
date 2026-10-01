"""Database-wide change log (PostgreSQL only).

Every insert, edit and delete on an audited table is recorded by Postgres
itself, in `audit_log`: table, operation, the row before and after (as
JSON), when, the database login, and -- when the writer supplies them --
who (initials) and why (a reason). Nothing that writes to the database can
bypass it: the app, a script, or a hand-typed SQL statement.

Locked: `audit_log` and `report_generation_log` refuse edits, deletes and
TRUNCATE; audited tables refuse TRUNCATE (it would skip the per-row log).
Corrections are made by adding entries, never by changing old ones.

Chained: each entry stores the previous entry's hash and its own, so
altering or removing any past entry is detectable (`verify_chain`). This
matters because the lock stops accidents, not an administrator -- the
table owner can disable a trigger -- and nothing short of a role split
(the app running as a login that doesn't own the tables) changes that.
Dropping a whole table can't be blocked either without superuser rights.

Who/why: set per transaction with `set_change_context` (the
`app.changed_by` / `app.change_reason` settings). Direct edits go through
report-engine's scripts/db_edit.py, which requires both. App
writes already carry the technician's initials in each row's `created_by`,
which the logged row includes.

Excluded columns: `EXCLUDED_COLUMNS` strips named columns from the logged
copies -- for anything that must never be kept forever (e.g. payment data
in a future module). Nothing is excluded today.

Install or re-install with `install(conn)`; it is idempotent and attaches
the audit trigger to every table in the public schema except the two logs.
A new table added later is covered by re-running it -- and
report-engine's tests fail while any table is uncovered.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection

AUDIT_TABLE = "audit_log"
# Tables whose rows are themselves records: locked, never audited.
LOG_TABLES = ("audit_log", "report_generation_log")
# table -> columns never copied into the audit log.
EXCLUDED_COLUMNS: dict[str, tuple[str, ...]] = {}

_CHAIN_LOCK_KEY = 727274  # serialises appends so the hash chain stays linear

_DDL = """
CREATE TABLE IF NOT EXISTS audit_log (
    id          bigserial PRIMARY KEY,
    changed_at  timestamptz NOT NULL DEFAULT now(),
    table_name  text NOT NULL,
    operation   text NOT NULL,
    old_row     jsonb,
    new_row     jsonb,
    db_user     text NOT NULL DEFAULT current_user,
    changed_by  text,
    reason      text,
    prev_hash   text,
    row_hash    text NOT NULL
);

CREATE OR REPLACE FUNCTION audit_hash(
    prev text, at timestamptz, tbl text, op text, old jsonb, new jsonb, usr text, by text, why text
) RETURNS text LANGUAGE sql IMMUTABLE AS $$
    SELECT encode(sha256(convert_to(concat_ws('|',
        coalesce(prev, ''),
        to_char(at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US'),
        tbl, op, coalesce(old::text, ''), coalesce(new::text, ''),
        usr, coalesce(by, ''), coalesce(why, '')
    ), 'UTF8')), 'hex')
$$;

CREATE OR REPLACE FUNCTION audit_append(
    tbl text, op text, old jsonb, new jsonb, by text, why text
) RETURNS bigint LANGUAGE plpgsql AS $$
DECLARE
    prev text;
    at timestamptz := now();
    usr text := current_user;
    new_id bigint;
BEGIN
    PERFORM pg_advisory_xact_lock(__CHAIN_LOCK_KEY__);
    SELECT row_hash INTO prev FROM audit_log ORDER BY id DESC LIMIT 1;
    INSERT INTO audit_log (changed_at, table_name, operation, old_row, new_row, db_user,
                           changed_by, reason, prev_hash, row_hash)
    VALUES (at, tbl, op, old, new, usr, by, why, prev,
            audit_hash(prev, at, tbl, op, old, new, usr, by, why))
    RETURNING id INTO new_id;
    RETURN new_id;
END
$$;

CREATE OR REPLACE FUNCTION audit_row() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    old_j jsonb := CASE WHEN TG_OP IN ('UPDATE', 'DELETE') THEN to_jsonb(OLD) END;
    new_j jsonb := CASE WHEN TG_OP IN ('INSERT', 'UPDATE') THEN to_jsonb(NEW) END;
    col text;
BEGIN
    -- TG_ARGV is NULL, not empty, when a table has no excluded columns.
    IF TG_NARGS > 0 THEN
        FOREACH col IN ARRAY TG_ARGV LOOP
            old_j := old_j - col;
            new_j := new_j - col;
        END LOOP;
    END IF;
    IF TG_OP = 'UPDATE' AND old_j = new_j THEN
        RETURN NULL;  -- nothing visible changed
    END IF;
    PERFORM audit_append(TG_TABLE_NAME, TG_OP, old_j, new_j,
                         nullif(current_setting('app.changed_by', true), ''),
                         nullif(current_setting('app.change_reason', true), ''));
    RETURN NULL;
END
$$;

CREATE OR REPLACE FUNCTION audit_block() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% on % is not allowed: it is a locked record (add a correcting entry instead)',
        TG_OP, TG_TABLE_NAME;
END
$$;
"""


def install(conn: Connection) -> list[str]:
    """Creates/updates the change log, locks the two log tables, and
    attaches the audit trigger to every other table in the public schema.
    Returns the audited table names. Run inside a transaction."""
    # Raw execution: the DDL holds literal % and :MI/:SS that a bound
    # statement would misread as parameters.
    # (a raw cursor with no parameters, so the driver leaves them alone).
    conn.connection.cursor().execute(_DDL.replace("__CHAIN_LOCK_KEY__", str(_CHAIN_LOCK_KEY)))
    for table in LOG_TABLES:
        conn.execute(text(f'DROP TRIGGER IF EXISTS zz_lock_rows ON "{table}"'))
        conn.execute(text(f'DROP TRIGGER IF EXISTS zz_lock_truncate ON "{table}"'))
        conn.execute(text(
            f'CREATE TRIGGER zz_lock_rows BEFORE UPDATE OR DELETE ON "{table}" '
            "FOR EACH ROW EXECUTE FUNCTION audit_block()"
        ))
        conn.execute(text(
            f'CREATE TRIGGER zz_lock_truncate BEFORE TRUNCATE ON "{table}" '
            "FOR EACH STATEMENT EXECUTE FUNCTION audit_block()"
        ))
    audited = audited_tables(conn)
    for table in audited:
        args = ", ".join(f"'{c}'" for c in EXCLUDED_COLUMNS.get(table, ()))
        conn.execute(text(f'DROP TRIGGER IF EXISTS zz_audit ON "{table}"'))
        conn.execute(text(f'DROP TRIGGER IF EXISTS zz_audit_truncate ON "{table}"'))
        conn.execute(text(
            f'CREATE TRIGGER zz_audit AFTER INSERT OR UPDATE OR DELETE ON "{table}" '
            f"FOR EACH ROW EXECUTE FUNCTION audit_row({args})"
        ))
        conn.execute(text(
            f'CREATE TRIGGER zz_audit_truncate BEFORE TRUNCATE ON "{table}" '
            "FOR EACH STATEMENT EXECUTE FUNCTION audit_block()"
        ))
    return audited


def audited_tables(conn: Connection) -> list[str]:
    """Every public-schema table except the two locked logs."""
    rows = conn.execute(text(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
    )).scalars().all()
    return [t for t in rows if t not in LOG_TABLES]


def set_change_context(conn: Connection, changed_by: str, reason: str | None = None) -> None:
    """Attaches who/why to every change in the current transaction."""
    conn.execute(text("SELECT set_config('app.changed_by', :by, true)"), {"by": changed_by})
    conn.execute(text("SELECT set_config('app.change_reason', :why, true)"), {"why": reason or ""})


def append_entry(
    conn: Connection, table: str, operation: str, old_row: dict | None, new_row: dict | None,
    changed_by: str, reason: str,
) -> int:
    """Adds a hand-written entry (e.g. a backfill or a correction note),
    chained like every trigger-written one."""
    import json

    return conn.execute(
        text("SELECT audit_append(:t, :op, CAST(:old AS jsonb), CAST(:new AS jsonb), :by, :why)"),
        {
            "t": table, "op": operation,
            "old": json.dumps(old_row) if old_row is not None else None,
            "new": json.dumps(new_row) if new_row is not None else None,
            "by": changed_by, "why": reason,
        },
    ).scalar()


def verify_chain(conn: Connection) -> list[int]:
    """IDs of entries whose hash or link to the previous entry doesn't
    check out -- empty means the log is intact."""
    return conn.execute(text("""
        SELECT id FROM (
            SELECT id, prev_hash, row_hash,
                   lag(row_hash) OVER (ORDER BY id) AS expected_prev,
                   audit_hash(prev_hash, changed_at, table_name, operation, old_row, new_row,
                              db_user, changed_by, reason) AS expected_hash
            FROM audit_log
        ) t
        WHERE row_hash <> expected_hash OR prev_hash IS DISTINCT FROM expected_prev
        ORDER BY id
    """)).scalars().all()
