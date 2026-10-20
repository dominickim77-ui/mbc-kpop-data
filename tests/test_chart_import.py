"""STEP21 synthetic CSVs only; no new official week or source attestation implied."""
import asyncio
import csv
import io
import json
import shutil
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from news import chart_import as intake
from news.chart_data_manager import choose_pair, scan_chart_weeks
from news.weekly_chart_analysis import build_weekly_rows

ROOT = Path(__file__).resolve().parents[1]


def fixture(platform, delta=0):
    count, fields, _, _ = intake.SPECS[platform]
    out = io.StringIO(newline='')
    writer = csv.writer(out)
    writer.writerow(fields)
    for rank in range(1, count + 1):
        writer.writerow([rank, f'TEST Artist {rank}', f'TEST Song {rank}', 100000 - rank + delta])
    return out.getvalue().encode('utf-8')


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'app'
        self.inbox = Path(self.temp.name) / 'input'
        self.inbox.mkdir()
        shutil.copytree(ROOT / 'data/charts', self.root / 'data/charts')
        shutil.copytree(ROOT / 'data/chart_registry', self.root / 'data/chart_registry')
        self.end = '2026-10-15'
        self.metadata = {}
        for p, (_, _, host, metric) in intake.SPECS.items():
            (self.inbox / f'{p}.csv').write_bytes(fixture(p))
            self.metadata[p] = {
                'source_url': f'https://{host}/TEST-FIXTURE', 'region': 'Global',
                'chart_type': 'weekly_top_songs', 'metric': metric,
                'week_start': '2026-10-09', 'week_end': self.end, 'timezone': 'UTC',
                'source_confirmed': True, 'period_confirmed': True,
                'reviewer': 'SYNTHETIC TEST — NOT A REAL SOURCE REVIEW',
                'source_evidence': 'Synthetic fixture for isolated tests only',
                'period_basis': 'Synthetic test period',
                'usage_status': 'confirmed_local_analysis', 'usage_evidence': 'Self-generated test rows',
                'downloaded_at': '2026-10-16T12:00:00+00:00',
            }
        self.save_metadata()
        self.originals = self.hashes()

    def save_metadata(self):
        for p in intake.SPECS:
            self.metadata[p]['sha256'] = intake.sha256((self.inbox / f'{p}.csv').read_bytes())
        (self.inbox / 'source.json').write_bytes(intake.json_bytes(self.metadata))

    def run_import(self, apply=False):
        return intake.import_week(self.root, self.inbox / 'spotify.csv', self.inbox / 'youtube.csv',
                                  self.inbox / 'source.json', self.end, apply)

    def hashes(self):
        return {p.relative_to(self.root).as_posix(): intake.sha256(p.read_bytes())
                for p in self.root.rglob('*') if p.is_file()}

    def assert_originals(self):
        now = self.hashes()
        for path, digest in self.originals.items():
            self.assertEqual(now[path], digest, path)

    def test_dry_run_has_no_writes(self):
        r = self.run_import()
        self.assertEqual(r['status'], 'PASS')
        self.assertFalse(r['registered'])
        self.assertTrue(r['comparable'])
        self.assertEqual(self.originals, self.hashes())
        self.assertEqual(str(choose_pair(self.root)[0].current_end), '2026-10-08')

    def test_observed_windows_legacy_newlines_preserved(self):
        for path in (self.root / 'data/charts/youtube').glob('*.csv'):
            path.write_bytes(path.read_bytes().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n'))
        pair = choose_pair(self.root)[0]
        self.assertEqual(str(pair.current_end), '2026-10-08')

    def test_register_then_restart_and_repeat_no_duplicate(self):
        r = self.run_import(True)
        self.assertTrue(r['registered'], r)
        pair = choose_pair(self.root)[0]
        self.assertEqual(str(pair.current_end), self.end)
        raw_files = list((self.root / intake.OBJECTS).glob('*.csv'))
        self.assertEqual(len(raw_files), 2)
        manifest = (self.root / intake.WEEKS / f'{self.end}.json').read_bytes()
        repeated = self.run_import(True)
        self.assertEqual(repeated['status'], 'SKIP')
        self.assertEqual((self.root / intake.WEEKS / f'{self.end}.json').read_bytes(), manifest)
        self.assert_originals()

    def test_conflict_never_overwrites(self):
        self.run_import(True)
        path = self.root / intake.WEEKS / f'{self.end}.json'
        before = path.read_bytes()
        (self.inbox / 'spotify.csv').write_bytes(fixture('spotify', 1))
        self.save_metadata()
        r = self.run_import(True)
        self.assertEqual(r['code'], 'CONFLICT')
        self.assertEqual(path.read_bytes(), before)
        self.assert_originals()

    def test_unregistered_csv_is_not_discovered(self):
        (self.root / 'data/charts/spotify/regional-global-weekly-2026-10-15.csv').write_bytes(fixture('spotify'))
        (self.root / 'data/charts/youtube/youtube-charts-top-songs-global-weekly-20261015.csv').write_bytes(fixture('youtube'))
        self.assertEqual(len(scan_chart_weeks(self.root)[0]), 1)

    def test_missing_platform_retains_old_week(self):
        (self.inbox / 'youtube.csv').unlink()
        self.assertEqual(self.run_import(True)['status'], 'FAIL')
        self.assertEqual(str(choose_pair(self.root)[0].current_end), '2026-10-08')

    def test_malformed_csv_variants(self):
        valid = fixture('spotify').decode()
        variants = {
            'header': valid.replace('rank,artist_names', 'rank,rank'),
            'rank': valid.replace('2,TEST Artist 2,', '1,TEST Artist 2,'),
            'negative': valid.replace('99999', '-1'),
            'empty_artist': valid.replace('TEST Artist 1,', ','),
            'duplicate_song': valid.replace('TEST Artist 2,TEST Song 2', 'TEST Artist 1,TEST Song 1'),
            'short': '\n'.join(valid.splitlines()[:-1]),
            'extra_cell': valid.replace('99999', '99999,extra'),
            'float': valid.replace('99999', '99999.0'),
            'malformed_quote': valid + '"unterminated',
        }
        for name, data in variants.items():
            with self.subTest(name=name):
                (self.inbox / 'spotify.csv').write_text(data, encoding='utf-8')
                self.save_metadata()
                self.assertEqual(self.run_import(True)['status'], 'FAIL')
                self.assertEqual(str(choose_pair(self.root)[0].current_end), '2026-10-08')
        self.assert_originals()

    def test_source_and_usage_gates(self):
        cases = [('source_confirmed', False), ('source_confirmed', 'true'),
                 ('period_confirmed', False), ('usage_status', 'unknown'),
                 ('source_url', 'https://charts.spotify.com.evil.example/test'),
                 ('source_url', 'https://charts.spotify.com/test?token=secret'),
                 ('week_start', '2026-10-08'), ('region', 'KR'), ('metric', 'lifetime_views'),
                 ('timezone', 'Asia/Seoul'), ('reviewer', ''), ('downloaded_at', '2026-10-01T00:00:00Z')]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                old = self.metadata['spotify'][field]
                self.metadata['spotify'][field] = value
                self.save_metadata()
                self.assertEqual(self.run_import()['status'], 'BLOCKED')
                self.metadata['spotify'][field] = old

    def test_source_hash_mismatch(self):
        (self.inbox / 'spotify.csv').write_bytes(fixture('spotify', 1))
        self.assertEqual(self.run_import()['code'], 'SOURCE_HASH')

    def test_relabelled_old_week_blocked(self):
        for p, name in [('spotify', 'regional-global-weekly-2026-10-08.csv'),
                        ('youtube', 'youtube-charts-top-songs-global-weekly-20261008.csv')]:
            shutil.copyfile(self.root / 'data/charts' / p / name, self.inbox / f'{p}.csv')
        self.save_metadata()
        self.assertEqual(self.run_import()['code'], 'REUSED_WEEK')

    def test_missing_legacy_file_cannot_be_replaced_by_import(self):
        self.end = '2026-10-08'
        for m in self.metadata.values():
            m.update(week_start='2026-10-02', week_end=self.end)
        self.save_metadata()
        (self.root / 'data/charts/spotify/regional-global-weekly-2026-10-08.csv').unlink()
        self.assertEqual(self.run_import(True)['code'], 'CONFLICT')

    def test_duplicate_json_key_and_nonobject_provenance(self):
        for raw in (b'{"spotify":{},"spotify":{}}', b'[]'):
            (self.inbox / 'source.json').write_bytes(raw)
            self.assertIn(self.run_import()['status'], ('FAIL', 'BLOCKED'))

    def test_partial_object_write_failure_never_publishes(self):
        original = intake._write_new
        def fail_second(path, raw):
            if path.parent.name == 'objects' and path.name == intake.sha256(fixture('youtube')) + '.csv':
                raise OSError('simulated second object failure')
            return original(path, raw)
        with patch.object(intake, '_write_new', side_effect=fail_second):
            result = self.run_import(True)
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(str(choose_pair(self.root)[0].current_end), '2026-10-08')
        self.assertTrue(self.run_import(True)['registered'])

    def test_existing_corrupt_object_never_overwritten(self):
        path = self.root / intake.OBJECTS / (intake.sha256(fixture('spotify')) + '.csv')
        path.parent.mkdir(parents=True)
        path.write_bytes(b'corrupted')
        self.assertEqual(self.run_import(True)['code'], 'OBJECT_CONFLICT')
        self.assertEqual(path.read_bytes(), b'corrupted')

    def test_rank_amount_order_requires_review(self):
        raw = fixture('spotify').replace(b'99999', b'1')
        (self.inbox / 'spotify.csv').write_bytes(raw)
        self.save_metadata()
        self.assertEqual(self.run_import()['code'], 'ORDER_REVIEW')

    def test_direct_cli_dry_run_exit_and_no_writes(self):
        from contextlib import redirect_stdout
        output = io.StringIO()
        with redirect_stdout(output):
            code = intake.main(['--root', str(self.root), '--spotify', str(self.inbox / 'spotify.csv'),
                                '--youtube', str(self.inbox / 'youtube.csv'),
                                '--provenance', str(self.inbox / 'source.json'), '--week-end', self.end])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())['status'], 'PASS')
        self.assertEqual(self.originals, self.hashes())

    def test_invalid_and_future_period(self):
        for end in ('2026-10-16', '2030-01-03', '../invalid', '2026-99-15'):
            self.end = end
            self.assertEqual(self.run_import(True)['code'], 'PERIOD')

    def test_invalid_encoding_and_oversized_file(self):
        (self.inbox / 'spotify.csv').write_bytes(b'\xff\xff')
        self.save_metadata()
        self.assertEqual(self.run_import()['code'], 'CSV')
        (self.inbox / 'spotify.csv').write_bytes(b' ' * (intake.MAX_BYTES + 1))
        self.assertEqual(self.run_import()['code'], 'SIZE')

    def test_bom_preserved_byte_for_byte(self):
        raw = b'\xef\xbb\xbf' + fixture('spotify')
        (self.inbox / 'spotify.csv').write_bytes(raw)
        self.save_metadata()
        r = self.run_import(True)
        self.assertTrue(r['registered'], r)
        self.assertEqual((self.root / r['planned_files']['spotify']['path']).read_bytes(), raw)

    def test_failure_before_commit_then_retry(self):
        with patch.object(intake.os, 'replace', side_effect=OSError('simulated disk failure')):
            r = self.run_import(True)
        self.assertEqual(r['status'], 'FAIL')
        self.assertEqual(str(choose_pair(self.root)[0].current_end), '2026-10-08')
        self.assertTrue((self.root / r['staging'] / 'failure.json').exists())
        self.assertTrue(self.run_import(True)['registered'])
        self.assert_originals()

    def test_lock_blocks_writer_and_keeps_old_week(self):
        with intake.writer_lock(self.root):
            r = self.run_import(True)
        self.assertEqual(r['code'], 'LOCKED')
        self.assertEqual(str(choose_pair(self.root)[0].current_end), '2026-10-08')

    def test_concurrent_registration_has_one_commit(self):
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda _: self.run_import(True), range(2)))
        self.assertEqual(sum(r['registered'] for r in results), 1, results)
        self.assertEqual(len(list((self.root / intake.WEEKS).glob('*.json'))), 1)

    def test_tampered_object_excludes_new_week_only(self):
        r = self.run_import(True)
        (self.root / r['planned_files']['spotify']['path']).write_bytes(fixture('spotify', 3))
        pair, _, notes = choose_pair(self.root)
        self.assertEqual(str(pair.current_end), '2026-10-08')
        self.assertTrue(notes)
        self.assertEqual(self.run_import(True)['code'], 'CONFLICT')

    def test_corrupt_manifest_not_overwritten(self):
        r = self.run_import(True)
        path = self.root / intake.WEEKS / f'{self.end}.json'
        path.write_text('{bad', encoding='utf-8')
        self.assertEqual(str(choose_pair(self.root)[0].current_end), '2026-10-08')
        self.assertEqual(self.run_import(True)['code'], 'CONFLICT')
        self.assertEqual(path.read_text(), '{bad')

    def test_manifest_path_traversal_excluded(self):
        self.run_import(True)
        path = self.root / intake.WEEKS / f'{self.end}.json'
        m = json.loads(path.read_text())
        m['files']['spotify']['path'] = '../outside.csv'
        path.write_bytes(intake.json_bytes(m))
        self.assertEqual(str(choose_pair(self.root)[0].current_end), '2026-10-08')

    def test_gap_registered_but_not_comparable(self):
        # Use an earlier completed week without a preceding registered week.
        self.end = '2026-09-17'
        for m in self.metadata.values():
            m.update(week_start='2026-09-11', week_end=self.end)
        self.save_metadata()
        r = self.run_import(True)
        self.assertTrue(r['registered'])
        self.assertFalse(r['comparable'])
        self.assertEqual(len(scan_chart_weeks(self.root)[0]), 1)

    def test_dashboard_http_new_week_without_db_or_api(self):
        self.run_import(True)
        import app as site
        from tests.support.asgi import form_request
        pair = choose_pair(self.root)[0]
        def choose(week_end=''):
            return choose_pair(self.root, week_end)
        def build(selected, pair=None):
            return build_weekly_rows(selected, root=self.root, pair=pair)
        selected = [{'song_id': 999, 'artist': 'TEST Artist 1', 'track': 'TEST Song 1',
                     'spotify_rank': 1, 'spotify_streams': 99999, 'chart_date': self.end,
                     'youtube_views': None, 'youtube_likes': None, 'youtube_comments': None,
                     'youtube_video_id': None, 'youtube_title': None, 'youtube_channel': None,
                     'collected_at': None}]
        selection_patch = patch.object(site, 'analysis_song_ids', [])
        selection_patch.start()
        self.addCleanup(selection_patch.stop)
        prior = list(site.analysis_song_ids)
        site.analysis_song_ids[:] = [999]
        try:
            with patch.object(site, 'choose_pair', side_effect=choose), \
                 patch.object(site, 'build_weekly_rows', side_effect=build), \
                 patch('news.weekly_chart_analysis.ROOT', self.root), \
                 patch.object(site, 'get_dashboard_data', return_value=selected), \
                 patch.object(site, 'get_db_connection', side_effect=AssertionError('DB forbidden')):
                status, _, body = asyncio.run(form_request('/?week_end=2026-10-15', method='GET'))
                self.assertEqual(status, 200)
                self.assertIn(b'2026-10-15', body)
                self.assertIn(b'TEST Song 1', body)
                status, _, body = asyncio.run(form_request('/?artist=TEST&week_end=2026-10-15', method='GET'))
                self.assertEqual(status, 200)
                self.assertIn(b'TEST Song 200', body)
                status, _, body = asyncio.run(form_request('/compare?week_end=2026-10-15', method='GET'))
                self.assertEqual(status, 200)
                self.assertIn(b'2026-10-15', body)
        finally:
            site.analysis_song_ids[:] = prior
        rows = build_weekly_rows(selected, root=self.root, pair=pair)
        self.assertIsNone(rows[0]['spotify_prev'])
        self.assertEqual(rows[0]['spotify_current'], 99999)
        self.assertNotEqual(rows[0]['review_code'], 'reviewed')

    def test_new_week_news_remains_blocked(self):
        self.run_import(True)
        from news import news_routes
        from tests.support.asgi import asgi_request
        with patch.object(news_routes, 'generate_paid_article') as paid:
            status, _ = asyncio.run(asgi_request('/api/news/preview?week_end=2026-10-15'))
        self.assertEqual(status, 409)
        paid.assert_not_called()


if __name__ == '__main__':
    unittest.main()
