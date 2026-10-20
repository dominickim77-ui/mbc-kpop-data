"""Local operator bootstrap; no public elevation endpoint and no default password."""
import argparse
import getpass
import sqlite3
from contextlib import closing
from security.editorial_store import initialize, connect, audit, database_path
from security.auth import password_hash


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['status', 'init', 'bootstrap'])
    parser.add_argument('--username')
    args = parser.parse_args()
    if args.action == 'status':
        path = database_path().resolve()
        if not path.is_file():
            raise SystemExit('인증 저장소가 없습니다. 운영 설정 경로를 확인해 주세요.')
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
            db.execute('PRAGMA query_only=ON')
            count = db.execute("SELECT COUNT(*) FROM users WHERE role='ADMIN'").fetchone()[0]
        print(f'ADMIN 계정: {count}개. 계정과 역할은 변경하지 않았습니다.')
        return
    if args.action == 'init':
        initialize()
        print('별도 인증·기사 DB 초기화 완료. 기존 MySQL 변경 없음.')
        return
    if not args.username:
        parser.error('--username required (existing registered account)')
    password = getpass.getpass('등록 계정 비밀번호: ')
    from security.auth import verify_password
    with connect(True) as db:
        if db.execute("SELECT 1 FROM users WHERE role='ADMIN'").fetchone():
            raise SystemExit('관리자가 이미 있습니다. 관리자 화면에서 역할을 부여하세요.')
        row = db.execute('SELECT * FROM users WHERE username=?', (args.username.casefold(),)).fetchone()
        if not row or not verify_password(password, row['password_hash']):
            raise SystemExit('계정 확인 실패')
        db.execute("UPDATE users SET role='ADMIN' WHERE id=?", (row['id'],))
        db.execute('DELETE FROM sessions WHERE user_id=?', (row['id'],))
        audit(db, row['id'], 'BOOTSTRAP_ADMIN', row['id'], {})
    print('최초 관리자 지정 완료. 다시 로그인하세요.')


if __name__ == '__main__': main()
