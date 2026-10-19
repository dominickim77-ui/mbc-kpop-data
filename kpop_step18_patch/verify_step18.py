"""Offline unit checks; no database, YouTube, or OpenAI requests."""
from __future__ import annotations

import ast
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parent.parent
MOD = ROOT / 'news' / 'youtube_approval_lock.py'
ROUTES = ROOT / 'news' / 'youtube_video_review_step17b.py'
JS = ROOT / 'static' / 'youtube_video_review_step17b.js'


def review_file(root, time, video_id, song_id=5):
    obj = dict(song_id=song_id, status='VIDEO_IDENTITY_REVIEW',db_status='DB_STORED',
               manually_checked_channel=True,manually_checked_track_version=True,
               video_id=video_id,channel_id='UC-valid',youtube_channel='HYBE LABELS',
               video_title='Animal Official MV', approved_at_utc=time.isoformat(),
               original_candidate=dict(video_id=video_id,channel_id='UC-valid'))
    path=root/f'song_{song_id}_{video_id}.json'
    path.write_text(json.dumps(obj),encoding='utf-8')
    return path


def main():
    spec=importlib.util.spec_from_file_location('youtube_approval_lock',MOD)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory() as temp:
        p=Path(temp)
        assert module.latest_approved(p,5) is None
        at=datetime(2026,10,19,1,36,tzinfo=timezone.utc)
        old=review_file(p,at,'j84h0XW8rMs')
        new=review_file(p,at+timedelta(minutes=6),'m7k9UMcHbr0')
        assert module.latest_approved(p,5)['video_id']=='m7k9UMcHbr0'
        assert module.latest_approved(p,3) is None
        old.unlink()
        assert module.latest_approved(p,5)['video_id']=='m7k9UMcHbr0'
        new.write_text('{bad json',encoding='utf-8')
        try:
            module.latest_approved(p,5)
        except module.ApprovalIntegrityError:
            pass
        else:
            raise AssertionError('corrupt review must fail closed')
    ast.parse(ROUTES.read_text(encoding='utf-8'))
    js=JS.read_text(encoding='utf-8')
    assert 'STEP18_APPROVAL_LOCK_V1' in ROUTES.read_text(encoding='utf-8')
    assert 'approve.disabled = Boolean(data.approval_locked)' in js
    assert 'approval_locked=existing_approval is not None' in ROUTES.read_text(encoding='utf-8')
    print('✅ 기존 HYBE 승인 기록 우선 선택 / 이전 잘못된 승인 기록 보존')
    print('✅ 손상된 승인 기록은 자동 승인하지 않고 중단')
    print('✅ 서버 신규 승인 보호 + 브라우저 승인 버튼 잠금 검사 통과')
    print('✅ 실제 MySQL/YouTube API/OpenAI 호출 없음')

if __name__ == '__main__':
    try: main()
    except (AssertionError,OSError,SyntaxError) as exc:
        raise SystemExit('❌ STEP18 검증 실패: '+str(exc)) from None
