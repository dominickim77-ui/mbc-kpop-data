"""Explicit local launcher using this interpreter and the project root."""
import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description='기존 로컬 개발 서버 실행: http://127.0.0.1:8000')
    parser.parse_args(argv)
    env = dict(os.environ, PYTHONUTF8='1')
    return subprocess.call([sys.executable, '-m', 'uvicorn', 'app:app', '--app-dir', str(ROOT),
                            '--host', '127.0.0.1', '--port', '8000', '--reload'], cwd=ROOT, env=env)


if __name__ == '__main__':
    raise SystemExit(main())
