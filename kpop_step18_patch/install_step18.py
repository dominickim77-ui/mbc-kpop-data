"""Install STEP18 protection over clean STEP17B repo files.

Usage: python kpop_step18_patch/install_step18.py --dry-run
       python kpop_step18_patch/install_step18.py
"""
from __future__ import annotations

import argparse
import ast
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ROUTES = ROOT / 'news' / 'youtube_video_review_step17b.py'
JS = ROOT / 'static' / 'youtube_video_review_step17b.js'
LOCK = ROOT / 'news' / 'youtube_approval_lock.py'
MARKER = '# STEP18_APPROVAL_LOCK_V1'


def replace_once(text, needle, replacement, label):
    n = text.count(needle)
    if n != 1:
        raise RuntimeError(f'{label}: 기대했던 위치가 {n}개야. 코드를 확인한 뒤 다시 진행해 줘.')
    return text.replace(needle, replacement, 1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    if not ROUTES.is_file() or not JS.is_file() or LOCK.exists():
        raise RuntimeError('기존 파일 또는 신규 모듈 위치가 예상과 달라. 중단했어.')
    source = ROUTES.read_text(encoding='utf-8-sig')
    script = JS.read_text(encoding='utf-8-sig')
    if MARKER in source or 'approval_locked' in script:
        raise RuntimeError('STEP18이 이미 적용됐거나 충돌하는 변경이 있어. 중단했어.')
    try:
        b = subprocess.run(['git', 'branch', '--show-current'], cwd=ROOT, capture_output=True, text=True, check=True)
        if b.stdout.strip() != 'feature/kpop-news-analysis':
            raise RuntimeError('현재 브랜치가 feature/kpop-news-analysis가 아니야. 중단했어.')
        changes = subprocess.run(['git','status','--porcelain','--',str(ROUTES.relative_to(ROOT)),str(JS.relative_to(ROOT))],cwd=ROOT,capture_output=True,text=True,check=True)
        if changes.stdout.strip():
            raise RuntimeError('수정 대상 파일에 아직 커밋되지 않은 변경이 있어. 먼저 확인해 줘.')
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError('Git 상태 확인 실패. 작업은 중단했어.') from exc

    guard = '''    # STEP18_APPROVAL_LOCK_V1: never silently replace a manually approved Video ID.\n    from news.youtube_approval_lock import latest_approved, ApprovalIntegrityError\n    try:\n        approved = latest_approved(REVIEW_DIR, body.song_id)\n    except ApprovalIntegrityError as exc:\n        raise HTTPException(409, str(exc)) from None\n    if approved is not None:\n        if approved['video_id'] == body.video_id:\n            raise HTTPException(409, '이 Video ID는 이미 승인됐어. 중복 저장하지 않아.')\n        raise HTTPException(409,\n            f"이미 승인된 영상({approved['video_id']}; {approved['channel']})이 있어. "\n            '다른 영상으로 바꾸려면 기존 승인을 정정하는 별도 검수 절차가 필요해.')\n'''
    route_anchor = "    with _cache_lock:\n        _prune_cache(time.monotonic())\n        session = _sessions.get(body.review_token)"
    source = replace_once(source, route_anchor, guard + route_anchor, '승인 API')
    fetch_anchor = "    track = _get_selected_track(song_id)\n    from news.chart_data_manager import choose_pair, CatalogError"
    source = replace_once(source, fetch_anchor, """    track = _get_selected_track(song_id)\n    # STEP18_APPROVAL_LOCK_V1: show lock without querying YouTube again.\n    from news.youtube_approval_lock import latest_approved, ApprovalIntegrityError\n    try:\n        existing_approval = latest_approved(REVIEW_DIR, song_id)\n    except ApprovalIntegrityError as exc:\n        raise HTTPException(409, str(exc)) from None\n    from news.chart_data_manager import choose_pair, CatalogError""", '후보 검색')
    return_anchor = "approval_required=True, statistics_kind='INDIVIDUAL_VIDEO_LIFETIME')"
    if source.count(return_anchor) != 2:
        raise RuntimeError('후보 API 응답 구조가 바뀌었어. 중단했어.')
    source = source.replace(return_anchor,"approval_required=True, statistics_kind='INDIVIDUAL_VIDEO_LIFETIME',\n                            approval_locked=existing_approval is not None,\n                            approved_video_id=existing_approval['video_id'] if existing_approval else None)")
    script = replace_once(script,
        "    box.append(textElement('p', `${data.artist} — ${data.track} | 영상 후보 ${data.candidates.length}개 | 자동 승인 없음`));",
        "    box.append(textElement('p', `${data.artist} — ${data.track} | 영상 후보 ${data.candidates.length}개 | 자동 승인 없음`));\n"
        "    if (data.approval_locked) box.append(textElement('p', `🔒 이미 승인된 Video ID: ${data.approved_video_id}. 다른 후보의 신규 승인은 잠겨 있어. 정정 절차가 필요해.`, 'yt17-warning'));",
        'UI 잠금 안내')
    script = replace_once(script,
        "    approve.className = 'yt17-approve';",
        "    approve.className = 'yt17-approve';\n    approve.disabled = Boolean(data.approval_locked);",
        'UI 승인 버튼')
    ast.parse(source, filename=str(ROUTES))
    ast.parse((HERE / LOCK.name).read_text(encoding='utf-8'), filename=str(LOCK))
    if args.dry_run:
        print('✅ STEP18 DRY RUN · 기존 승인 API/후보 화면 위치 확인')
        print('✅ 기존 검수 JSON·MySQL·Fact Sheet 변경 없음')
        print('✅ 변경 대상: news/youtube_video_review_step17b.py, static/youtube_video_review_step17b.js')
        print('✅ 신규 파일: news/youtube_approval_lock.py')
        return
    backup = ROOT.parent / ('mbc-kpop-step18-backup-' + datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    backup.mkdir(parents=True, exist_ok=False)
    shutil.copy2(ROUTES, backup / ROUTES.name)
    shutil.copy2(JS, backup / JS.name)
    try:
        ROUTES.write_text(source, encoding='utf-8', newline='\n')
        JS.write_text(script, encoding='utf-8', newline='\n')
        shutil.copy2(HERE / LOCK.name, LOCK)
    except Exception:
        shutil.copy2(backup / ROUTES.name, ROUTES)
        shutil.copy2(backup / JS.name, JS)
        LOCK.unlink(missing_ok=True)
        raise
    print('✅ STEP18 설치 완료 · 기존 승인 영상 잠금')
    print('✅ 기존 승인 기록·DB는 수정하지 않았어')
    print('📂 백업:', backup)
    print('다음: python kpop_step18_patch/verify_step18.py')

if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, SyntaxError) as exc:
        raise SystemExit('❌ 설치 중단: ' + str(exc)) from None
