"""Real isolated SQLite + in-process HTTP. No MySQL, network, paid API, or real approvals."""
import asyncio
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app as site
from security import auth, editorial_store as store
from news import editorial

PASSWORD = 'Synthetic-test-password-23'


async def request(path, method='GET', payload=None, cookie='', origin='http://127.0.0.1:8000'):
    route, _, query = path.partition('?')
    headers = [('host','127.0.0.1:8000'),('content-type','application/json')]
    if origin is not None: headers.append(('origin',origin))
    if cookie: headers.append(('cookie',cookie))
    scope = {'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','method':method,'scheme':'http',
             'path':route,'raw_path':route.encode(),'query_string':query.encode(),'root_path':'',
             'headers':[(k.encode(),v.encode()) for k,v in headers],
             'client':('127.0.0.1',1234),'server':('127.0.0.1',8000)}
    events=[]
    delivered=False
    async def receive():
        nonlocal delivered
        if not delivered:
            delivered=True
            return {'type':'http.request','body':json.dumps(payload).encode() if payload is not None else b'','more_body':False}
        return {'type':'http.disconnect'}
    async def send(event): events.append(event)
    await site.app(scope,receive,send)
    start=next(e for e in events if e['type']=='http.response.start')
    raw=b''.join(e.get('body',b'') for e in events if e['type']=='http.response.body')
    try: data=json.loads(raw)
    except (ValueError,UnicodeError): data=raw.decode()
    return start['status'],data,{k.decode():v.decode() for k,v in start['headers']}


class EditorialAuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.db=Path(self.tmp.name)/'isolated_test.sqlite3'
        env=patch.dict(os.environ,{'KPOP_AUTH_DB':str(self.db),'PYTHON_DOTENV_DISABLED':'1'})
        env.start();self.addCleanup(env.stop);store.initialize()
        for target in ['mysql.connector.connect','requests.sessions.Session.request','openai.OpenAI']:
            p=patch(target,side_effect=AssertionError('External access forbidden'));p.start();self.addCleanup(p.stop)
        self.evidence={'facts':{'week_current':{'end':'2026-10-08'},'synthetic':True},'source_sha256':{}}
        self.real_evidence=editorial.fresh_evidence
        p=patch.object(editorial,'fresh_evidence',side_effect=lambda week:(self.evidence,editorial.digest(self.evidence),'SYNTHETIC ONLY'))
        p.start();self.addCleanup(p.stop)
        self.reader=self.user('reader','READER')
        self.writer=self.user('writer','JOURNALIST')
        self.other=self.user('other','JOURNALIST')
        self.editor=self.user('editor','EDITOR')
        self.admin=self.user('admin','ADMIN')

    def call(self,path,method='GET',data=None,cookie='',**kw):
        return asyncio.run(request(path,method,data,cookie,**kw))

    def user(self,name,role):
        status,row,_=self.call('/api/auth/signup','POST',{'username':name,'password':PASSWORD})
        self.assertEqual(status,201)
        # Trusted fixture setup only; role escalation through HTTP is tested below.
        with store.connect(True) as db:db.execute('UPDATE users SET role=? WHERE id=?',(role,row['id']))
        status,_,headers=self.call('/api/auth/login','POST',{'username':name,'password':PASSWORD})
        self.assertEqual(status,200)
        return {'id':row['id'],'cookie':headers['set-cookie'].split(';')[0],'name':name,'role':role}

    def create(self,user=None):
        status,row,_=self.call('/api/editorial/articles','POST',{'title':'SYNTHETIC TEST','body':'Synthetic article, never publish.','week_end':'2026-10-08'},(user or self.writer)['cookie'])
        self.assertEqual(status,201);return row

    def submit(self,row):
        status,_,_=self.call(f"/api/editorial/articles/{row['id']}/submit",'POST',{'expected_version':row['version']},self.writer['cookie'])
        self.assertEqual(status,200)

    def review(self,row,**changes):
        body={'expected_version':row['version'],'evidence_hash':row['evidence_hash'],
              'checklist':dict.fromkeys(['numbers','period_units','no_unsupported_claims','sources'],True),
              'comment':'SYNTHETIC TEST REVIEW ONLY','decision':'APPROVED'}
        body.update(changes)
        return self.call(f"/api/editorial/articles/{row['id']}/review",'POST',body,self.editor['cookie'])

    def test_signup_escalation_password_hash_and_cookie(self):
        self.assertEqual(self.call('/api/auth/signup','POST',{'username':'attack','password':PASSWORD,'role':'ADMIN'})[0],422)
        self.assertEqual(self.call('/api/auth/me',cookie=self.reader['cookie'])[1]['role'],'READER')
        with store.connect() as db:
            hashed=db.execute('SELECT password_hash FROM users WHERE id=?',(self.reader['id'],)).fetchone()[0]
            self.assertNotIn(PASSWORD,hashed)
            self.assertTrue(auth.verify_password(PASSWORD,hashed))
        status,_,headers=self.call('/api/auth/login','POST',{'username':'reader','password':PASSWORD})
        self.assertEqual(status,200)
        for flag in ['HttpOnly','SameSite=strict','Max-Age=28800']:self.assertIn(flag,headers['set-cookie'])

    def test_wrong_password_logout_expiry_forged_cookie(self):
        self.assertEqual(self.call('/api/auth/login','POST',{'username':'reader','password':'bad-password-123'})[0],401)
        self.assertEqual(self.call('/api/auth/me',cookie='kpop_session=forged')[0],401)
        self.assertEqual(self.call('/api/auth/logout','POST',cookie=self.reader['cookie'])[0],200)
        self.assertEqual(self.call('/api/auth/me',cookie=self.reader['cookie'])[0],401)
        with store.connect(True) as db:db.execute('UPDATE sessions SET expires_at=0')
        self.assertEqual(self.call('/api/auth/me',cookie=self.writer['cookie'])[0],401)

    def test_unauthenticated_and_reader_route_matrix(self):
        for path in ['/api/news/preview','/api/news/article','/api/editorial/articles','/api/youtube-video-review/candidates']:
            self.assertEqual(self.call(path)[0],401,path)
            self.assertEqual(self.call(path,cookie=self.reader['cookie'])[0],403,path)
        self.assertEqual(self.call('/api/editorial/published',cookie=self.reader['cookie'])[1],[])
        self.assertEqual(self.call('/add-analysis','POST',cookie=self.reader['cookie'])[0],403)
        self.assertEqual(self.call('/api/auth/users',cookie=self.editor['cookie'])[0],403)

    def test_origin_protection(self):
        for origin in [None,'https://evil.example','http://localhost:8000']:
            self.assertEqual(self.call('/api/auth/signup','POST',{'username':'evil','password':PASSWORD},origin=origin)[0],403)
            self.assertEqual(self.call('/api/auth/logout','POST',cookie=self.writer['cookie'],origin=origin)[0],403)

    def test_admin_role_change_revokes_session(self):
        path=f"/api/auth/users/{self.reader['id']}/role"
        self.assertEqual(self.call(path,'PUT',{'role':'ADMIN'},self.reader['cookie'])[0],403)
        self.assertEqual(self.call(path,'PUT',{'role':'JOURNALIST'},self.admin['cookie'])[0],200)
        self.assertEqual(self.call('/api/auth/me',cookie=self.reader['cookie'])[0],401)
        self.assertEqual(self.call(f"/api/auth/users/{self.admin['id']}/role",'PUT',{'role':'READER'},self.admin['cookie'])[0],409)

    def test_throttle_persists(self):
        for _ in range(10):self.assertEqual(self.call('/api/auth/login','POST',{'username':'missing','password':PASSWORD})[0],401)
        self.assertEqual(self.call('/api/auth/login','POST',{'username':'missing','password':PASSWORD})[0],429)

    def test_other_writer_cannot_read_edit_submit(self):
        row=self.create();path=f"/api/editorial/articles/{row['id']}"
        self.assertEqual(self.call(path,cookie=self.other['cookie'])[0],404)
        self.assertEqual(self.call(path,'PUT',{'title':'stolen','body':'bad','week_end':row['week_end'],'expected_version':1},self.other['cookie'])[0],404)
        self.assertEqual(self.call(path+'/submit','POST',{'expected_version':1},self.other['cookie'])[0],404)
        self.assertEqual(self.call('/api/editorial/articles',cookie=self.other['cookie'])[1],[])

    def test_hold_revise_approve_and_immutable_history(self):
        row=self.create();self.submit(row)
        checklist=dict.fromkeys(['numbers','period_units','no_unsupported_claims','sources'],True);checklist['numbers']=False
        status,result,_=self.review(row,checklist=checklist)
        self.assertEqual((status,result['status']),(200,'ON_HOLD'));self.assertTrue(result['approval_blocked'])
        self.assertEqual(self.call('/api/editorial/published',cookie=self.reader['cookie'])[1],[])
        status,row,_=self.call(f"/api/editorial/articles/{row['id']}",'PUT',{'title':'Revised','body':'Corrected synthetic','week_end':'2026-10-08','expected_version':1},self.writer['cookie'])
        self.assertEqual((status,row['status'],row['version']),(200,'REVISED',2));self.submit(row)
        self.assertEqual(self.review(row)[1]['status'],'APPROVED')
        self.assertEqual(len(self.call('/api/editorial/published',cookie=self.reader['cookie'])[1]),1)
        with store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM reviews').fetchone()[0],2)
            for table in ['reviews','revisions','audit']:
                with self.assertRaises(sqlite3.IntegrityError):db.execute('DELETE FROM '+table)
        detail=self.call(f"/api/editorial/articles/{row['id']}",cookie=self.writer['cookie'])[1]
        self.assertEqual(len(detail['revisions']),2);self.assertEqual(len(detail['reviews']),2)

    def test_approval_edit_invalidates_publication_and_old_version(self):
        row=self.create();self.submit(row);self.assertEqual(self.review(row)[0],200)
        self.call(f"/api/editorial/articles/{row['id']}",'PUT',{'title':'Changed','body':'new content','week_end':row['week_end'],'expected_version':1},self.writer['cookie'])
        self.assertEqual(self.call('/api/editorial/published',cookie=self.reader['cookie'])[1],[])
        self.assertEqual(self.review(row)[0],409)

    def test_evidence_change_prevents_review_and_publication(self):
        row=self.create();self.submit(row);self.evidence['changed']=True
        self.assertEqual(self.review(row)[0],409)
        self.evidence.pop('changed');self.assertEqual(self.review(row)[0],200)
        self.evidence['changed']=True
        self.assertEqual(self.call('/api/editorial/published',cookie=self.reader['cookie'])[1],[])

    def test_strict_checklist_and_self_review(self):
        row=self.create();self.submit(row)
        self.assertEqual(self.review(row,checklist={'numbers':'true'})[0],422)
        self.assertEqual(self.review(row,comment='  ')[0],422)
        own=self.create(self.editor)
        self.call(f"/api/editorial/articles/{own['id']}/submit",'POST',{'expected_version':1},self.editor['cookie'])
        self.assertEqual(self.review(own)[0],403)

    def test_withdraw_preserves_records(self):
        row=self.create();self.submit(row);self.review(row)
        self.assertEqual(self.call(f"/api/editorial/articles/{row['id']}/withdraw",'POST',{'expected_version':1},self.writer['cookie'])[0],200)
        self.assertEqual(self.call('/api/editorial/published',cookie=self.reader['cookie'])[1],[])
        with store.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM reviews').fetchone()[0],1)

    def test_real_legacy_fact_validation(self):
        evidence,fingerprint,ref=self.real_evidence('2026-10-08')
        self.assertEqual(len(evidence['source_sha256']),4)
        self.assertEqual(len(fingerprint),64)
        self.assertIn('20261008',ref)
        from fastapi import HTTPException
        with self.assertRaises(HTTPException):self.real_evidence('2099-01-01')

    def test_authenticated_fact_review_roundtrip_and_source_change(self):
        from tests.test_weekly_facts import WeeklyFactTests
        from news import weekly_facts as wf
        fixture=WeeklyFactTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        body={k:fixture.review[k] for k in ['draft_sha256','period_evidence','period_review','tracks']}
        path=f'/api/editorial/fact-drafts/{fixture.week}/review'
        self.assertEqual(self.call(path,'POST',body,self.writer['cookie'])[0],403)
        status,result,_=self.call(path,'POST',body,self.editor['cookie'])
        self.assertEqual(status,200);self.assertFalse(result['article_publication_approved'])
        with patch.object(wf,'ROOT',fixture.root):
            facts=wf.load_reviewed(fixture.root,fixture.week)
            self.assertEqual(facts['human_review']['reviewer'],f"user:{self.editor['id']}")
            source=fixture.root/fixture.draft['source_refs']['spotify_current']['path']
            source.write_bytes(source.read_bytes()+b'\n')
            with self.assertRaises(ValueError):wf.load_reviewed(fixture.root,fixture.week)
        with store.connect() as db:
            with self.assertRaises(sqlite3.IntegrityError):db.execute('DELETE FROM fact_reviews')

    def test_youtube_review_cache_is_owned(self):
        from news import youtube_video_review_step17b as yt
        from fastapi import HTTPException
        from starlette.requests import Request
        import time
        token=auth.current_user.set(self.editor)
        self.addCleanup(auth.current_user.reset,token)
        request=Request({'type':'http','method':'POST','headers':[(b'host',b'127.0.0.1:8000'),(b'origin',b'http://127.0.0.1:8000'),(b'x-requested-with',b'KpopYouTubeReview'),(b'content-type',b'application/json')]})
        body=yt.ApproveRequest(song_id=1,video_id='abcdefghijk',review_token='other-user-token',verified_channel=True,verified_track_version=True,understood_lifetime_metric=True)
        with patch.dict(yt._sessions,{'other-user-token':{'song_id':1,'at':time.monotonic(),'user_id':self.admin['id']}},clear=True), patch('news.youtube_approval_lock.latest_approved',return_value=None):
            with self.assertRaises(HTTPException) as caught:yt.approve_video(request,body)
            self.assertEqual(caught.exception.status_code,409)

    def test_selection_isolation_and_restart_persistence(self):
        selection=auth.UserSelection()
        for user,ids in [(self.reader,[1,2]),(self.writer,[7])]:
            token=auth.current_user.set(user)
            try:selection.extend(ids);self.assertEqual(list(selection),ids)
            finally:auth.current_user.reset(token)
        self.assertEqual(self.call('/reset-analysis','POST',cookie=self.reader['cookie'])[0],303)
        with store.connect() as db:
            self.assertEqual(json.loads(db.execute('SELECT selection FROM users WHERE id=?',(self.writer['id'],)).fetchone()[0]),[7])
        row=self.create();self.submit(row);self.review(row)
        # Independent Python process verifies durable records, not only same-process caches.
        import subprocess,sys
        code='import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); print(c.execute("SELECT status FROM articles").fetchone()[0], c.execute("SELECT COUNT(*) FROM reviews").fetchone()[0])'
        result=subprocess.run([sys.executable,'-B','-c',code,str(self.db)],capture_output=True,text=True,check=True)
        self.assertEqual(result.stdout.strip(),'APPROVED 1')


if __name__=='__main__':unittest.main()
