"""Install STEP16 review queue, failing closed on any unexpected existing code changes.

Backs up four existing files outside the repository before changes. Does not modify
.env, MySQL, chart CSV, approved facts, historical articles, or Git metadata.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATCH = Path(__file__).resolve().parent
PAYLOAD = PATCH / 'payload'
MODIFY = {
    'news/news_routes.py': '42bb670b73996fb36b3d34f5cd4ab30cd3fb0f53',
    'static/news_panel.js': '8975af975dcf5a68c38e5894b10956fbe1c2ab0a',
    'static/style.css': '715e30a1b0d4d152c875e79b7fc34c383974c1eb',
    'templates/index.html': '6b89c003e2401bfd89df92d37ff76a1b552cef06',
}
CREATE = ['news/review_candidates_step16.py']


def git_blob(data: bytes) -> str:
    # Git on Windows can checkout text with CRLF; hash normalized blob contents.
    data = data.replace(b'\r\n', b'\n')
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\x00' + data).hexdigest()


def preflight() -> None:
    for relpath, expected in MODIFY.items():
        target = ROOT / relpath
        if not target.is_file():
            raise RuntimeError(f'원본 파일을 찾을 수 없어: {relpath}')
        found = git_blob(target.read_bytes())
        if found != expected:
            raise RuntimeError(f'{relpath}가 GitHub STEP15 기준과 달라. 파일을 덮어쓰지 않고 중단해.\n현재 {found}\n기준 {expected}')
    for relpath in CREATE:
        if (ROOT / relpath).exists():
            raise RuntimeError(f'이미 {relpath}가 있어. 재설치/덮어쓰기 금지.')
    for relpath in list(MODIFY) + CREATE:
        if not (PAYLOAD / relpath).is_file():
            raise RuntimeError(f'ZIP의 설치 파일 누락: {relpath}')


def atomic_copy(source: Path, target: Path) -> None:
    # replace in same dir where possible; never touch unrelated files.
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.step16-', delete=False) as f:
            tmp = Path(f.name)
            f.write(source.read_bytes())
        os.replace(tmp, target)
    finally:
        if tmp is not None and tmp.exists():
            tmp.unlink()


def run(dry_run: bool) -> None:
    preflight()
    if dry_run:
        for p in MODIFY: print('✅ 수정 가능:', p)
        for p in CREATE: print('✅ 추가 가능:', p)
        print('✅ 설치 전 검사 통과. 변경사항 없음 (dry-run).')
        return
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    backup = ROOT.parent / f'{ROOT.name}_step16_backup_{timestamp}'
    if backup.exists():
        raise RuntimeError('백업 폴더가 이미 존재해. 설치 중단.')
    backup.mkdir(parents=True, exist_ok=False)
    staged_targets = []
    try:
        for relpath in MODIFY:
            dest = backup / relpath
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relpath, dest)
        for relpath in MODIFY:
            staged_targets.append(relpath)
            atomic_copy(PAYLOAD / relpath, ROOT / relpath)
        for relpath in CREATE:
            staged_targets.append(relpath)
            atomic_copy(PAYLOAD / relpath, ROOT / relpath)
    except Exception:
        for relpath in reversed(staged_targets):
            if relpath in MODIFY:
                saved = backup / relpath
                if saved.exists():
                    shutil.copy2(saved, ROOT / relpath)
            else:
                (ROOT / relpath).unlink(missing_ok=True)
        raise
    print('✅ STEP 16 검수 후보 확인 기능 설치 완료')
    print('✅ 기존 검수·기사 생성·주차 동기화 기능 유지')
    print('✅ .env, 원본 CSV, Fact Sheet, 기존 기사, DB 데이터 변경 없음')
    print('📁 백업:', backup)
    print('다음: python kpop_step16_patch\\verify_step16.py')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='STEP16 설치 스크립트')
    parser.add_argument('--dry-run', action='store_true', help='설치 전 검증만 수행')
    args = parser.parse_args()
    try:
        run(args.dry_run)
    except Exception as error:
        print('❌ STEP16 설치 중단:', error)
        raise SystemExit(1)
