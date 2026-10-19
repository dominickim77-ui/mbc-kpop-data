"""Current runtime approval lock; all history records are temporary fixtures."""
import json
import tempfile
import unittest
from pathlib import Path
from news.youtube_approval_lock import latest_approved, ApprovalIntegrityError


class CurrentLockTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.review = Path(temp.name) / 'facts/youtube_video_reviews'
        self.review.mkdir(parents=True)

    def record(self, suffix, video, time, db_status='DB_STORED'):
        value = dict(song_id=5, status='VIDEO_IDENTITY_REVIEW', db_status=db_status,
                     manually_checked_channel=True, manually_checked_track_version=True,
                     video_id=video, channel_id='UC-fixture', youtube_channel='Fixture Channel',
                     video_title='Fixture MV', approved_at_utc=time,
                     original_candidate=dict(video_id=video, channel_id='UC-fixture'))
        path = self.review / f'song_5_{suffix}.json'
        path.write_text(json.dumps(value), encoding='utf-8')
        return path

    def test_no_history_has_no_approval(self):
        self.assertIsNone(latest_approved(self.review, 5))

    def test_latest_completed_manual_approval(self):
        self.record('old', 'AAAAAAAAAAA', '2026-10-19T01:00:00+00:00')
        self.record('new', 'BBBBBBBBBBB', '2026-10-19T02:00:00+00:00')
        self.assertEqual(latest_approved(self.review, 5)['video_id'], 'BBBBBBBBBBB')
        self.assertIsNone(latest_approved(self.review, 3))

    def test_corrupt_history_fails_closed(self):
        path = self.record('bad', 'AAAAAAAAAAA', '2026-10-19T01:00:00+00:00')
        path.write_text('{broken', encoding='utf-8')
        with self.assertRaises(ApprovalIntegrityError):
            latest_approved(self.review, 5)

    def test_incomplete_db_evidence_fails_closed(self):
        self.record('pending', 'AAAAAAAAAAA', '2026-10-19T01:00:00+00:00', 'PENDING_DB_WRITE')
        with self.assertRaises(ApprovalIntegrityError):
            latest_approved(self.review, 5)
