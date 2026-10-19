"""Safe, fail-closed installer for STEP18 append-only correction authority."""
from __future__ import annotations

import argparse
import ast
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path.cwd()
PACKAGE = Path(__file__).resolve().parent
FILES = [
    Path('news/youtube_approval_lock.py'),
    Path('news/youtube_display_resolver.py'),
    Path('news/youtube_video_review_step17b.py'),
]
NEW_FILE = Path('news/youtube_active_corrections.py')


def replace_once(contents: str, old: str, new: str, label: str) -> str:
    if contents.count(old) != 1:
        raise ValueError(f'{label}: 예상 코드 위치가 다릅니다 ({contents.count(old)}개). 설치 중단')
    return contents.replace(old, new, 1)


def proposed_updates() -> dict[Path, str]:
    originals = {p: (ROOT / p).read_text(encoding='utf-8-sig') for p in FILES}
    lock = originals[FILES[0]]
    lock = replace_once(lock,
        '''    if not candidates:\n        return None\n    _, _, video_id, channel, title = max(candidates)\n    return dict(video_id=video_id, channel=channel, title=title)''',
        '''    if not candidates:\n        original_latest = None\n    else:\n        _, _, video_id, channel, title = max(candidates)\n        original_latest = dict(video_id=video_id, channel=channel, title=title)\n    # STEP18_CORRECTION: append-only human correction is the shared authority.\n    from news.youtube_active_corrections import resolve_active_approval\n    return resolve_active_approval(root, song_id, original_latest)''',
        'youtube_approval_lock.py')
    resolver = originals[FILES[1]]
    original_prefix = 'def apply_approved_youtube_videos(rows, cursor, root):'
    if resolver.count(original_prefix) != 1 or not resolver.rstrip().endswith('return rows'):
        raise ValueError('youtube_display_resolver.py: 함수 구조가 달라 자동 교체를 중단했어')
    prefix = resolver[:resolver.index(original_prefix)]
    resolver = prefix + '''def apply_approved_youtube_videos(rows, cursor, root):\n    """Show only the single currently ACTIVE reviewed Video ID (no writes)."""\n    from news.youtube_approval_lock import latest_approved\n\n    review_dir = Path(root) / "facts" / "youtube_video_reviews"\n    for row in rows:\n        row["youtube_video_review_status"] = "UNREVIEWED"\n        active = latest_approved(review_dir, int(row["song_id"]))\n        if active is None:\n            continue\n        cursor.execute(\n            """SELECT youtube_video_id, youtube_title, youtube_channel,\n                      youtube_views, youtube_likes, youtube_comments, collected_at\n               FROM youtube_stats\n               WHERE song_id = %s AND youtube_video_id = %s\n               ORDER BY youtube_id DESC LIMIT 1""",\n            (int(row["song_id"]), active["video_id"]),\n        )\n        matched = cursor.fetchone()\n        if matched is None or matched["youtube_video_id"] != active["video_id"]:\n            # Keep historical row for diagnosis, but never label it approved.\n            row["youtube_video_review_status"] = "REVIEW_DATA_MISMATCH"\n            continue\n        row.update(matched)\n        row["youtube_video_review_status"] = "APPROVED"\n    return rows\n'''
    review = originals[FILES[2]]
    start = review.find('def video_review_status(song_id: int, current_video_id: str | None) -> str:')
    boundary = '\n@router.get(\'/candidates\')'
    end = review.find(boundary, start)
    if start < 0 or end < 0 or review.count('def video_review_status(') != 1:
        raise ValueError('video_review_status: 변경 위치를 정확히 찾지 못해 설치 중단')
    safe_status = '''def video_review_status(song_id: int, current_video_id: str | None) -> str:\n    """Only the ACTIVE reviewed video may be displayed as MANUALLY_APPROVED."""\n    if not current_video_id or not VIDEO_ID.fullmatch(str(current_video_id)):\n        return 'PENDING_NO_VIDEO'\n    from news.youtube_approval_lock import latest_approved, ApprovalIntegrityError\n    try:\n        active = latest_approved(REVIEW_DIR, int(song_id))\n    except ApprovalIntegrityError:\n        return 'REVIEW_RECORD_ERROR'\n    if active is None:\n        return 'LEGACY_UNVERIFIED'\n    if active['video_id'] == str(current_video_id):\n        return 'MANUALLY_APPROVED'\n    return 'SUPERSEDED_REVIEW'\n\n'''
    review = review[:start] + safe_status + review[end:]
    proposal = {FILES[0]: lock, FILES[1]: resolver, FILES[2]: review,
                NEW_FILE: (PACKAGE / 'youtube_active_corrections.py').read_text(encoding='utf-8')}
    for name, source in proposal.items():
        ast.parse(source, filename=str(name))
    return proposal


def main():
    parser = argparse.ArgumentParser(description='STEP18 append-only approval correction installer')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    if not (ROOT/'app.py').exists() or not (ROOT/'news').is_dir():
        raise SystemExit('❌ 프로젝트 최상위 C:\\WORKSPACE\\mbc-kpop-data에서 실행해 줘')
    if (ROOT / NEW_FILE).exists():
        raise SystemExit('❌ 새 승인 정정 모듈이 이미 있어. 재설치·덮어쓰기 전에 확인 필요')
    try:
        proposals = proposed_updates()
    except (OSError, ValueError, SyntaxError) as exc:
        raise SystemExit(f'❌ 설치 전 검사 실패: {exc}') from None
    if args.dry_run:
        print('✅ 설치 전 검사 통과 · 수정 예정:', ', '.join(map(str, proposals)))
        print('✅ 기존 MySQL/승인 JSON/기사 파일은 수정하지 않음')
        return
    backup = Path.home()/'Downloads'/('kpop_step18_correction_code_backup_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    for name in FILES:
        dest = backup / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, dest)
    print('✅ 원본 코드 백업:', backup)
    done = []
    try:
        for name, source in proposals.items():
            dest = ROOT / name
            temp = dest.with_name(dest.name + '.step18.tmp')
            if temp.exists():
                raise ValueError(f'임시 파일이 이미 있어: {temp}')
            with temp.open('x', encoding='utf-8', newline='\n') as stream:
                stream.write(source)
            temp.replace(dest)
            done.append(name)
    except Exception:
        for name in reversed(done):
            if name in FILES:
                shutil.copy2(backup / name, ROOT / name)
            else:
                (ROOT / name).unlink(missing_ok=True)
        raise
    print('✅ 설치 완료 · 승인 정책/화면 표시/검수 상태 기준 통일')
    print('✅ 이 단계에서는 정정 JSON 생성도 MySQL 변경도 없음')


if __name__ == '__main__':
    main()
