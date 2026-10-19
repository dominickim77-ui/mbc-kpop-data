"""Install STEP17A into the checked GitHub STEP16 working-tree state.

Requires an unchanged baseline. No network/MySQL/OpenAI calls. Backups created
outside the repository before any file is changed. Idempotent: second run stops.
"""
import argparse
import datetime
import hashlib
import json
import shutil
import sys
from pathlib import Path

PATCH = Path(__file__).resolve().parent
ROOT = PATCH.parent
FILES = ['news/news_routes.py', 'static/news_panel.js', 'templates/index.html']
NEW = ['news/spotify_only_preview.py']


def blob_sha(path):
    data = path.read_bytes()
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    manifest = json.loads((PATCH / 'manifest.json').read_text(encoding='utf-8'))
    mismatches = []
    for rel in FILES:
        dest = ROOT / rel
        if not dest.is_file() or blob_sha(dest) != manifest['expected_blob_sha'][rel]:
            mismatches.append(rel)
    for rel in NEW:
        if (ROOT / rel).exists():
            mismatches.append(rel + ' (이미 존재)')
    if mismatches:
        print('⛔ 설치 중단 — 기존 파일이 기대한 STEP16 코드와 달라:', ', '.join(mismatches))
        print('기존 파일을 덮어쓰지 않았어. 변경 상태를 확인하고 새 패치를 요청해 줘.')
        return 1
    if args.dry_run:
        print('✅ 설치 전 검사 완료. 변경 예정: ' + ', '.join(FILES + NEW))
        print('ℹ .env / 데이터 CSV / 기사 / 기존 승인 Fact Sheet는 변경하지 않아.')
        return 0
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    backup = ROOT.parent / (ROOT.name + '_step17a_backup_' + stamp)
    for rel in FILES:
        target = backup / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, target)
    print('✅ 원본 백업:', backup)
    try:
        for rel in FILES + NEW:
            dest = ROOT / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(PATCH / 'payload' / rel, dest)
    except Exception:
        for rel in FILES:
            shutil.copy2(backup / rel, ROOT / rel)
        print('⛔ 복사 실패. 기존 수정 파일을 백업에서 복원했어. 신규 파일은 따로 확인해 줘.')
        raise
    print('✅ STEP17A 설치 완료 — Spotify 단독 검수 초안 버튼 및 무료 API')
    print('다음: python kpop_step17_patch\\verify_step17.py')
    return 0

if __name__ == '__main__':
    sys.exit(main())
