"""STEP17B tests: no YouTube API request, no DB, no OpenAI. Run after installing."""
import ast
import json
import re
import subprocess
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from news import youtube_video_review_step17b as review


class FakeResponse:
    def __init__(self, result):
        self.status_code = 200
        self.ok = True
        self._result = result

    def json(self):
        return self._result


class FakeCursor:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params):
        self.calls.append((sql, params))

    def close(self):
        pass


class FakeDB:
    def __init__(self):
        self.cursor_obj = FakeCursor()
        self.committed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed = True

    def rollback(self):
        pass

    def close(self):
        pass


class Request:
    def __init__(self, approval=False):
        self.headers = {'host':'127.0.0.1:8000', 'x-requested-with':'KpopYouTubeReview'}
        if approval:
            self.headers['origin'] = 'http://127.0.0.1:8000'


class Step17BTests(unittest.TestCase):
    def setUp(self):
        review._sessions.clear()

    def test_existing_code_changed_safely(self):
        app = (ROOT / 'app.py').read_text(encoding='utf-8')
        html = (ROOT / 'templates/index.html').read_text(encoding='utf-8')
        self.assertIn('KPOP_YOUTUBE_VIDEO_HUMAN_REVIEW_STEP17B', app)
        self.assertNotIn('"maxResults": 1', app)
        self.assertIn('LEFT JOIN youtube_stats AS y', app)
        self.assertIn('"youtube_review_status"', app)
        self.assertIn('id="youtube-review-step17b"', html)
        ast.parse(app)

    def test_review_hints_never_auto_approve(self):
        self.assertIn('리믹스', review._candidate_hint('Animal (Remix)'))
        self.assertEqual(review._video_id_from_url('https://www.youtube.com/watch?v=m7k9UMcHbr0'), 'm7k9UMcHbr0')
        self.assertIsNone(review._video_id_from_url('https://example.com/watch?v=m7k9UMcHbr0'))
        self.assertIsNone(review._video_id_from_url('https://www.youtube.com/watch?v=broken'))

    def test_candidates_no_mysql_write_and_explicit_approval(self):
        target = {'song_id': 7, 'artist':'KATSEYE', 'track':'Animal'}
        search_payload = {'items':[{'id':{'videoId':'m7k9UMcHbr0'}},{'id':{'videoId':'AAAAAAAAAAA'}}]}
        videos_payload = {'items':[
          {'id':'m7k9UMcHbr0', 'snippet':{'title':'KATSEYE Animal Official MV','channelTitle':'HYBE LABELS','channelId':'UCdef','publishedAt':'2026-08-01'},
            'statistics':{'viewCount':'137000000','likeCount':'10000','commentCount':'100'}},
          {'id':'AAAAAAAAAAA', 'snippet':{'title':'Animal Remix cover','channelTitle':'Unknown','channelId':'UCabc','publishedAt':'2026-08-01'},
            'statistics':{'viewCount':'100','likeCount':'2','commentCount':'1'}}]}
        class FakePair:
            from datetime import date
            current_end = date(2026,10,8)
        fake_manager = __import__('news.chart_data_manager',fromlist=['choose_pair'])
        calls=[]
        def fake_get(url, params, timeout):
            calls.append(url)
            if url.endswith('/search'):
                return FakeResponse(search_payload)
            ids = set(params.get('id','').split(','))
            return FakeResponse({'items':[v for v in videos_payload['items'] if v['id'] in ids]})
        with patch.object(review,'_get_selected_track',return_value=target), \
             patch.object(review,'_chart_reference',return_value=None), \
             patch.object(fake_manager,'choose_pair',return_value=(FakePair(),[],[])), \
             patch.object(review.requests,'get',side_effect=fake_get), \
             patch.dict(review.os.environ,{'YOUTUBE_API_KEY':'fake-secret'}):
            response = review.get_candidates(Request(),song_id=7,week_end='2026-10-08')
            self.assertEqual(len(response['candidates']),2)
            self.assertTrue(all(c['status']=='PENDING_HUMAN_REVIEW' for c in response['candidates']))
            self.assertEqual(len(calls),2)  # search + videos
            cached = review.get_candidates(Request(),song_id=7,week_end='2026-10-08')
            self.assertTrue(cached['cached'])
            self.assertEqual(len(calls),2)  # no quota cost on cached call
            token = response['review_token']
            with self.assertRaises(Exception):
                review.approve_video(Request(True),review.ApproveRequest(
                    song_id=7, video_id='m7k9UMcHbr0',review_token=token,
                    verified_channel=False,verified_track_version=True,understood_lifetime_metric=True))
            fake_db = FakeDB()
            fake_app = types.ModuleType('app')
            fake_app.get_db_connection = lambda: fake_db
            with tempfile.TemporaryDirectory(dir=ROOT) as folder, \
                 patch.object(review,'REVIEW_DIR',Path(folder)), \
                 patch.dict(sys.modules,{'app':fake_app}), \
                 patch.object(review,'_get_selected_track',return_value=target), \
                 patch.object(review.requests,'get',side_effect=fake_get), \
                 patch.dict(review.os.environ,{'YOUTUBE_API_KEY':'fake-secret'}):
                result=review.approve_video(Request(True),review.ApproveRequest(
                    song_id=7, video_id='m7k9UMcHbr0',review_token=token,
                    verified_channel=True, verified_track_version=True,understood_lifetime_metric=True))
                self.assertEqual(result['status'],'MANUALLY_APPROVED')
                self.assertTrue(fake_db.committed)
                self.assertEqual(len(fake_db.cursor_obj.calls),1)
                self.assertEqual(review.video_review_status(7,'m7k9UMcHbr0'),'MANUALLY_APPROVED')
                self.assertEqual(review.video_review_status(7,'AAAAAAAAAAA'),'LEGACY_UNVERIFIED')
                files=list(Path(folder).glob('*.json'))
                self.assertEqual(len(files),1)
                self.assertFalse(json.loads(files[0].read_text(encoding='utf-8'))['publication_approved'])

    def test_invalid_origin_rejected(self):
        req=Request(True)
        req.headers['origin']='https://evil.example'
        with self.assertRaises(Exception):
            review._require_local_request(req,approval=True)


if __name__ == '__main__':
    print('STEP17B offline tests only — no real API, MySQL or OpenAI requests.')
    unittest.main(verbosity=2)
