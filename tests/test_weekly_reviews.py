"""Current review-candidate and free-preview contracts, not historical payload hashes."""
import unittest
from unittest.mock import patch
import asyncio

from news.chart_data_manager import choose_pair
from news.review_candidates_step16 import build_review_queue
from news.spotify_only_preview import make_spotify_only_preview, SpotifyOnlyPreviewError
from tests.support.asgi import asgi_request

SELECTED = [{'artist': a, 'track': t} for a, t in [
    ('BTS', 'SWIM'), ('BTS', 'NORMAL'), ('ROSÉ, Bruno Mars', 'APT.'),
    ('LISA', 'SaWaDiKa'), ('KATSEYE', 'Hootie Frutti'), ('KATSEYE', 'Animal')]]


class WeeklyReviewTests(unittest.TestCase):
    def test_reviewed_candidate_and_held_categories(self):
        pair = choose_pair(week_end='2026-10-08')[0]
        report = build_review_queue(SELECTED, pair)
        states = {r['track']: r['review_status'] for r in report['candidates']}
        self.assertEqual(states['SWIM'], 'SPOTIFY_ONLY_REVIEW_PENDING')
        self.assertEqual(states['Animal'], 'DUAL_CHART_REVIEWED')
        self.assertEqual(states['SaWaDiKa'], 'DUAL_CHART_REVIEWED')
        self.assertEqual(states['Hootie Frutti'], 'HOLD_VERSION')
        self.assertFalse(report['auto_approval'])
        self.assertFalse(report['publication_approved'])

    def test_free_spotify_preview_preserves_counts_and_exclusions(self):
        pair = choose_pair(week_end='2026-10-08')[0]
        report = make_spotify_only_preview(SELECTED, pair)
        rows = {r['track']: r for r in report['evidence']['candidates']}
        self.assertEqual(set(rows), {'SWIM', 'NORMAL', 'APT.'})
        self.assertEqual((rows['SWIM']['previous_rank'], rows['SWIM']['current_rank']), (24, 20))
        self.assertFalse(report['ai_generated_now'])
        self.assertFalse(report['publication_approved'])
        self.assertFalse(report['evidence']['allowed_paid_ai_generation'])

    def test_reviewed_only_selection_cannot_become_unreviewed_preview(self):
        pair = choose_pair(week_end='2026-10-08')[0]
        with self.assertRaises(SpotifyOnlyPreviewError):
            make_spotify_only_preview([{'artist': 'LISA', 'track': 'SaWaDiKa'}], pair)

    def test_current_candidate_http_contract(self):
        from news import news_routes
        with patch.object(news_routes, 'read_current_selection', return_value=SELECTED):
            status, report = asyncio.run(asgi_request('/api/news/review-candidates?week_end=2026-10-08'))
        self.assertEqual(status, 200)
        self.assertEqual(report['selected_count'], 6)
        self.assertFalse(report['publication_approved'])
