"""Offline regression tests for the append-only correction workflow."""
from __future__ import annotations
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent
TEST_VIDEO = 'm7k9UMcHbr0'
VIBE = 'SyLtYUk9Ogg'
JAE = 'j84h0XW8rMs'


class TestCorrection(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.review = self.root / 'facts' / 'youtube_video_reviews'
        self.review.mkdir(parents=True)
        (self.root / 'news').mkdir()
        (self.root / 'news' / '__init__.py').touch()
        src = Path(__file__).resolve().parent.parent / 'news' / 'youtube_approval_lock.py'
        if src.is_file() and 'resolve_active_approval' in src.read_text(encoding='utf8'):
            shutil.copy2(src, self.root / 'news' / 'youtube_approval_lock.py')
        else:
            # Tests also run before package installation in a clean temp repo.
            stem = (Path(__file__).resolve().parent.parent / 'news' / 'youtube_approval_lock.py')
            if not stem.is_file():
                raise AssertionError('STEP18 설치를 먼저 완료해 주세요. 승인 잠금 파일이 없습니다.')
            lock = stem.read_text(encoding='utf8')
            old = '    if not candidates:\n        return None\n    _, _, video_id, channel, title = max(candidates)\n    return dict(video_id=video_id, channel=channel, title=title)'
            new = '''    if not candidates:\n        original_latest = None\n    else:\n        _, _, video_id, channel, title = max(candidates)\n        original_latest = dict(video_id=video_id, channel=channel, title=title)\n    from news.youtube_active_corrections import resolve_active_approval\n    return resolve_active_approval(root, song_id, original_latest)'''
            if old not in lock:
                raise ValueError('Reference fixture invalid')
            (self.root / 'news' / 'youtube_approval_lock.py').write_text(lock.replace(old,new),encoding='utf8')
        shutil.copy2(PACKAGE / 'youtube_active_corrections.py', self.root / 'news' / 'youtube_active_corrections.py')
        approvals = [(JAE,'Jaeguchi','2026-10-19T01:36:25+00:00'),
                     (TEST_VIDEO,'HYBE LABELS','2026-10-19T01:42:49+00:00'),
                     (VIBE,'Vibe Music','2026-10-19T02:27:10+00:00')]
        self.files = {}
        for i,(vid,channel,ts) in enumerate(approvals):
            data = {'status':'VIDEO_IDENTITY_REVIEW','db_status':'DB_STORED','song_id':5,
                    'video_id':vid,'video_title': f'Animal {channel}',
                    'youtube_channel':channel,'channel_id':f'UC_channel_{i}',
                    'approved_at_utc':ts, 'manually_checked_channel':True,
                    'manually_checked_track_version':True,
                    'original_candidate':{'video_id':vid,'channel_id':f'UC_channel_{i}'}}
            path=self.review/f'song_5_20261019_{i}.json'
            path.write_text(json.dumps(data),encoding='utf8')
            self.files[vid]=(path,data,hashlib.sha256(path.read_bytes()).hexdigest())

    def tearDown(self): self.temp.cleanup()

    def run_script(self, script: str):
        proc = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, cwd=self.root,
                              encoding='utf-8', timeout=10)
        if proc.returncode: raise AssertionError(proc.stdout+'\n'+proc.stderr)
        return proc.stdout.strip()

    def make_correction(self):
        path,target,digest = self.files[TEST_VIDEO]
        rec = {'status':'ACTIVE_VIDEO_CORRECTION','song_id':5,
               'recorded_at_utc': '2026-10-19T03:10:00+00:00','human_confirmed':True,
               'previous_active_video_id':VIBE, 'active_video_id':TEST_VIDEO,
               'active_channel':target['youtube_channel'],
               'active_channel_id':target['channel_id'], 'active_title':target['video_title'],
               'source_approval_file':path.name,'source_approval_sha256':digest,
               'invalidated_video_ids':[VIBE,JAE], 'reason':'Incorrect lyrics candidates replaced with reviewed MV',
               'db_modified':False,'publication_approved':False}
        dst=self.root/'facts'/'youtube_video_corrections';dst.mkdir()
        (dst/'song_5_20261019T031000000000Z_xxxxxxxx.json').write_text(json.dumps(rec),encoding='utf8')
        return dst

    def test_without_correction_current_is_vibe(self):
        result=self.run_script('from news.youtube_approval_lock import latest_approved; '
            'from pathlib import Path; print(latest_approved(Path("facts/youtube_video_reviews"),5)["video_id"])')
        self.assertEqual(result,VIBE)

    def test_after_correction_active_is_official(self):
        self.make_correction()
        result=self.run_script('from news.youtube_approval_lock import latest_approved; '
            'from pathlib import Path; print(latest_approved(Path("facts/youtube_video_reviews"),5)["video_id"])')
        self.assertEqual(result,TEST_VIDEO)

    def test_changed_original_approval_fails_closed(self):
        self.make_correction()
        path=self.files[TEST_VIDEO][0]
        path.write_text(path.read_text(encoding='utf8').replace('HYBE LABELS','FAKE CHANNEL'),encoding='utf8')
        script='from news.youtube_approval_lock import latest_approved,ApprovalIntegrityError; from pathlib import Path; '\
            'exec("try:\\n latest_approved(Path(\\\"facts/youtube_video_reviews\\\"),5)\\nexcept ApprovalIntegrityError:\\n print(\\\"BLOCKED\\\")")'
        self.assertEqual(self.run_script(script),'BLOCKED')

    def test_chain_prevents_conflicting_rewrite(self):
        directory=self.make_correction()
        target=next(directory.glob('song_5_*.json'))
        data=json.loads(target.read_text(encoding='utf8'));data['previous_active_video_id']=JAE
        target.write_text(json.dumps(data),encoding='utf8')
        script='from news.youtube_approval_lock import latest_approved,ApprovalIntegrityError; from pathlib import Path; '\
            'exec("try:\\n latest_approved(Path(\\\"facts/youtube_video_reviews\\\"),5)\\nexcept ApprovalIntegrityError:\\n print(\\\"BLOCKED\\\")")'
        self.assertEqual(self.run_script(script),'BLOCKED')


if __name__=='__main__': unittest.main(verbosity=2)
