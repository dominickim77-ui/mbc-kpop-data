"""Optional psycopg 3 runtime for the reviewed STEP 24 schema.

No schema creation, migration, or fallback to legacy storage. SQL adapters below
cover this application's SQL only, not arbitrary SQLite/MySQL dialects.
"""
import os
import re
import sqlite3
from contextlib import contextmanager

# Shared by all editorial writers, including bootstrap and role changes.
# READ COMMITTED + transaction-scoped advisory lock preserves BEGIN IMMEDIATE's
# read/modify/write ordering across processes. Readers never take this lock.
EDITORIAL_LOCK = 27001


def enabled():
    backend = os.environ.get('KPOP_DB_BACKEND', 'legacy').strip().lower()
    if backend not in {'legacy', 'postgresql'}:
        raise RuntimeError('KPOP_DB_BACKEND must be legacy or postgresql')
    return backend == 'postgresql'


def open_connection():
    dsn = os.environ.get('KPOP_POSTGRES_DSN', '').strip()
    if not dsn:
        raise RuntimeError('KPOP_POSTGRES_DSN is required; legacy fallback is disabled')
    return _connect_driver(dsn)


def _connect_driver(dsn):
    """Single physical connection boundary, blocked by offline checks."""
    try:
        import psycopg
    except ImportError:
        raise RuntimeError('Install requirements-postgres.txt in an isolated environment') from None
    try:
        # Explicit isolation is required for the lock-then-read protocol.
        db = psycopg.connect(dsn, connect_timeout=5,
                             options='-c timezone=UTC -c search_path=public -c statement_timeout=15000',
                             autocommit=False)
        db.isolation_level = psycopg.IsolationLevel.READ_COMMITTED
        return db
    except psycopg.Error:
        # DSNs/credentials and server diagnostics must not appear in HTTP output.
        raise RuntimeError('PostgreSQL connection unavailable') from None


class Row(dict):
    """Keep existing named and positional SQLite row consumers compatible."""
    def __getitem__(self, key):
        if isinstance(key, int):
            return tuple(self.values())[key]
        return super().__getitem__(key)


def editorial_sql(sql):
    # Replace placeholders outside SQL string literals only; values stay bound.
    parts = re.split(r"('(?:''|[^'])*')", sql)
    parts[::2] = [part.replace('?', '%s') for part in parts[::2]]
    sql = ''.join(parts)
    if re.fullmatch(r'INSERT OR REPLACE INTO login_limits VALUES\(%s,%s,%s\)', sql, re.I):
        sql = ('INSERT INTO login_limits(key,attempts,window_start) VALUES(%s,%s,%s) '
               'ON CONFLICT(key) DO UPDATE SET attempts=EXCLUDED.attempts, '
               'window_start=EXCLUDED.window_start')
    sql = sql.replace('updated_at=CURRENT_TIMESTAMP',
                      "updated_at=to_char(CURRENT_TIMESTAMP AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')")
    match = re.match(r'\s*INSERT INTO (users|articles|fact_reviews)\s*\(', sql, re.I)
    identity = bool(match)
    if identity:
        sql += ' RETURNING id'
    return sql, identity


def chart_sql(sql):
    identity = bool(re.match(r'\s*INSERT INTO tracks\s*\(', sql, re.I))
    if 'ON DUPLICATE KEY UPDATE' in sql:
        match = re.match(r'\s*INSERT INTO (spotify_chart|youtube_stats)\s*\(', sql, re.I)
        if not match:
            raise ValueError('Unsupported chart upsert')
        keys = {'spotify_chart': 'song_id,chart_date',
                'youtube_stats': 'youtube_video_id,collected_at'}[match[1].lower()]
        before, after = sql.split('ON DUPLICATE KEY UPDATE', 1)
        after = re.sub(r'VALUES\((\w+)\)', r'EXCLUDED.\1', after)
        sql = before + f'ON CONFLICT ({keys}) DO UPDATE SET ' + after
    if identity:
        sql = sql.rstrip().rstrip(';') + ' RETURNING song_id'
    return sql, identity


class Cursor:
    def __init__(self, raw, *, dictionary=False, editorial=False):
        self.raw, self.dictionary, self.editorial = raw, dictionary, editorial
        self.lastrowid = None

    def execute(self, sql, params=()):
        sql, identity = (editorial_sql if self.editorial else chart_sql)(sql)
        self.lastrowid = None
        try:
            self.raw.execute(sql, params)
        except Exception as exc:
            # Retain the signup conflict contract without requiring psycopg
            # to be installed for the legacy backend.
            if (getattr(exc, 'sqlstate', None) or '').startswith('23'):
                raise sqlite3.IntegrityError('PostgreSQL constraint violation') from None
            raise
        if identity:
            self.lastrowid = self.raw.fetchone()[0]
        return self

    def _row(self, row):
        if row is None or not self.dictionary:
            return row
        return Row(zip((column.name for column in self.raw.description), row))

    def fetchone(self):
        return self._row(self.raw.fetchone())

    def fetchall(self):
        return [self._row(row) for row in self.raw.fetchall()]

    def __iter__(self):
        while (row := self.fetchone()) is not None:
            yield row

    @property
    def rowcount(self):
        return self.raw.rowcount

    def close(self):
        self.raw.close()


class Connection:
    def __init__(self, raw):
        self.raw = raw

    def cursor(self, dictionary=False):
        return Cursor(self.raw.cursor(), dictionary=dictionary)

    def execute(self, sql, params=()):
        return Cursor(self.raw.cursor(), dictionary=True, editorial=True).execute(sql, params)

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def close(self):
        self.raw.close()


def chart_connection():
    return Connection(open_connection())


@contextmanager
def editorial_connection(write=False):
    raw = open_connection()
    try:
        if write:
            raw.execute('SELECT pg_advisory_xact_lock(%s)', (EDITORIAL_LOCK,))
        yield Connection(raw)
        raw.commit()
    except BaseException:
        raw.rollback()
        raise
    finally:
        raw.close()
