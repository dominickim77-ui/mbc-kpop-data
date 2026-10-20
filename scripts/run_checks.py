"""One explicit check entry point. Offline default never opts into real DB tests."""
import argparse
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    # Windows redirected output can default to cp949 even though workers use UTF-8.
    # Keep a successful check from crashing while printing its Korean/emoji report.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='backslashreplace')
    parser = argparse.ArgumentParser(description='기본 오프라인 회귀 / 명시적 읽기 전용 DB 또는 분리 DB 검증')
    parser.add_argument('--mode', choices=('offline', 'db-readonly', 'test-db'), default='offline')
    parser.add_argument('--database')
    parser.add_argument('--allow-test-db', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args(argv)
    if args.mode == 'db-readonly' and not args.database:
        parser.error('db-readonly requires --database')
    if args.mode == 'test-db' and not args.allow_test_db:
        parser.error('test-db requires --allow-test-db (creates/deletes only isolated test databases)')
    if args.allow_test_db and args.mode != 'test-db':
        parser.error('--allow-test-db is only valid with --mode test-db')
    env = dict(os.environ, PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1',
               STEP19_RUN_DB_TESTS='0', PYTHON_DOTENV_DISABLED='1', PYTHONNOUSERSITE='1')
    env.pop('PYTHONPATH', None)
    env.pop('PYTHONHOME', None)
    python = [sys.executable, '-B']
    if args.mode == 'offline':
        tasks = [(name, python + ['-m', 'scripts.offline_worker', name])
                 for name in ('syntax', 'unittest', 'charts')]
    elif args.mode == 'db-readonly':
        tasks = [('schema', python + [str(ROOT / 'scripts/check_db_schema.py'), '--database', args.database])]
    else:
        env['STEP19_RUN_DB_TESTS'] = '1'
        tasks = [('isolated_test_db', python + ['-m', 'unittest', 'discover', '-s', 'tests', '-t', '.',
                                              '-p', 'test_db_schema_reproduction.py', '-v'])]
    results = []
    for name, command in tasks:
        try:
            proc = subprocess.run(command, cwd=ROOT, env=env, text=True, encoding='utf-8',
                                  capture_output=True, timeout=240)
        except subprocess.TimeoutExpired:
            results.append({'check': name, 'exit_code': 124, 'error': 'timeout'})
            continue
        print(proc.stdout, end='')
        print(proc.stderr, end='', file=sys.stderr)
        item = {'check': name, 'exit_code': proc.returncode}
        for line in proc.stdout.splitlines():
            if line.startswith('CHECK_SUMMARY '):
                item['summary'] = json.loads(line.removeprefix('CHECK_SUMMARY '))
        results.append(item)
    report = {'mode': args.mode, 'python': platform.python_version(), 'executable': sys.executable,
              'checks': results, 'passed': all(r['exit_code'] == 0 for r in results)}
    print('RUN_SUMMARY ' + json.dumps(report, ensure_ascii=False))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
