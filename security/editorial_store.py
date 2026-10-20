"""Legacy SQLite or opt-in PostgreSQL persistence; no automatic migrations."""
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from db.postgres_runtime import enabled, editorial_connection

ROOT = Path(__file__).resolve().parents[1]


def available():
    return enabled() or database_path().is_file()


def database_path():
    return Path(os.environ.get('KPOP_AUTH_DB', str(ROOT / 'data/private/editorial.sqlite3')))


@contextmanager
def connect(write=False):
    if enabled():
        with editorial_connection(write) as db:
            yield db
        return
    path = database_path()
    if not path.is_file():
        raise RuntimeError('인증 DB를 먼저 초기화하세요: python -m security.admin init')
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    try:
        if write:
            db.execute('BEGIN IMMEDIATE')
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def initialize():
    if enabled():
        raise RuntimeError('PostgreSQL requires the reviewed STEP 24 schema; automatic init is disabled')
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents accidentally resetting an existing store.
    with path.open('xb'):
        pass
    with connect() as db:
        db.executescript((ROOT / 'db/migrations/002_editorial_sqlite.sql').read_text(encoding='utf-8'))


def audit(db, actor, action, target, data):
    db.execute('INSERT INTO audit(actor_id,action,target,data) VALUES(?,?,?,?)',
               (actor, action, str(target), json.dumps(data, ensure_ascii=False)))
