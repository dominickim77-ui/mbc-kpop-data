import os
import subprocess
import sys
import unittest
from pathlib import Path


class ReportEncodingTests(unittest.TestCase):
    def test_redirected_cp949_parent_can_print_utf8_worker_output(self):
        code = """from unittest.mock import patch
import subprocess
from scripts.run_checks import main
result = subprocess.CompletedProcess([],0,stdout='\\u2705 \\ud55c\\uae00\\n',stderr='')
with patch('scripts.run_checks.subprocess.run',return_value=result):
    raise SystemExit(main([]))
"""
        process = subprocess.run(
            [sys.executable, '-B', '-c', code],
            cwd=Path(__file__).resolve().parents[1],
            env=dict(os.environ, PYTHONIOENCODING='cp949', PYTHONUTF8='0'),
            capture_output=True, timeout=15)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn('✅ 한글', process.stdout.decode('utf-8'))
