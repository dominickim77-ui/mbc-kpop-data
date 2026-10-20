"""Internal worker for the explicit offline checks. Not a server or a data writer."""
import ast
import json
import os
import runpy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def deny(*args, **kwargs):
    raise AssertionError('Real DB/API access is forbidden in offline checks')


def main():
    task = sys.argv[1] if len(sys.argv) == 2 else ''
    if task not in {'syntax', 'unittest', 'charts'}:
        raise SystemExit('Unsupported offline task')
    os.chdir(ROOT)
    os.environ['STEP19_RUN_DB_TESTS'] = '0'
    os.environ['STEP27_RUN_POSTGRES_TESTS'] = '0'
    os.environ['KPOP_DB_BACKEND'] = 'legacy'
    os.environ.pop('KPOP_POSTGRES_DSN', None)
    os.environ.pop('KPOP_POSTGRES_TEST_DSN', None)
    os.environ['PYTHON_DOTENV_DISABLED'] = '1'
    for key in list(os.environ):
        if key.startswith(('MYSQL_', 'OPENAI_', 'YOUTUBE_')):
            os.environ.pop(key, None)
    if task == 'syntax':
        count = 0
        for folder, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if not d.startswith(('.git', '.venv'))
                       and d not in {'__pycache__', 'node_modules', '.reports'}]
            for name in files:
                if name.endswith('.py'):
                    path = Path(folder) / name
                    ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
                    count += 1
        print('CHECK_SUMMARY ' + json.dumps({'kind': task, 'python_files': count}))
        return 0
    # Block the actual project DB/API entry points; in-process ASGI transports remain usable.
    with patch('db.postgres_runtime._connect_driver', side_effect=deny), \
         patch('dotenv.load_dotenv', return_value=False), \
         patch('mysql.connector.connect', side_effect=deny), \
         patch('requests.sessions.Session.request', side_effect=deny), \
         patch('urllib.request.urlopen', side_effect=deny), \
         patch('openai.OpenAI', side_effect=deny), \
         patch('openai.AsyncOpenAI', side_effect=deny):
        if task == 'unittest':
            suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'), top_level_dir=str(ROOT))
            result = unittest.TextTestRunner(verbosity=2).run(suite)
            summary = {'kind': task, 'discovered': result.testsRun,
                       'passed': result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped)
                                 - len(result.expectedFailures) - len(result.unexpectedSuccesses),
                       'failures': len(result.failures), 'errors': len(result.errors),
                       'skipped': len(result.skipped), 'expected_failures': len(result.expectedFailures),
                       'unexpected_successes': len(result.unexpectedSuccesses)}
            print('CHECK_SUMMARY ' + json.dumps(summary))
            return 0 if result.wasSuccessful() else 1
        sys.argv = ['news.chart_data_manager', '--check']
        try:
            runpy.run_module('news.chart_data_manager', run_name='__main__')
        except SystemExit as exc:
            return int(exc.code or 0)
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
