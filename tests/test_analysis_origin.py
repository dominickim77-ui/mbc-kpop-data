"""Native-form ASGI regressions; real DB and HTTP calls are forbidden."""
import asyncio
import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode, unquote_plus

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import app as site
from test_step19_p1 import FakeDB

PATHS = ('/add-analysis', '/remove-analysis/7', '/reset-analysis')


async def form_request(path, headers=None, form=None, method='POST', scheme='http'):
    raw_headers = list(headers if headers is not None else [
        ('host', '127.0.0.1:8000'), ('origin', 'http://127.0.0.1:8000')])
    raw_headers.append(('content-type', 'application/x-www-form-urlencoded'))
    route, _, query = path.partition('?')
    scope = {'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
             'method': method, 'scheme': scheme, 'path': route, 'raw_path': route.encode(),
             'query_string': query.encode(), 'root_path': '',
             'headers': [(k.encode(), v.encode()) for k, v in raw_headers],
             'client': ('127.0.0.1', 1234), 'server': ('127.0.0.1', 8000)}
    data = form if form is not None else {'selected_ranks': [1], 'search_artist': 'KATSEYE',
                                         'week_end': '2026-10-08'}
    events, sent = [], False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {'type': 'http.request', 'body': urlencode(data, doseq=True).encode(), 'more_body': False}
        return {'type': 'http.disconnect'}

    async def send(event):
        events.append(event)

    await site.app(scope, receive, send)
    start = next(e for e in events if e['type'] == 'http.response.start')
    body = b''.join(e.get('body', b'') for e in events if e['type'] == 'http.response.body')
    return start['status'], dict((k.decode(), v.decode()) for k, v in start['headers']), body


class AnalysisOriginTests(unittest.TestCase):
    def setUp(self):
        self.prior = list(site.analysis_song_ids)
        site.analysis_song_ids[:] = [7, 8]
        self.addCleanup(lambda: site.analysis_song_ids.__setitem__(slice(None), self.prior))
        for target in ['mysql.connector.connect', 'requests.sessions.Session.request']:
            guard = patch(target, side_effect=AssertionError('Real DB/API access forbidden'))
            guard.start()
            self.addCleanup(guard.stop)

    def assert_rejected(self, headers, scheme='http'):
        for path in PATHS:
            with self.subTest(path=path, headers=headers):
                site.analysis_song_ids[:] = [7, 8]
                with patch.object(site, '_add_analysis', wraps=site._add_analysis) as add, \
                     patch.object(site, 'get_db_connection', side_effect=AssertionError('Denied request touched DB')) as db:
                    status, _, body = asyncio.run(form_request(path, headers=headers, scheme=scheme))
                    self.assertEqual(status, 403)
                    self.assertEqual(site.analysis_song_ids, [7, 8])
                    add.assert_not_called()
                    db.assert_not_called()
                    return_body = body
        return return_body

    def assert_native_forms_accepted(self, headers):
        for path in PATHS:
            with self.subTest(path=path, headers=headers):
                site.analysis_song_ids[:] = [7, 8]
                fake = FakeDB()
                with patch.object(site, 'get_db_connection', return_value=fake) as db:
                    status, response_headers, _ = asyncio.run(form_request(path, headers=headers))
                self.assertEqual(status, 303)
                self.assertIn('week_end=2026-10-08', response_headers['location'])
                if path == '/add-analysis':
                    self.assertTrue(fake.committed)
                    self.assertEqual(site.analysis_song_ids, [7, 8, 100])
                    self.assertIn('artist=KATSEYE', response_headers['location'])
                    db.assert_called_once()
                elif path == '/remove-analysis/7':
                    self.assertEqual(site.analysis_song_ids, [8])
                    db.assert_not_called()
                else:
                    self.assertEqual(site.analysis_song_ids, [])
                    db.assert_not_called()

    def test_native_forms_on_both_documented_origins(self):
        for host in ['127.0.0.1:8000', 'localhost:8000']:
            self.assert_native_forms_accepted([('host', host), ('origin', 'http://' + host)])

    def test_origin_absent_uses_same_origin_referer(self):
        self.assert_native_forms_accepted([('host', '127.0.0.1:8000'),
            ('referer', 'http://127.0.0.1:8000/?artist=KATSEYE&week_end=2026-10-08')])

    def test_case_and_effective_port_normalization(self):
        self.assert_native_forms_accepted([('host', 'LOCALHOST:8000'), ('origin', 'HTTP://localhost:08000')])

    def test_valid_fetch_metadata(self):
        for value in ['same-origin', 'same-site', 'none']:
            self.assert_native_forms_accepted([('host', '127.0.0.1:8000'),
                ('origin', 'http://127.0.0.1:8000'), ('sec-fetch-site', value)])

    def test_external_origin_rejected(self):
        self.assert_rejected([('host', '127.0.0.1:8000'), ('origin', 'https://untrusted.example')])

    def test_other_port_scheme_and_local_alias_rejected(self):
        for origin in ['http://127.0.0.1:9000', 'https://127.0.0.1:8000', 'http://localhost:8000']:
            self.assert_rejected([('host', '127.0.0.1:8000'), ('origin', origin)])

    def test_null_or_bad_origin_cannot_fall_back_to_referer(self):
        for origin in ['null', '', 'https://untrusted.example']:
            self.assert_rejected([('host', '127.0.0.1:8000'), ('origin', origin),
                                  ('referer', 'http://127.0.0.1:8000/')])

    def test_missing_both_source_headers_rejected(self):
        self.assert_rejected([('host', '127.0.0.1:8000')])

    def test_missing_origin_and_bad_referer_rejected_without_reflection(self):
        for referer in ['', 'null', 'https://untrusted.example/path?private=fixture_secret',
                        'http://127.0.0.1:9000/', 'http://localhost:8000/']:
            body = self.assert_rejected([('host', '127.0.0.1:8000'), ('referer', referer)])
            self.assertNotIn(b'fixture_secret', body)

    def test_malformed_origins_rejected(self):
        for origin in ['http://127.0.0.1:8000/', 'http://127.0.0.1:8000?',
                       'http://127.0.0.1:8000#', 'http://user@127.0.0.1:8000',
                       'http://127.0.0.1:8000@untrusted.example', 'http://127.0.0.1:bad',
                       'http://127.0.0.1:65536', 'http://127.0.0.1:0', 'http://127.0.0.1:',
                       'http://127.0.0.1:8000,http://localhost:8000',
                       ' http://127.0.0.1:8000', 'http://127.0.0.1:8000\t',
                       'http://127.0.0.1:8000\\evil', 'http://127%2e0.0.1:8000',
                       'http://127.0.0.1.attacker.example:8000']:
            self.assert_rejected([('host', '127.0.0.1:8000'), ('origin', origin)])

    def test_untrusted_host_cannot_allowlist_itself(self):
        for host in ['untrusted.example:8000', 'localhost.attacker.example:8000',
                     '127.0.0.1:9000', '[::1]:8000', 'user@127.0.0.1:8000', '127.0.0.1:8000/']:
            self.assert_rejected([('host', host), ('origin', 'http://' + host)])

    def test_missing_host_rejected(self):
        self.assert_rejected([('origin', 'http://127.0.0.1:8000')])

    def test_duplicate_security_headers_rejected(self):
        base = [('host', '127.0.0.1:8000'), ('origin', 'http://127.0.0.1:8000')]
        for extra in [[('host', '127.0.0.1:8000')], [('origin', 'http://127.0.0.1:8000')],
                      [('referer', 'http://127.0.0.1:8000/')] * 2,
                      [('sec-fetch-site', 'same-origin')] * 2]:
            self.assert_rejected(base + extra)

    def test_cross_site_metadata_overrides_usable_source(self):
        for value in ['cross-site', '', 'unknown']:
            self.assert_rejected([('host', '127.0.0.1:8000'), ('origin', 'http://127.0.0.1:8000'),
                                  ('sec-fetch-site', value)])

    def test_same_site_or_none_metadata_does_not_replace_source(self):
        for value in ['same-site', 'none', 'same-origin']:
            self.assert_rejected([('host', '127.0.0.1:8000'), ('sec-fetch-site', value)])

    def test_forwarded_headers_do_not_bypass_target_allowlist(self):
        self.assert_rejected([('host', 'untrusted.example:8000'), ('origin', 'http://127.0.0.1:8000'),
                              ('x-forwarded-host', '127.0.0.1:8000'), ('x-forwarded-proto', 'http')])
        self.assert_rejected([('host', '127.0.0.1:8000'), ('origin', 'http://127.0.0.1:8000'),
                              ('x-forwarded-proto', 'http')], scheme='https')

    def test_accepted_add_commit_failure_preserves_p1_state(self):
        fake = FakeDB(fail_commit=True)
        with patch.object(site, 'get_db_connection', return_value=fake):
            status, headers, _ = asyncio.run(form_request('/add-analysis'))
        self.assertEqual(status, 303)
        self.assertEqual(fake.selection_at_commit, [7, 8])
        self.assertEqual(site.analysis_song_ids, [7, 8])
        self.assertTrue(fake.rolled_back)
        self.assertNotIn('Analysis에 추가했습니다', unquote_plus(headers['location']))

    def test_accepted_add_insert_failure_preserves_p1_state(self):
        fake = FakeDB(fail_write=2)
        with patch.object(site, 'get_db_connection', return_value=fake):
            status, _, _ = asyncio.run(form_request('/add-analysis', form={
                'selected_ranks': [1, 2], 'week_end': '2026-10-08'}))
        self.assertEqual(status, 303)
        self.assertEqual(site.analysis_song_ids, [7, 8])
        self.assertTrue(fake.rolled_back)

    def test_accepted_add_publishes_only_after_commit(self):
        fake = FakeDB()
        with patch.object(site, 'get_db_connection', return_value=fake):
            status, _, _ = asyncio.run(form_request('/add-analysis'))
        self.assertEqual(status, 303)
        self.assertEqual(fake.selection_at_commit, [7, 8])
        self.assertEqual(site.analysis_song_ids, [7, 8, 100])

    def test_accepted_concurrent_reset_preserves_p1_serialization(self):
        entered, release, reset_started = threading.Event(), threading.Event(), threading.Event()
        fake = FakeDB()

        def commit_hook():
            entered.set()
            if not release.wait(5):
                raise AssertionError('Commit release timeout')

        def reset_request():
            reset_started.set()
            return asyncio.run(form_request('/reset-analysis'))

        fake.commit_hook = commit_hook
        with patch.object(site, 'get_db_connection', return_value=fake), ThreadPoolExecutor(2) as pool:
            added = pool.submit(asyncio.run, form_request('/add-analysis'))
            self.assertTrue(entered.wait(5))
            reset = pool.submit(reset_request)
            self.assertTrue(reset_started.wait(5))
            release.set()
            self.assertEqual(added.result(timeout=5)[0], 303)
            self.assertEqual(reset.result(timeout=5)[0], 303)
        self.assertEqual(site.analysis_song_ids, [])

    def test_readonly_get_pages_do_not_require_source_headers(self):
        for path in ['/', '/?artist=KATSEYE&week_end=2026-10-08', '/spotify', '/youtube', '/compare']:
            with self.subTest(path=path), patch.object(site, 'get_dashboard_data', return_value=[]):
                status, _, _ = asyncio.run(form_request(path, headers=[('host', '127.0.0.1:8000')], method='GET'))
                self.assertEqual(status, 200)

    def test_analysis_mutations_remain_post_only(self):
        for path in PATHS:
            with self.subTest(path=path):
                status, _, _ = asyncio.run(form_request(path, method='GET'))
                self.assertEqual(status, 405)
                self.assertEqual(site.analysis_song_ids, [7, 8])

    def test_existing_form_template_remains_native(self):
        template = (ROOT / 'templates/index.html').read_text(encoding='utf-8')
        for action in ['/add-analysis', '/reset-analysis', '/remove-analysis/{{ item.song_id }}']:
            self.assertIn(f'<form method="post" action="{action}">', template)
        self.assertIn('name="week_end" value="{{ selected_week_end }}"', template)


if __name__ == '__main__':
    unittest.main(verbosity=2)
