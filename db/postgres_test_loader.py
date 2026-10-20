"""Optional psycopg 3 entry point for a NEW, dedicated localhost test database.

Not imported by FastAPI. Requires an already opened psycopg connection with no
active transaction. Caller owns credentials; never include DSNs in logs.
Real PostgreSQL execution remains BLOCKED until tested on that engine.
"""
import re

from db.postgres_prepare import plan, schema_sql, sequence_sql, TABLES


def load(connection, snapshot, *, allow_test_database=False):
    # Reject before any database write. Do not accept cloud hosts or production names.
    if (not allow_test_database
            or connection.info.host not in ('localhost', '127.0.0.1', '::1')
            or not re.fullmatch(r'kpop_step24_test_[a-z0-9_]+', connection.info.dbname)
            or connection.info.transaction_status != 0):
        raise ValueError('Requires idle dedicated localhost test database and explicit opt-in')
    rows = plan(snapshot)
    with connection.transaction():
        with connection.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM information_schema.tables "
                        "WHERE table_schema NOT IN ('pg_catalog','information_schema')")
            if cur.fetchone()[0]:
                raise ValueError('Test database must be empty; no overwrite or cleanup is performed')
            cur.execute("SET LOCAL search_path TO public")
            cur.execute(schema_sql())
            for sql, values in rows:
                cur.execute(sql, values)
            for sql in sequence_sql().splitlines():
                cur.execute(sql)
            counts = {}
            for table in TABLES:
                cur.execute(f'SELECT COUNT(*) FROM {table}')
                counts[table] = cur.fetchone()[0]
                if counts[table] != len(snapshot[table]):
                    raise ValueError('Row count mismatch')
    return counts
