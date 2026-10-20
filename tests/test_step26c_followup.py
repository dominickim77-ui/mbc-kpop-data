import contextlib
import hashlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from fastapi import HTTPException
from security import admin, auth, editorial_store as store
from news import youtube_video_review_step17b as review
import app


class YouTubeErrors(unittest.TestCase):
    def call(self,status,payload):
        response=Mock(status_code=status,ok=False)
        response.json.return_value=payload
        with patch.object(review.requests,'get',return_value=response):
            with self.assertRaises(HTTPException) as caught:
                review._youtube_json('search',{'key':'private-test-key'})
        self.assertNotIn('private-test-key',str(caught.exception.detail))
        return caught.exception

    def test_quota_distinct_from_app_permissions(self):
        self.assertEqual(self.call(403,{'error':{'errors':[{'reason':'quotaExceeded'}]}}).status_code,429)

    def test_api_access_is_not_user_role(self):
        result=self.call(403,{'error':{'errors':[{'reason':'accessNotConfigured'}]}})
        self.assertEqual(result.status_code,502)
        self.assertIn('API 접근',result.detail)

    def test_unstructured_403_not_mislabelled_quota(self):
        self.assertEqual(self.call(403,{'error':None}).status_code,502)

    def test_rate_limit(self):
        self.assertEqual(self.call(429,{}).status_code,429)

    def test_key_error(self):
        self.assertEqual(self.call(401,{}).status_code,502)

    def test_redirect_anchor(self):
        response=app.analysis_redirect('/?artist=BTS&week_end=2026-10-08')
        self.assertEqual(response.status_code,303)
        self.assertEqual(response.headers['location'],'/?artist=BTS&week_end=2026-10-08#analysis-workspace')


class AdminOperations(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.path=Path(tmp.name)/'auth.sqlite3'
        p=patch.dict(os.environ,{'KPOP_AUTH_DB':str(self.path)})
        p.start();self.addCleanup(p.stop)
        store.initialize()
        with store.connect(True) as db:
            self.uid=db.execute('INSERT INTO users(username,password_hash) VALUES(?,?)',
                                ('operator',auth.password_hash('Synthetic-test-password-26'))).lastrowid

    def run_admin(self,argv,password='Synthetic-test-password-26'):
        with patch('sys.argv',['admin',*argv]),patch.object(admin.getpass,'getpass',return_value=password),contextlib.redirect_stdout(io.StringIO()) as out:
            admin.main()
        return out.getvalue()

    def test_status_is_readonly(self):
        before=hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.assertIn('0개',self.run_admin(['status']))
        self.assertEqual(before,hashlib.sha256(self.path.read_bytes()).hexdigest())

    def test_bootstrap_verifies_password_and_records_audit(self):
        with self.assertRaises(SystemExit):self.run_admin(['bootstrap','--username','operator'],'wrong')
        with store.connect() as db:self.assertEqual(db.execute('SELECT role FROM users').fetchone()[0],'READER')
        self.run_admin(['bootstrap','--username','operator'])
        with store.connect() as db:
            self.assertEqual(db.execute('SELECT role FROM users').fetchone()[0],'ADMIN')
            self.assertEqual(db.execute("SELECT COUNT(*) FROM audit WHERE action='BOOTSTRAP_ADMIN'").fetchone()[0],1)
        with self.assertRaises(SystemExit):self.run_admin(['bootstrap','--username','operator'])

    def test_missing_store_not_created(self):
        missing=self.path.with_name('absent.sqlite3')
        with patch.dict(os.environ,{'KPOP_AUTH_DB':str(missing)}):
            with self.assertRaises(SystemExit):self.run_admin(['status'])
        self.assertFalse(missing.exists())
