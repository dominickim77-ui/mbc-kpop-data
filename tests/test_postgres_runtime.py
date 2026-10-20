"""Offline contracts only: these are NOT PostgreSQL engine tests."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from db import postgres_runtime as pg
from security import editorial_store as store


class PostgresRuntimeTests(unittest.TestCase):
    def test_default_and_invalid_backend(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(pg.enabled())
        with patch.dict(os.environ, {'KPOP_DB_BACKEND': 'typo'}):
            with self.assertRaises(RuntimeError):
                pg.enabled()

    def test_missing_dsn_fails_closed(self):
        with patch.dict(os.environ, {'KPOP_POSTGRES_DSN': ''}), \
             patch('mysql.connector.connect') as mysql:
            with self.assertRaises(RuntimeError):
                pg.open_connection()
            mysql.assert_not_called()

    def test_editorial_postgres_does_not_open_sqlite(self):
        with patch.dict(os.environ, {'KPOP_DB_BACKEND': 'postgresql'}), \
             patch.object(pg, 'open_connection', side_effect=RuntimeError('unavailable')), \
             patch('sqlite3.connect') as sqlite:
            with self.assertRaises(RuntimeError):
                with store.connect():
                    pass
            sqlite.assert_not_called()
            self.assertTrue(store.available())
            with self.assertRaises(RuntimeError):
                store.initialize()

    def test_chart_backend_dispatch(self):
        import app
        with patch.dict(os.environ, {'KPOP_DB_BACKEND': 'postgresql'}), \
             patch.object(pg, 'chart_connection', return_value='test connection') as connect, \
             patch('mysql.connector.connect') as mysql:
            self.assertEqual(app.get_db_connection(), 'test connection')
            connect.assert_called_once()
            mysql.assert_not_called()

    def test_parameter_values_not_interpolated(self):
        raw = Mock()
        raw.fetchone.return_value = (42,)
        cur = pg.Cursor(raw, editorial=True)
        value = "O'Brien ? %s"
        cur.execute('INSERT INTO users(username,password_hash) VALUES(?,?)', (value, 'hash'))
        self.assertEqual(cur.lastrowid, 42)
        sql, params = raw.execute.call_args.args
        self.assertIn('RETURNING id', sql)
        self.assertEqual(params, (value, 'hash'))
        self.assertNotIn(value, sql)
        self.assertEqual(pg.editorial_sql("SELECT '?' WHERE username=?")[0],
                         "SELECT '?' WHERE username=%s")

    def test_upsert_and_timestamp(self):
        sql, _ = pg.editorial_sql('INSERT OR REPLACE INTO login_limits VALUES(?,?,?)')
        self.assertIn('ON CONFLICT(key) DO UPDATE', sql)
        self.assertIn('EXCLUDED.window_start', sql)
        sql, _ = pg.editorial_sql('UPDATE articles SET updated_at=CURRENT_TIMESTAMP WHERE id=?')
        self.assertIn("AT TIME ZONE 'UTC'", sql)
        sql, _ = pg.chart_sql('INSERT INTO spotify_chart (song_id) VALUES (%s) ON DUPLICATE KEY UPDATE spotify_rank = VALUES(spotify_rank)')
        self.assertIn('ON CONFLICT (song_id,chart_date)', sql)
        self.assertIn('EXCLUDED.spotify_rank', sql)
        sql, _ = pg.chart_sql('INSERT INTO youtube_stats (song_id) VALUES (%s) ON DUPLICATE KEY UPDATE youtube_views = VALUES(youtube_views)')
        self.assertIn('ON CONFLICT (youtube_video_id,collected_at)', sql)

    def test_mapping_positional_and_iterator(self):
        raw = Mock()
        raw.description = [SimpleNamespace(name='id'), SimpleNamespace(name='role')]
        raw.fetchone.side_effect = [(1, 'EDITOR'), None]
        rows = list(pg.Cursor(raw, dictionary=True))
        self.assertEqual(rows[0][0], 1)
        self.assertEqual(rows[0]['role'], 'EDITOR')
        self.assertEqual(dict(rows[0]), {'id': 1, 'role': 'EDITOR'})

    def test_chart_returning_identity(self):
        raw = Mock()
        raw.fetchone.return_value = (11,)
        cur = pg.Cursor(raw)
        cur.execute('INSERT INTO tracks (artist,track) VALUES (%s,%s)', ('a', 'b'))
        self.assertEqual(cur.lastrowid, 11)
        self.assertIn('RETURNING song_id', raw.execute.call_args.args[0])

    def test_unique_constraint_contract(self):
        import sqlite3
        raw = Mock()
        error = Exception('private server diagnostic')
        error.sqlstate = '23505'
        raw.execute.side_effect = error
        with self.assertRaises(sqlite3.IntegrityError) as caught:
            pg.Cursor(raw).execute('SELECT 1')
        self.assertNotIn('private', str(caught.exception))

    def test_writer_lock_commit_close(self):
        raw = Mock()
        with patch.object(pg, 'open_connection', return_value=raw):
            with pg.editorial_connection(True) as conn:
                conn.execute('UPDATE users SET selection=? WHERE id=?', ('[]', 1))
        self.assertEqual(raw.method_calls[0].args,
                         ('SELECT pg_advisory_xact_lock(%s)', (pg.EDITORIAL_LOCK,)))
        raw.commit.assert_called_once()
        raw.rollback.assert_not_called()
        raw.close.assert_called_once()

    def test_failure_rolls_back_and_closes(self):
        raw = Mock()
        with patch.object(pg, 'open_connection', return_value=raw):
            with self.assertRaises(ValueError):
                with pg.editorial_connection(True):
                    raise ValueError('synthetic')
        raw.rollback.assert_called_once()
        raw.commit.assert_not_called()
        raw.close.assert_called_once()

    def test_readers_do_not_lock(self):
        raw = Mock()
        with patch.object(pg, 'open_connection', return_value=raw):
            with pg.editorial_connection():
                pass
        raw.execute.assert_not_called()
        raw.close.assert_called_once()

    def test_non_database_error_is_not_masked(self):
        raw = Mock()
        error = RuntimeError('synthetic error')
        error.sqlstate = None
        raw.execute.side_effect = error
        with self.assertRaisesRegex(RuntimeError, 'synthetic error'):
            pg.Cursor(raw).execute('SELECT 1')
