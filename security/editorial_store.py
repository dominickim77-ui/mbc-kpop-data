"""Isolated SQLite persistence. No MySQL connection or automatic schema changes."""
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def database_path():
    return Path(os.environ.get('KPOP_AUTH_DB', str(ROOT / 'data/private/editorial.sqlite3')))


@contextmanager
def connect(write=False):
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
