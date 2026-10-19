"""Pure checks run by default. Live tests create/drop ONLY fresh STEP19 test DBs.

PowerShell opt-in: $env:STEP19_RUN_DB_TESTS='1'
Credentials: STEP19_DB_ENV_FILE, otherwise repository .env (read only).
"""
import copy
import json
import os
import re
import subprocess
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from db.schema_tools import (SchemaError, apply_test_migration, compare_schema, connect_database,
                             inspect_schema, load_config, load_manifest, plan_migration,
                             require_test_target)


class SchemaPolicyTests(unittest.TestCase):
    def test_operational_or_unspecified_target_cannot_receive_ddl(self):
        for name in [None, '', 'mbc_kpop_data', 'MBC_KPOP_DATA', 'other_database',
                     'mbc_kpop_step19_test_bad`name']:
            with self.subTest(name=name), self.assertRaises(SchemaError):
                require_test_target(name, 'mbc_kpop_data')

    def test_configured_database_is_protected_even_with_test_prefix(self):
        with self.assertRaises(SchemaError):
            require_test_target('mbc_kpop_step19_test_prod', 'MBC_KPOP_STEP19_TEST_PROD')

    def test_no_operational_database_config_means_no_apply(self):
        with self.assertRaises(SchemaError):
            require_test_target('mbc_kpop_step19_test_fixture', None)

    def test_cli_rejects_operational_apply_before_connecting(self):
        from scripts import migrate_db_schema
        with patch.object(sys, 'argv', ['migrate', '--database', 'mbc_kpop_data', '--apply']), \
             patch.object(migrate_db_schema, 'load_config', return_value={'MYSQL_DATABASE': 'mbc_kpop_data'}), \
             patch.object(migrate_db_schema, 'connect_database') as connect:
            self.assertEqual(migrate_db_schema.main(), 1)
            connect.assert_not_called()

    def test_index_visibility_and_direction_are_compared(self):
        expected = load_manifest()
        for field, value in [('IS_VISIBLE', 'NO'), ('COLLATION', 'D')]:
            actual = copy.deepcopy(expected)
            actual.update(database=[{'database_name': 'fixture'}], triggers=[], routines=[])
            actual['indexes'][0][field] = value
            result = compare_schema(actual, expected)
            self.assertTrue(result['errors'] or result['missing_unique_indexes'])

    def test_counter_and_row_count_not_part_of_schema_contract(self):
        expected = load_manifest()
        actual = copy.deepcopy(expected)
        actual.update(database=[{'database_name': 'fixture'}], triggers=[], routines=[],
                      arbitrary_row_count=9999, auto_increment_counter=100000)
        self.assertTrue(compare_schema(actual, expected)['compatible'])


@unittest.skipUnless(os.environ.get('STEP19_RUN_DB_TESTS') == '1',
                     'Opt in to fresh isolated MySQL database creation with STEP19_RUN_DB_TESTS=1')
class MySQLReproductionTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config(os.environ.get('STEP19_DB_ENV_FILE'))
        self.name = 'mbc_kpop_step19_test_' + uuid.uuid4().hex[:12]
        require_test_target(self.name, self.config.get('MYSQL_DATABASE'))
        self.admin = connect_database(self.config, None)
        self.addCleanup(self.admin.close)
        cursor = self.admin.cursor()
        try:
            cursor.execute('SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s', (self.name,))
            self.assertIsNone(cursor.fetchone(), 'Never reuse an existing database for fixtures')
            cursor.execute(f'CREATE DATABASE `{self.name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci')
        finally:
            cursor.close()
        self.created = True
        self.addCleanup(self.drop_created_database)
        self.connection = connect_database(self.config, self.name)
        self.addCleanup(self.connection.close)

    def drop_created_database(self):
        # Only the exact database created by this test instance may be removed.
        require_test_target(self.name, self.config.get('MYSQL_DATABASE'))
        if self.created:
            cursor = self.admin.cursor()
            try:
                cursor.execute(f'DROP DATABASE `{self.name}`')
            finally:
                cursor.close()
            self.created = False

    def execute(self, sql, params=None):
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql, params or ())
        finally:
            cursor.close()

    def build(self, legacy=False):
        path = ROOT / ('tests/fixtures/legacy_step18_schema.sql' if legacy else 'mbc_kpop_data.sql')
        text = re.sub(r'--[^\n]*', '', path.read_text(encoding='utf-8'))
        text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
        for sql in text.split(';'):
            if sql.strip():
                self.assertRegex(sql.strip(), r'^(CREATE TABLE|ALTER TABLE)\b')
                self.execute(sql.strip())

    def seed(self):
        self.execute("INSERT INTO tracks (song_id,artist,track) VALUES (41,'Fixture Artist','Fixture Track')")
        self.execute("INSERT INTO spotify_chart VALUES (71,41,20,30000,'2026-10-08','2026-10-19 01:00:00')")
        self.execute("INSERT INTO youtube_stats VALUES (81,41,'AAAAAAAAAAA','Fixture MV','Fixture Channel',2000,12,1,'2026-10-19 01:00:00')")
        self.connection.commit()

    def snapshot(self):
        cursor = self.connection.cursor(dictionary=True)
        try:
            result = {}
            for table, pk in [('tracks', 'song_id'), ('spotify_chart', 'spotify_id'), ('youtube_stats', 'youtube_id')]:
                cursor.execute(f'SELECT * FROM {table} ORDER BY {pk}')
                result[table] = cursor.fetchall()
            return result
        finally:
            cursor.close()
            self.connection.rollback()

    def plan(self):
        self.connection.start_transaction(readonly=True)
        try:
            return plan_migration(self.connection)
        finally:
            self.connection.rollback()

    def migrate(self):
        return apply_test_migration(self.connection, self.name, self.config['MYSQL_DATABASE'])

    def test_bootstrap_reproduces_schema(self):
        self.build()
        self.assertTrue(self.plan()['compatible'])
        self.assertEqual(self.plan()['statements'], [])

    def test_existing_tables_fail_instead_of_silently_skipping(self):
        import mysql.connector
        self.build()
        self.seed()
        before = self.snapshot()
        with self.assertRaises(mysql.connector.Error):
            self.build()
        self.assertEqual(self.snapshot(), before)

    def test_spotify_upsert_preserves_song_week_identity(self):
        import mysql.connector
        self.build()
        self.seed()
        with self.assertRaises(mysql.connector.IntegrityError):
            self.execute("INSERT INTO spotify_chart (song_id,spotify_rank,spotify_streams,chart_date,collected_at) VALUES (41,19,31000,'2026-10-08','2026-10-19 02:00:00')")
        self.connection.rollback()
        self.execute("INSERT INTO spotify_chart (song_id,spotify_rank,spotify_streams,chart_date,collected_at) VALUES (41,19,31000,'2026-10-08','2026-10-19 02:00:00') ON DUPLICATE KEY UPDATE spotify_rank=VALUES(spotify_rank),spotify_streams=VALUES(spotify_streams),collected_at=VALUES(collected_at)")
        self.connection.commit()
        rows = self.snapshot()['spotify_chart']
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]['spotify_id'], rows[0]['song_id'], rows[0]['spotify_streams']), (71, 41, 31000))

    def test_youtube_same_time_rejected_new_snapshot_preserved(self):
        import mysql.connector
        self.build()
        self.seed()
        with self.assertRaises(mysql.connector.IntegrityError):
            self.execute("INSERT INTO youtube_stats (song_id,youtube_video_id,youtube_title,youtube_channel,youtube_views,youtube_likes,youtube_comments,collected_at) VALUES (41,'AAAAAAAAAAA','Fixture MV','Fixture Channel',2100,12,1,'2026-10-19 01:00:00')")
        self.connection.rollback()
        self.execute("INSERT INTO youtube_stats (song_id,youtube_video_id,youtube_title,youtube_channel,youtube_views,youtube_likes,youtube_comments,collected_at) VALUES (41,'AAAAAAAAAAA','Fixture MV','Fixture Channel',2100,12,1,'2026-10-19 02:00:00')")
        self.connection.commit()
        rows = self.snapshot()['youtube_stats']
        self.assertEqual(len(rows), 2)
        self.assertEqual([r['youtube_views'] for r in rows], [2000, 2100])

    def test_foreign_keys_reject_orphan_insert_and_parent_delete(self):
        import mysql.connector
        self.build()
        self.seed()
        with self.assertRaises(mysql.connector.IntegrityError):
            self.execute("INSERT INTO spotify_chart VALUES (72,999,1,1,'2026-10-08','2026-10-19 00:00:00')")
        self.connection.rollback()
        with self.assertRaises(mysql.connector.IntegrityError):
            self.execute('DELETE FROM tracks WHERE song_id=41')
        self.connection.rollback()
        self.assertEqual(len(self.snapshot()['tracks']), 1)

    def test_legacy_migration_preserves_all_rows_ids_and_is_idempotent(self):
        self.build(legacy=True)
        self.seed()
        before = self.snapshot()
        self.assertEqual(len(self.plan()['statements']), 2)
        result = self.migrate()
        self.assertEqual(len(result['applied']), 2)
        self.assertTrue(result['compatible'])
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.migrate()['applied'], [])
        self.assertEqual(self.snapshot(), before)

    def test_empty_legacy_database_migrates(self):
        self.build(legacy=True)
        self.assertEqual(len(self.migrate()['applied']), 2)
        self.assertTrue(self.plan()['compatible'])

    def test_partial_prior_migration_only_adds_missing_index(self):
        self.build(legacy=True)
        self.seed()
        before = self.snapshot()
        self.execute('ALTER TABLE spotify_chart ADD UNIQUE KEY uq_spotify_song_chart (song_id, chart_date)')
        result = self.migrate()
        self.assertEqual(len(result['applied']), 1)
        self.assertIn('youtube_stats', result['applied'][0])
        self.assertEqual(self.snapshot(), before)

    def test_different_equivalent_index_name_is_not_added_again(self):
        self.build()
        self.execute('ALTER TABLE spotify_chart RENAME INDEX uq_spotify_song_chart TO equivalent_spotify')
        result = self.migrate()
        self.assertEqual(result['applied'], [])
        self.assertTrue(result['warnings'])

    def test_different_equivalent_fk_name_is_accepted(self):
        self.build()
        self.execute('ALTER TABLE youtube_stats DROP FOREIGN KEY youtube_stats_ibfk_1, ADD CONSTRAINT equivalent_fk FOREIGN KEY (song_id) REFERENCES tracks(song_id) ON UPDATE RESTRICT ON DELETE RESTRICT')
        self.assertEqual(self.migrate()['applied'], [])

    def test_spotify_duplicates_abort_before_any_ddl(self):
        self.build(legacy=True)
        self.seed()
        self.execute("INSERT INTO spotify_chart VALUES (72,41,21,29000,'2026-10-08','2026-10-19 02:00:00')")
        self.connection.commit()
        before = self.snapshot()
        with self.assertRaises(SchemaError):
            self.migrate()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(len(compare_schema(inspect_schema(self.connection))['missing_unique_indexes']), 2)
        self.connection.rollback()

    def test_youtube_duplicates_abort_before_any_ddl(self):
        self.build(legacy=True)
        self.seed()
        self.execute("INSERT INTO youtube_stats VALUES (82,41,'AAAAAAAAAAA','Fixture MV','Fixture Channel',2000,12,1,'2026-10-19 01:00:00')")
        self.connection.commit()
        before = self.snapshot()
        with self.assertRaises(SchemaError):
            self.migrate()
        self.assertEqual(self.snapshot(), before)

    def test_orphan_fixture_aborts_without_deleting_rows(self):
        self.build(legacy=True)
        self.seed()
        self.execute('SET FOREIGN_KEY_CHECKS=0')
        try:
            self.execute("INSERT INTO spotify_chart VALUES (72,999,1,1,'2026-10-08','2026-10-19 00:00:00')")
            self.connection.commit()
        finally:
            self.execute('SET FOREIGN_KEY_CHECKS=1')
        before = self.snapshot()
        with self.assertRaises(SchemaError):
            self.migrate()
        self.assertEqual(self.snapshot(), before)

    def test_column_drift_blocks_both_index_additions(self):
        self.build(legacy=True)
        self.execute('ALTER TABLE tracks MODIFY artist VARCHAR(254) NOT NULL')
        with self.assertRaises(SchemaError):
            self.migrate()
        self.assertEqual(len(compare_schema(inspect_schema(self.connection))['missing_unique_indexes']), 2)
        self.connection.rollback()

    def test_conflicting_index_name_blocks_whole_plan(self):
        self.build(legacy=True)
        self.execute('ALTER TABLE spotify_chart ADD KEY uq_spotify_song_chart (song_id, chart_date)')
        with self.assertRaises(SchemaError):
            self.migrate()

    def test_prefix_unique_is_not_equivalent(self):
        self.build(legacy=True)
        self.execute('ALTER TABLE youtube_stats ADD UNIQUE KEY uq_youtube_video_collected (youtube_video_id(5), collected_at)')
        with self.assertRaises(SchemaError):
            self.migrate()


if __name__ == '__main__':
    unittest.main(verbosity=2)
