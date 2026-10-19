"""Exercise harmless entry points from a neutral directory; never run data writers."""
import os
import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import run_checks, run_local

ROOT = Path(__file__).resolve().parents[1]


class ExecutionEnvironmentTests(unittest.TestCase):
    def setUp(self):
        # Expected parser/runner failures are asserted, not printed as real check summaries.
        for redirect in [contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO())]:
            redirect.__enter__()
            self.addCleanup(redirect.__exit__, None, None, None)

    def probe(self, args, cwd):
        env = dict(os.environ, PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', PYTHON_DOTENV_DISABLED='1')
        proc = subprocess.run([sys.executable, '-B', *args], cwd=cwd, env=env,
                              capture_output=True, text=True, encoding='utf-8', timeout=15)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout

    def test_app_import_and_templates_outside_project_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            self.probe(['-c', 'import sys;sys.path.insert(0,sys.argv[1]);import app;app.templates.get_template("index.html");print("OK")', str(ROOT)], folder)

    def test_current_offline_modules_import_from_neutral_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            self.probe(['-c', 'import sys;sys.path.insert(0,sys.argv[1]);import news.weekly_changes,news.review_tracks', str(ROOT)], folder)

    def test_legacy_file_commands_help_without_generating_data(self):
        with tempfile.TemporaryDirectory() as folder:
            for name in ['weekly_changes.py', 'review_tracks.py']:
                with self.subTest(name=name):
                    self.probe([str(ROOT / 'news' / name), '--help'], folder)

    def test_module_commands_help_without_generating_data(self):
        for name in ['news.weekly_changes', 'news.review_tracks']:
            with self.subTest(name=name):
                self.probe(['-m', name, '--help'], ROOT)

    def test_local_launcher_help_does_not_start_server(self):
        with tempfile.TemporaryDirectory() as folder:
            self.probe([str(ROOT / 'scripts/run_local.py'), '--help'], folder)

    def test_local_launcher_uses_current_interpreter_and_allowed_address(self):
        with patch.object(run_local.subprocess, 'call', return_value=0) as child:
            self.assertEqual(run_local.main([]), 0)
        args = child.call_args.args[0]
        self.assertEqual(args[0], sys.executable)
        self.assertIn('127.0.0.1', args)
        self.assertIn('8000', args)
        self.assertEqual(child.call_args.kwargs['cwd'], ROOT)

    def test_default_runner_overrides_inherited_test_db_opt_in(self):
        result = subprocess.CompletedProcess([], 0, stdout='', stderr='')
        with patch.dict(os.environ, {'STEP19_RUN_DB_TESTS': '1'}), \
             patch.object(run_checks.subprocess, 'run', return_value=result) as child:
            self.assertEqual(run_checks.main([]), 0)
        self.assertEqual(child.call_count, 3)
        for call in child.call_args_list:
            self.assertEqual(call.kwargs['env']['STEP19_RUN_DB_TESTS'], '0')
            self.assertEqual(call.args[0][0], sys.executable)
            self.assertEqual(call.kwargs['cwd'], ROOT)

    def test_test_db_mode_requires_separate_explicit_permission(self):
        with patch.object(run_checks.subprocess, 'run') as child:
            with self.assertRaises(SystemExit):
                run_checks.main(['--mode', 'test-db'])
            child.assert_not_called()

    def test_readonly_mode_requires_explicit_database(self):
        with self.assertRaises(SystemExit):
            run_checks.main(['--mode', 'db-readonly'])

    def test_runner_propagates_failed_check(self):
        result = subprocess.CompletedProcess([], 7, stdout='', stderr='fixture failure')
        with patch.object(run_checks.subprocess, 'run', return_value=result):
            self.assertEqual(run_checks.main([]), 1)

    def test_runner_reports_timeout_as_failure(self):
        with patch.object(run_checks.subprocess, 'run', side_effect=subprocess.TimeoutExpired(['fixture'], 1)):
            self.assertEqual(run_checks.main([]), 1)
