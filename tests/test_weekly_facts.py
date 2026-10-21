"""Isolated synthetic weeks only. All approval records are test fixtures."""
import copy
import json
import unittest
from unittest.mock import patch

from tests import test_chart_import as fixtures
from news import weekly_facts as wf, selected_news as sn, news_routes as routes, generation
from news import chart_import as intake
from news.chart_data_manager import choose_pair
from news.weekly_chart_analysis import build_weekly_rows
from fastapi import HTTPException
from starlette.requests import Request
from tests.support.generation import generation_session
from news import article_origin
from security import editorial_store as store


class WeeklyFactTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.IntakeTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        f = self.fixture
        self.root = f.root
        self.assertTrue(f.run_import(True)['registered'])
        f.end = '2026-10-22'
        for p in intake.SPECS:
            (f.inbox / f'{p}.csv').write_bytes(fixtures.fixture(p, 500))
            f.metadata[p].update(week_start='2026-10-16', week_end=f.end,
                                 downloaded_at='2026-10-23T12:00:00+00:00')
        f.save_metadata()
        # Future test periods are deterministic via the intake's injectable clock.
        from datetime import datetime, timezone
        with patch.object(intake, 'datetime') as clock:
            clock.now.return_value = datetime(2026, 10, 24, tzinfo=timezone.utc)
            clock.fromisoformat = datetime.fromisoformat
            self.assertTrue(f.run_import(True)['registered'])
        self.week = f.end
        # Registered inventory checks chronology against now too.
        self.clock = patch.object(intake, 'datetime')
        clock = self.clock.start()
        self.addCleanup(self.clock.stop)
        clock.now.return_value = datetime(2026, 10, 24, tzinfo=timezone.utc)
        clock.fromisoformat = datetime.fromisoformat
        self.draft = wf.build_draft(self.root, self.week)
        self.track = self.draft['candidates'][0]
        self.rows = [{'artist': self.track['artist'], 'track': self.track['track_name']}]
        self.review = wf.review_template(self.draft)
        self.review.update(reviewer='SYNTHETIC TEST REVIEW', reviewed_at='2026-10-24T12:00:00+00:00',
                           period_review='CONFIRMED_COMPARABLE_PERIODS', period_evidence='Test UTC periods', tracks=[{
            'candidate_id': self.track['candidate_id'], 'identity_review': 'CONFIRMED_SAME_SONG',
            'version_review': 'CONFIRMED_SAME_VERSION', 'editorial_category': 'KPOP_SOLO',
            'evidence': 'SYNTHETIC FIXTURE ONLY — never installed or published'}])
        for module in (sn, generation, routes):
            p = patch.object(module, 'ROOT', self.root)
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(routes, 'read_current_selection', return_value=self.rows)
        p.start()
        self.addCleanup(p.stop)

    def save_reviewed(self):
        facts = wf.apply_review(self.draft, self.review)
        path = wf.fact_path(self.root, self.week)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(facts), encoding='utf-8')
        return facts

    def test_draft_sources_and_no_inherited_approval(self):
        self.assertEqual(self.draft['analysis_tracks'], [])
        self.assertEqual(self.draft['review_stage'], 'PENDING_HUMAN_REVIEW')
        self.assertFalse(self.draft['article_publication_approved'])
        self.assertEqual(len(self.draft['source_refs']), 4)
        self.assertTrue(all(r['provenance'] for r in self.draft['source_refs'].values()))
        self.assertEqual(self.track['identity_review'], 'PENDING')
        self.fixture.assert_originals()

    def test_missing_values_remain_null(self):
        d = wf.build_draft(self.root, '2026-10-15')
        t = next(t for t in d['candidates'] if t['artist'] == 'TEST Artist 1')
        self.assertIsNone(t['spotify']['previous_week_streams'])
        self.assertIsNone(t['spotify']['streams_change_pct'])

    def test_unreviewed_status_and_preview_blocked(self):
        state = routes.current_news_selection(self.week)
        self.assertFalse(state['can_generate'])
        self.assertEqual(state['fact_status'], 'DRAFT')
        with self.assertRaises(HTTPException) as error:
            routes.preview_selected_article(self.week)
        self.assertEqual(error.exception.status_code, 409)

    def test_reviewed_free_preview_and_chart_status(self):
        self.save_reviewed()
        state = routes.current_news_selection(self.week)
        self.assertTrue(state['can_generate'])
        result = routes.preview_selected_article(self.week)
        self.assertIn(self.week, result['article'])
        self.assertFalse(result['publication_approved'])
        self.assertFalse(result['ai_generated_now'])
        self.assertIn(self.week, result['source'])
        pair = choose_pair(self.root, self.week)[0]
        rows = build_weekly_rows([dict(self.rows[0], song_id=999)], self.root, pair)
        self.assertTrue(rows)

    def test_unreviewed_song_cannot_enter_evidence(self):
        facts = self.save_reviewed()
        other = self.draft['candidates'][1]
        rows = self.rows + [{'artist': other['artist'], 'track': other['track_name']}]
        snapshot = sn.selected_snapshot(rows, facts)
        snapshot['approved_tracks'].append(other)
        evidence = sn.evidence_for_selected(facts, snapshot)
        self.assertEqual(evidence['analysis_track_count'], 1)

    def test_wrong_week_or_draft_fingerprint_rejected(self):
        for key, value in [('week_end', '2026-10-15'), ('draft_sha256', '0' * 64)]:
            review = dict(self.review, **{key: value})
            with self.assertRaises(ValueError):
                wf.apply_review(self.draft, review)

    def test_missing_version_or_evidence_rejected(self):
        for key in ('identity_review', 'version_review', 'editorial_category', 'evidence'):
            review = copy.deepcopy(self.review)
            review['tracks'][0][key] = ''
            with self.assertRaises(ValueError):
                wf.apply_review(self.draft, review)

    def test_duplicate_or_unknown_review_rejected(self):
        review = copy.deepcopy(self.review)
        review['tracks'] *= 2
        with self.assertRaises(ValueError):
            wf.apply_review(self.draft, review)
        review['tracks'][0]['candidate_id'] = 'unknown'
        with self.assertRaises(ValueError):
            wf.apply_review(self.draft, review)

    def test_fact_values_dates_and_publication_tampering_blocked(self):
        facts = self.save_reviewed()
        for key, value in [('week_previous', {'start': 'bad', 'end': 'bad'}),
                           ('article_publication_approved', True), ('analysis_track_count', 5)]:
            with self.assertRaises(ValueError):
                wf.validate_reviewed(dict(facts, **{key: value}), self.root)
        facts['analysis_tracks'][0]['spotify']['streams_change_pct'] += 1
        with self.assertRaises(ValueError):
            wf.validate_reviewed(facts, self.root)

    def test_source_and_manifest_changes_blocked(self):
        facts = self.save_reviewed()
        ref = self.draft['source_refs']['spotify_current']
        path = self.root / ref['path']
        original = path.read_bytes()
        path.write_bytes(original + b'\n')
        with self.assertRaises(ValueError):
            wf.validate_reviewed(facts, self.root)
        path.write_bytes(original)
        manifest = self.root / ref['manifest']
        record = json.loads(manifest.read_text(encoding='utf-8'))
        record['provenance']['spotify']['source_evidence'] = 'changed evidence'
        manifest.write_text(json.dumps(record), encoding='utf-8')
        with self.assertRaises(ValueError):
            wf.validate_reviewed(facts, self.root)

    def test_paid_confirmation_required_and_draft_blocks_api(self):
        request = Request({'type': 'http', 'method': 'POST', 'headers': [
            (b'host', b'localhost'), (b'origin', b'http://localhost'),
            (b'x-requested-with', b'KpopNewsPanel'), (b'content-type', b'application/json')]})
        with generation_session(), patch.object(routes, 'generate_paid_article', side_effect=AssertionError('API forbidden')) as paid:
            for confirm in (False, True):
                with self.assertRaises(HTTPException):
                    routes.generate_selected_article(request, routes.GenerateRequest(confirm_paid=confirm, week_end=self.week))
            paid.assert_not_called()

    def test_saved_legacy_article_not_returned_as_new_week(self):
        with self.assertRaises(HTTPException):
            routes.get_saved_article(week_end=self.week)

    def test_reviewed_file_cannot_be_reused_for_other_week(self):
        facts = self.save_reviewed()
        path = wf.fact_path(self.root, '2026-10-15')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(facts), encoding='utf-8')
        with self.assertRaises(ValueError):
            wf.load_reviewed(self.root, '2026-10-15')

    def test_period_review_required(self):
        self.review['period_review'] = 'PENDING'
        with self.assertRaises(ValueError):
            wf.apply_review(self.draft, self.review)

    def test_cli_dry_run_and_exclusive_draft_save(self):
        import contextlib
        import io
        args = ['weekly_facts', '--root', str(self.root), '--week-end', self.week]
        target = wf.fact_path(self.root, self.week, False)
        with patch('sys.argv', args), contextlib.redirect_stdout(io.StringIO()):
            wf.main()
        self.assertFalse(target.exists())
        with patch('sys.argv', args + ['--apply']), contextlib.redirect_stdout(io.StringIO()):
            wf.main()
            before = target.read_bytes()
            with self.assertRaises(FileExistsError):
                wf.main()
        self.assertEqual(before, target.read_bytes())

    def test_new_week_paid_route_stub_preserves_draft_status(self):
        self.save_reviewed()
        request = Request({'type': 'http', 'method': 'POST', 'headers': [
            (b'host', b'localhost'), (b'origin', b'http://localhost'),
            (b'x-requested-with', b'KpopNewsPanel'), (b'content-type', b'application/json')]})
        with generation_session() as (user, cookie), patch.object(routes, 'ARTICLES', self.root / 'articles'), \
             patch.object(routes, 'generate_paid_article', return_value=('SYNTHETIC TEST DRAFT', 'offline-stub')) as paid:
            result = routes.generate_selected_article(request, routes.GenerateRequest(confirm_paid=True, week_end=self.week))
            with store.connect() as db:
                receipt = article_origin.receipt(db, result['generation_id'], user['id'])
            self.assertEqual(receipt['output'], result['article'])
            self.assertEqual(json.loads(receipt['generation']['input_json']), paid.call_args.args[0])
        self.assertFalse(result['publication_approved'])
        self.assertEqual(paid.call_args.args[0]['week_current']['end'], self.week)
        record = json.loads(next((self.root / 'articles').glob('*.json')).read_text(encoding='utf-8'))
        self.assertEqual(record['article_status'], 'DRAFT_NOT_FOR_PUBLICATION')
        provenance = record['generation_provenance']
        self.assertEqual(json.loads(provenance['input_json']), paid.call_args.args[0])
        self.assertEqual(provenance['prompt_version'], 'selected-v1')
        self.assertIn('입력에 없는 숫자는 추가하지 마라', provenance['instructions'])


if __name__ == '__main__':
    unittest.main()
