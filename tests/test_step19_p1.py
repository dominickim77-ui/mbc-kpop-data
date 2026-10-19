"""STEP19 P1 regressions. Real DB/API calls are forbidden; data edits use temp copies.

Run from repository root: python -B -m unittest discover -s tests -p test_step19_p1.py -v
"""
import asyncio
import copy
import csv
import json
import shutil
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote_plus

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import app as site
import pandas as pd
from news import selected_news as selection, news_routes as routes
from news.chart_data_manager import choose_pair


async def asgi_request(path, method='GET', payload=None):
    events = []
    headers = {'host': '127.0.0.1:8000', 'origin': 'http://127.0.0.1:8000',
               'content-type': 'application/json', 'x-requested-with': 'KpopNewsPanel'}
    route, _, query = path.partition('?')
    scope = {'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
             'method': method, 'scheme': 'http', 'path': route, 'raw_path': route.encode(),
             'query_string': query.encode(), 'root_path': '',
             'headers': [(k.encode(), v.encode()) for k, v in headers.items()],
             'client': ('127.0.0.1', 1234), 'server': ('127.0.0.1', 8000)}
    delivered = False

    async def receive():
        nonlocal delivered
        if not delivered:
            delivered = True
            return {'type': 'http.request', 'body': json.dumps(payload).encode() if payload else b'',
                    'more_body': False}
        return {'type': 'http.disconnect'}

    async def send(event):
        events.append(event)

    await site.app(scope, receive, send)
    status = next(e['status'] for e in events if e['type'] == 'http.response.start')
    body = b''.join(e.get('body', b'') for e in events if e['type'] == 'http.response.body')
    return status, json.loads(body)


class OfflineCase(unittest.TestCase):
    def setUp(self):
        self.api_guard = patch('requests.sessions.Session.request', side_effect=AssertionError('Real HTTP forbidden'))
        self.db_guard = patch('mysql.connector.connect', side_effect=AssertionError('Real DB forbidden'))
        self.api_guard.start()
        self.db_guard.start()
        self.addCleanup(self.api_guard.stop)
        self.addCleanup(self.db_guard.stop)


class ArticleEvidenceTests(OfflineCase):
    def setUp(self):
        super().setUp()
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        shutil.copytree(ROOT / 'data/charts', self.root / 'data/charts')
        (self.root / 'facts').mkdir()
        self.fact_path = self.root / 'facts/article_ready_fact_sheet_20261008.json'
        shutil.copyfile(ROOT / 'facts' / self.fact_path.name, self.fact_path)
        self.facts = json.loads(self.fact_path.read_text(encoding='utf-8'))
        self.selected = [{'song_id': i+1, 'artist': t['artist'], 'track': t['track_name']}
                         for i, t in enumerate(self.facts['analysis_tracks'])]
        for target, name, value in [(selection, 'ROOT', self.root), (selection, 'FACT_PATH', self.fact_path),
                                    (routes, 'ROOT', self.root), (routes, 'ARTICLES', self.root / 'articles')]:
            mock = patch.object(target, name, value)
            mock.start()
            self.addCleanup(mock.stop)
        mock = patch.object(routes, 'read_current_selection', return_value=self.selected)
        mock.start()
        self.addCleanup(mock.stop)

    def current_spotify(self):
        return self.root / 'data/charts/spotify/regional-global-weekly-2026-10-08.csv'

    def alter_chart(self, action):
        path = self.current_spotify()
        with path.open(encoding='utf-8-sig', newline='') as fh:
            reader = csv.DictReader(fh)
            names, rows = reader.fieldnames, list(reader)
        animal = next(r for r in rows if r['track_name'] == 'Animal' and r['artist_names'] == 'KATSEYE')
        action(rows, animal)
        with path.open('w', encoding='utf-8-sig', newline='') as fh:
            writer = csv.DictWriter(fh, fieldnames=names)
            writer.writeheader()
            writer.writerows(rows)

    def assert_generation_blocked(self, expected=422):
        with patch.object(routes, 'generate_paid_article') as paid:
            status, _ = asyncio.run(asgi_request('/api/news/preview?week_end=2026-10-08'))
            self.assertEqual(status, expected)
            status, _ = asyncio.run(asgi_request('/api/news/generate', 'POST',
                                                {'confirm_paid': True, 'week_end': '2026-10-08'}))
            self.assertEqual(status, expected)
            paid.assert_not_called()
        self.assertFalse((self.root / 'articles').exists())

    def test_approved_two_track_preview(self):
        status, data = asyncio.run(asgi_request('/api/news/preview?week_end=2026-10-08'))
        self.assertEqual(status, 200)
        self.assertIn('Animal', data['article'])
        self.assertIn('SaWaDiKa', data['article'])
        self.assertFalse(data['publication_approved'])

    def test_paid_success_uses_verified_evidence_stub_only(self):
        with patch.object(routes, 'generate_paid_article', return_value=('TEST DRAFT', 'offline-stub')) as paid:
            status, data = asyncio.run(asgi_request('/api/news/generate', 'POST',
                                                {'confirm_paid': True, 'week_end': '2026-10-08'}))
            self.assertEqual(status, 200)
            paid.assert_called_once()
            self.assertEqual(len(paid.call_args.args[0]['analysis_tracks']), 2)
            self.assertFalse(data['publication_approved'])
        records = list((self.root / 'articles').glob('*.json'))
        self.assertEqual(len(records), 1)
        self.assertEqual(json.loads(records[0].read_text(encoding='utf-8'))['article_status'],
                         'DRAFT_NOT_FOR_PUBLICATION')

    def test_mutated_fact_with_consistent_rate_blocked(self):
        p = self.facts['analysis_tracks'][0]['spotify']
        p['current_week_streams'] += 1000000
        p['streams_change_pct'] = round((p['current_week_streams']-p['previous_week_streams']) /
                                       p['previous_week_streams']*100, 2)
        self.fact_path.write_text(json.dumps(self.facts), encoding='utf-8')
        self.assert_generation_blocked()

    def test_changed_csv_amount_blocked(self):
        self.alter_chart(lambda rows, a: a.update(streams=str(int(a['streams'])+1)))
        self.assert_generation_blocked()

    def test_changed_csv_rank_blocked(self):
        def swap(rows, a):
            other = next(r for r in rows if r is not a)
            a['rank'], other['rank'] = other['rank'], a['rank']
        self.alter_chart(swap)
        self.assert_generation_blocked()

    def test_ambiguous_song_key_blocked(self):
        def duplicate(rows, a):
            other = next(r for r in rows if r is not a)
            other.update(artist_names=a['artist_names'], track_name=a['track_name'])
        self.alter_chart(duplicate)
        self.assert_generation_blocked()

    def test_missing_each_source_blocked(self):
        for path in (self.root / 'data/charts').rglob('*.csv'):
            with self.subTest(source=path.name):
                raw = path.read_bytes()
                path.unlink()
                try:
                    self.assert_generation_blocked()
                finally:
                    path.write_bytes(raw)

    def test_malformed_csv_blocked(self):
        self.current_spotify().write_text('bad,columns\n1,2\n', encoding='utf-8')
        self.assert_generation_blocked()

    def test_wrong_requested_week_blocked(self):
        with patch.object(routes, 'generate_paid_article') as paid:
            status, _ = asyncio.run(asgi_request('/api/news/generate', 'POST',
                                                {'confirm_paid': True, 'week_end': '2030-01-03'}))
            self.assertEqual(status, 409)
            paid.assert_not_called()

    def test_wrong_fact_period_blocked(self):
        self.facts['week_previous']['start'] = '2026-09-24'
        self.fact_path.write_text(json.dumps(self.facts), encoding='utf-8')
        self.assert_generation_blocked()

    def test_unreviewed_and_excluded_tracks_still_blocked(self):
        for artist, track in [('BTS', 'SWIM'), ('KATSEYE', 'Hootie Frutti')]:
            with self.subTest(track=track), patch.object(routes, 'read_current_selection',
                                                       return_value=[{'artist': artist, 'track': track}]):
                self.assert_generation_blocked()

    def test_source_change_after_selection_rechecked_before_paid(self):
        facts = selection.load_verified_facts()
        snapshot = selection.selected_snapshot(self.selected, facts)
        self.alter_chart(lambda rows, a: a.update(streams=str(int(a['streams'])+1)))
        with patch.object(routes, '_selection', return_value=(facts, snapshot)):
            self.assert_generation_blocked()


class FakeCursor:
    def __init__(self, db):
        self.db = db
        self.lastrowid = 0
        self.result = None
        self.closed = False

    def execute(self, sql, params=()):
        if 'SELECT DISTINCT artist' in sql:
            self.result = [{'artist': f'Existing{i}'} for i in params]
        elif 'SELECT song_id' in sql:
            song_id = self.db.ids.get(tuple(params))
            self.result = {'song_id': song_id} if song_id is not None else None
        elif 'INSERT INTO tracks' in sql:
            self.lastrowid = self.db.next_id
            self.db.next_id += 1
            self.db.ids[tuple(params)] = self.lastrowid
        elif 'INSERT INTO spotify_chart' in sql:
            self.db.writes += 1
            if self.db.fail_write == self.db.writes:
                raise RuntimeError('TEST INSERT FAILURE')
        else:
            raise AssertionError('Unexpected SQL')

    def fetchone(self):
        return self.result

    def fetchall(self):
        return self.result

    def close(self):
        self.closed = True


class FakeDB:
    def __init__(self, fail_commit=False, fail_write=None, next_id=100):
        self.fail_commit = fail_commit
        self.fail_write = fail_write
        self.next_id = next_id
        self.ids = {}
        self.writes = 0
        self.committed = False
        self.rolled_back = False
        self.closed = False
        self.selection_at_commit = None
        self.cur = FakeCursor(self)
        self.commit_hook = None

    def cursor(self, **kwargs):
        return self.cur

    def commit(self):
        self.selection_at_commit = list(site.analysis_song_ids)
        if self.commit_hook:
            self.commit_hook()
        if self.fail_commit:
            raise RuntimeError('TEST COMMIT FAILURE')
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


class AnalysisTransactionTests(OfflineCase):
    def setUp(self):
        super().setUp()
        self.prior = list(site.analysis_song_ids)
        site.analysis_song_ids[:] = [7]
        self.addCleanup(lambda: site.analysis_song_ids.__setitem__(slice(None), self.prior))
        self.pair = choose_pair(root=ROOT, week_end='2026-10-08')[0]
        self.chart = pd.DataFrame([{'rank': i, 'artist_names': f'Artist{i}',
                                   'track_name': f'Track{i}', 'streams': 10000+i}
                                  for i in range(1, 13)])
        for name, value in [('choose_pair', (self.pair, [self.pair], [])),
                            ('load_spotify_csv', self.chart)]:
            mock = patch.object(site, name, return_value=value)
            mock.start()
            self.addCleanup(mock.stop)

    def add(self, db, ranks):
        with patch.object(site, 'get_db_connection', return_value=db):
            return site.add_analysis(selected_ranks=ranks, search_artist='', week_end='2026-10-08')

    def test_commit_failure_preserves_selection_and_no_success_message(self):
        db = FakeDB(fail_commit=True)
        result = self.add(db, [1, 2])
        self.assertEqual(site.analysis_song_ids, [7])
        self.assertTrue(db.rolled_back)
        self.assertTrue(db.closed and db.cur.closed)
        self.assertNotIn('Analysis에 추가했습니다', unquote_plus(result.headers['location']))

    def test_second_insert_failure_discards_all_pending(self):
        db = FakeDB(fail_write=2)
        self.add(db, [1, 2])
        self.assertEqual(site.analysis_song_ids, [7])
        self.assertTrue(db.rolled_back)
        self.assertFalse(db.committed)

    def test_success_published_only_after_commit(self):
        db = FakeDB()
        result = self.add(db, [1, 2])
        self.assertTrue(db.committed)
        self.assertEqual(db.selection_at_commit, [7])
        self.assertEqual(site.analysis_song_ids, [7, 100, 101])
        self.assertIn('Analysis에 추가했습니다', unquote_plus(result.headers['location']))

    def test_duplicate_rank_is_added_once(self):
        db = FakeDB()
        self.add(db, [1, 1])
        self.assertEqual(site.analysis_song_ids, [7, 100])
        self.assertEqual(db.writes, 1)

    def test_existing_selection_not_duplicated(self):
        db = FakeDB()
        db.ids[('Artist1', 'Track1')] = 7
        self.add(db, [1])
        self.assertEqual(site.analysis_song_ids, [7])
        self.assertEqual(db.writes, 0)

    def test_ten_track_limit_counts_pending(self):
        db = FakeDB()
        self.add(db, list(range(1, 13)))
        self.assertEqual(len(site.analysis_song_ids), 10)
        self.assertEqual(db.writes, 9)

    def test_parallel_adds_respect_limit(self):
        site.analysis_song_ids[:] = list(range(1, 10))
        entered, release, second_started = threading.Event(), threading.Event(), threading.Event()
        first, second = FakeDB(), FakeDB(next_id=200)

        def wait_in_commit():
            entered.set()
            if not release.wait(5):
                raise AssertionError('Commit release timeout')

        first.commit_hook = wait_in_commit

        def second_add():
            second_started.set()
            return site.add_analysis(selected_ranks=[2], search_artist='', week_end='2026-10-08')

        with patch.object(site, 'get_db_connection', side_effect=[first, second]), ThreadPoolExecutor(2) as pool:
            one = pool.submit(site.add_analysis, [1], '', '2026-10-08')
            self.assertTrue(entered.wait(5))
            two = pool.submit(second_add)
            self.assertTrue(second_started.wait(5))
            release.set()
            one.result(timeout=5)
            two.result(timeout=5)
        self.assertEqual(len(site.analysis_song_ids), 10)
        self.assertEqual(first.writes + second.writes, 1)

    def test_reset_during_add_is_not_lost(self):
        entered, release, reset_started = threading.Event(), threading.Event(), threading.Event()
        db = FakeDB()

        def wait_in_commit():
            entered.set()
            if not release.wait(5):
                raise AssertionError('Commit release timeout')

        def reset():
            reset_started.set()
            return site.reset_analysis(week_end='2026-10-08')

        db.commit_hook = wait_in_commit
        with patch.object(site, 'get_db_connection', return_value=db), ThreadPoolExecutor(2) as pool:
            one = pool.submit(site.add_analysis, [1], '', '2026-10-08')
            self.assertTrue(entered.wait(5))
            two = pool.submit(reset)
            self.assertTrue(reset_started.wait(5))
            release.set()
            one.result(timeout=5)
            two.result(timeout=5)
        self.assertEqual(site.analysis_song_ids, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
