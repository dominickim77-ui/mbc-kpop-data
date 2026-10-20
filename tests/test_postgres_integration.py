"""Explicit real-engine test. NEVER enabled by the default offline runner.

Requires psycopg and a NEW EMPTY localhost kpop_step24_test_* database.
Reuses STEP 24's guarded loader. Leaves synthetic evidence for inspection; does
not create/drop databases or erase history. Use a fresh DB for every invocation.
"""
import asyncio
import json
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch


@unittest.skipUnless(os.environ.get('STEP27_RUN_POSTGRES_TESTS') == '1',
                     'Real PostgreSQL requires explicit isolated database opt-in')
class PostgresIntegrationTests(unittest.TestCase):
    def test_real_database_workflow(self):
        # No .env is loaded. Missing/invalid configuration is a failure after opt-in.
        import psycopg
        from psycopg.conninfo import conninfo_to_dict, make_conninfo
        from db.postgres_test_loader import load
        from db.postgres_prepare import TABLES
        from db import postgres_runtime as pg
        dsn = os.environ.get('KPOP_POSTGRES_TEST_DSN', '')
        config = conninfo_to_dict(dsn)
        import re
        if (config.get('host') not in ('localhost', '127.0.0.1', '::1')
                or config.get('hostaddr') not in (None, '127.0.0.1', '::1')
                or not re.fullmatch(r'kpop_step24_test_[a-z0-9_]+', config.get('dbname', ''))
                or 'service' in config):
            self.fail('Requires explicitly named fresh localhost STEP 24 test DB')
        with psycopg.connect(dsn, connect_timeout=5,
                             hostaddr='::1' if config['host'] == '::1' else '127.0.0.1') as raw:
            load(raw, {table: [] for table in TABLES}, allow_test_database=True)
        dsn = make_conninfo(dsn, hostaddr='::1' if config['host'] == '::1' else '127.0.0.1')
        env = patch.dict(os.environ, {'KPOP_DB_BACKEND': 'postgresql',
                         'KPOP_POSTGRES_DSN': dsn, 'PYTHON_DOTENV_DISABLED': '1'})
        env.start()
        self.addCleanup(env.stop)
        import app as site
        from security import auth, editorial_store as store
        from news import editorial
        from tests.test_editorial_auth import request, PASSWORD
        for target in ('mysql.connector.connect', 'sqlite3.connect',
                       'requests.sessions.Session.request', 'openai.OpenAI'):
            blocker = patch(target, side_effect=AssertionError('Legacy/API access forbidden'))
            blocker.start()
            self.addCleanup(blocker.stop)
        def call(path, method='GET', body=None, cookie=''):
            return asyncio.run(request(path, method, body, cookie))
        users = {}
        for name, role in [('writer', 'JOURNALIST'), ('other', 'JOURNALIST'),
                           ('editor', 'EDITOR'), ('reader', 'READER'), ('admin', 'ADMIN')]:
            status, row, _ = call('/api/auth/signup', 'POST', {'username': name, 'password': PASSWORD})
            self.assertEqual(status, 201)
            with store.connect(True) as db:
                db.execute('UPDATE users SET role=? WHERE id=?', (role, row['id']))
            status, _, headers = call('/api/auth/login', 'POST', {'username': name, 'password': PASSWORD})
            self.assertEqual(status, 200)
            users[name] = dict(row, role=role, cookie=headers['set-cookie'].split(';')[0])
        self.assertEqual(call('/api/auth/signup', 'POST', {'username':'writer','password':PASSWORD})[0], 409)
        self.assertEqual(call('/api/editorial/articles', cookie=users['reader']['cookie'])[0], 403)
        self.assertEqual(call('/api/auth/users/'+str(users['admin']['id'])+'/role', 'PUT',
                              {'role':'READER'}, users['admin']['cookie'])[0], 409)
        for _ in range(10):
            self.assertEqual(call('/api/auth/login', 'POST', {'username':'missing','password':PASSWORD})[0], 401)
        self.assertEqual(call('/api/auth/login', 'POST', {'username':'missing','password':PASSWORD})[0], 429)
        # Actual PostgreSQL catalog insert, conflict update, join, and reconnect.
        conn = site.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute('INSERT INTO tracks(artist,track) VALUES(%s,%s)', ('SYNTHETIC', 'TEST'))
            song = cur.lastrowid
            for streams in (100, 200):
                cur.execute('INSERT INTO spotify_chart(song_id,spotify_rank,spotify_streams,chart_date,collected_at) '
                            'VALUES(%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE spotify_streams=VALUES(spotify_streams)',
                            (song, 1, streams, '2026-10-08', '2026-10-09 00:00:00'))
            cur.execute('INSERT INTO youtube_stats(song_id,youtube_video_id,youtube_title,youtube_channel,'
                        'youtube_views,youtube_likes,youtube_comments,collected_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)',
                        (song, 'synthetic01', 'TEST', 'TEST', 1000, 10, 1, '2026-10-09 00:00:00'))
            conn.commit()
        finally:
            conn.close()
        with patch('news.youtube_display_resolver.apply_approved_youtube_videos', side_effect=lambda rows,*a:rows):
            rows = site.get_dashboard_data()
        self.assertEqual(rows[0]['spotify_streams'], 200)
        self.assertEqual(rows[0]['youtube_views'], 1000)
        def select(value):
            token = auth.current_user.set(users['writer'])
            try:
                auth.UserSelection().append(value)
            finally:
                auth.current_user.reset(token)
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(select, range(8)))
        with store.connect() as db:
            self.assertEqual(len(json.loads(db.execute('SELECT selection FROM users WHERE id=?',
                              (users['writer']['id'],)).fetchone()[0])), 8)
            self.assertEqual(db.execute('SELECT selection FROM users WHERE id=?',
                             (users['other']['id'],)).fetchone()[0], '[]')
        # The AI feature reads the same PostgreSQL-backed personal selection.
        from news import selected_news
        token = auth.current_user.set(users['writer'])
        try:
            auth.UserSelection().clear()
            auth.UserSelection().append(song)
            self.assertEqual(selected_news.read_current_selection()[0]['song_id'], song)
        finally:
            auth.current_user.reset(token)
        # New-week reviewed facts must load from PostgreSQL even without SQLite.
        from tests.test_weekly_facts import WeeklyFactTests
        from news import weekly_facts as wf
        fixture = WeeklyFactTests()
        fixture.setUp()
        try:
            body = {key: fixture.review[key] for key in
                    ('draft_sha256', 'period_evidence', 'period_review', 'tracks')}
            endpoint = f'/api/editorial/fact-drafts/{fixture.week}/review'
            self.assertEqual(call(endpoint, 'POST', body, users['writer']['cookie'])[0], 403)
            self.assertEqual(call(endpoint, 'POST', body, users['editor']['cookie'])[0], 200)
            with patch.object(wf, 'ROOT', fixture.root):
                facts = wf.load_reviewed(fixture.root, fixture.week)
                self.assertEqual(facts['human_review']['reviewer'], f"user:{users['editor']['id']}")
                self.assertIn('editorial-db:fact_reviews/', editorial.fresh_evidence(fixture.week)[2])
                self.assertEqual(call('/api/news/preview?week_end='+fixture.week,
                                      cookie=users['writer']['cookie'])[0], 200)
        finally:
            fixture.doCleanups()
        evidence = {'synthetic': True}
        with patch.object(editorial, 'fresh_evidence', return_value=(evidence, editorial.digest(evidence), 'SYNTHETIC')):
            status, article, _ = call('/api/editorial/articles','POST',
                                     {'title':'TEST','body':'Synthetic AI draft fixture','week_end':'2026-10-08'},
                                     users['writer']['cookie'])
            self.assertEqual(status, 201)
            path = '/api/editorial/articles/' + str(article['id'])
            self.assertEqual(call(path, cookie=users['other']['cookie'])[0], 404)
            self.assertEqual(call(path+'/submit','POST',{'expected_version':1},users['writer']['cookie'])[0], 200)
            review = {'expected_version':1, 'evidence_hash':article['evidence_hash'],
                      'checklist':dict.fromkeys(['numbers','period_units','no_unsupported_claims','sources'],True),
                      'comment':'Synthetic review', 'decision':'APPROVED'}
            def approve(_):
                return call(path+'/review','POST',review,users['editor']['cookie'])[0]
            with ThreadPoolExecutor(max_workers=2) as pool:
                self.assertEqual(sorted(pool.map(approve, range(2))), [200, 409])
            self.assertEqual(len(call('/api/editorial/published',cookie=users['reader']['cookie'])[1]), 1)
            self.assertEqual(call(path,'PUT',{'expected_version':1,'title':'Edited','body':'New draft',
                             'week_end':'2026-10-08'},users['writer']['cookie'])[0], 200)
            self.assertEqual(call('/api/editorial/published',cookie=users['reader']['cookie'])[1], [])
        # Failed transactions cannot partially persist; each probe has its own transaction.
        with self.assertRaises(ValueError):
            with store.connect(True) as db:
                db.execute("UPDATE users SET selection='[999]' WHERE id=?", (users['writer']['id'],))
                raise ValueError('rollback probe')
        with store.connect() as db:
            self.assertNotEqual(db.execute('SELECT selection FROM users WHERE id=?',
                                (users['writer']['id'],)).fetchone()[0], '[999]')
            self.assertEqual(db.execute('SELECT COUNT(*) FROM reviews').fetchone()[0], 1)
        for table in ('revisions', 'reviews', 'fact_reviews', 'audit'):
            for operation in ('DELETE FROM ', 'TRUNCATE '):
                with self.assertRaises(psycopg.Error):
                    with store.connect(True) as db:
                        db.execute(operation + table)
        self.assertEqual(call('/api/auth/logout','POST',cookie=users['writer']['cookie'])[0],200)
        self.assertEqual(call('/api/auth/me',cookie=users['writer']['cookie'])[0],401)
