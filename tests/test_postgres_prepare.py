import copy
import sqlite3
import unittest

from db.postgres_prepare import TABLES, columns, plan, schema_sql, sequence_sql, ROOT
from security.auth import password_hash, verify_password


class PostgresPreparationTests(unittest.TestCase):
    def fixture(self):
        snapshot = {t: [] for t in TABLES}
        snapshot['tracks'] = [{'song_id': 7, 'artist': 'Synthetic', 'track': 'Test'}]
        with sqlite3.connect(':memory:') as db:
            db.row_factory = sqlite3.Row
            db.executescript((ROOT / 'db/migrations/002_editorial_sqlite.sql').read_text())
            db.execute("INSERT INTO users(id,username,password_hash,selection) VALUES(42,'tester',?,'[7]')",
                       (password_hash('Synthetic-only-password'),))
            db.execute("INSERT INTO articles(id,author_id,title,body,week_end,fact_ref,evidence,evidence_hash,status) "
                       "VALUES(53,42,'Test','Body','2026-10-08','facts/test.json','{\"test\": true}','hash','DRAFT')")
            db.execute("INSERT INTO revisions(id,article_id,version,actor_id,snapshot) VALUES(61,53,1,42,'{}')")
            db.execute("INSERT INTO audit(id,actor_id,action,target,data) VALUES(70,42,'CREATE','53','{}')")
            for table in TABLES[3:]:
                snapshot[table] = [dict(r) for r in db.execute(f'SELECT * FROM {table}')]
        return snapshot

    def test_ids_json_password_and_input_preserved(self):
        data = self.fixture()
        before = copy.deepcopy(data)
        rows = plan(data)
        self.assertEqual(data, before)
        self.assertTrue(verify_password('Synthetic-only-password', data['users'][0]['password_hash']))
        self.assertIn(53, rows[2][1])
        self.assertIn('{"test": true}', rows[2][1])
        self.assertNotIn('Synthetic', rows[0][0])
        self.assertEqual(len(rows), 5)

    def test_orphan_author_rejected(self):
        data = self.fixture()
        data['articles'][0]['author_id'] = 999
        with self.assertRaises(sqlite3.IntegrityError):
            plan(data)

    def test_invalid_role_rejected(self):
        data = self.fixture()
        data['users'][0]['role'] = 'SUPERUSER'
        with self.assertRaises(sqlite3.IntegrityError):
            plan(data)

    def test_unknown_selection_rejected(self):
        data = self.fixture()
        data['users'][0]['selection'] = '[999]'
        with self.assertRaises(ValueError):
            plan(data)

    def test_duplicate_username_rejected(self):
        data = self.fixture()
        data['users'].append(dict(data['users'][0], id=43))
        with self.assertRaises(sqlite3.IntegrityError):
            plan(data)

    def test_duplicate_revision_rejected(self):
        data = self.fixture()
        data['revisions'].append(dict(data['revisions'][0], id=62))
        with self.assertRaises(sqlite3.IntegrityError):
            plan(data)

    def test_invalid_json_rejected(self):
        data = self.fixture()
        data['articles'][0]['evidence'] = '{"bad":NaN}'
        with self.assertRaises(ValueError):
            plan(data)

    def test_incomplete_snapshot_rejected(self):
        with self.assertRaises(ValueError):
            plan({'users': []})

    def test_mysql_orphan_and_weekly_duplicate_rejected(self):
        data = self.fixture()
        row = dict(spotify_id=1, song_id=999, spotify_rank=1, spotify_streams=99,
                   chart_date='2026-10-08', collected_at='2026-10-09 00:00:00')
        data['spotify_chart'] = [row]
        with self.assertRaises(ValueError):
            plan(data)
        row['song_id'] = 7
        data['spotify_chart'].append(dict(row, spotify_id=2))
        with self.assertRaises(ValueError):
            plan(data)

    def test_schema_artifacts_match_source(self):
        self.assertEqual(len(columns()), 11)
        schema = schema_sql()
        self.assertEqual(schema.count('CREATE TABLE '), 11)
        self.assertEqual(schema.count('BEFORE UPDATE OR DELETE OR TRUNCATE'), 4)
        self.assertNotIn('RAISE(ABORT', schema)
        self.assertNotIn('AUTOINCREMENT', schema)
        self.assertEqual((ROOT / 'db/migrations/003_postgresql_prepare.sql').read_text(), schema)
        self.assertEqual(sequence_sql().count('setval('), 9)

    def test_empty_snapshot(self):
        self.assertEqual(plan({t: [] for t in TABLES}), [])
