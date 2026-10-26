"""Real SQLite/HTTP policy regression; model boundary stubbed, never paid."""
import json,os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,MagicMock
from starlette.requests import Request
from tests.test_editorial_auth import EditorialAuthTests
from security import auth,editorial_store as store
from news import news_routes as routes,article_origin,selected_news
from news.provenance import generation_record

REFERENCE=Path(os.environ.get('KPOP_TEST_REFERENCE_ROOT', str(Path(__file__).resolve().parents[1])))

class OriginTests(EditorialAuthTests):
    def setUp(self):
        super().setUp()
        p=patch.object(selected_news,'ROOT',REFERENCE);p.start();self.addCleanup(p.stop)

    def receipt(self, output='Synthetic AI output', user=None):
        user=user or self.writer
        token=auth.current_user.set(user)
        client=MagicMock();client.__enter__.return_value=client
        client.responses.create.return_value=SimpleNamespace(status='completed',output_text=output)
        facts={'week_current':{'end':'2026-10-08'}}
        self.evidence['facts']=facts
        snapshot={'approved_tracks':[],'selected_tracks':[],'excluded_tracks':[]}
        request=Request({'type':'http','method':'POST','scheme':'http','headers':[(b'host',b'localhost:8000'),(b'origin',b'http://localhost:8000'),(b'x-requested-with',b'KpopNewsPanel'),(b'content-type',b'application/json')]})
        try:
            with patch.object(routes,'ROOT',Path(self.tmp.name)),patch.object(routes,'ARTICLES',Path(self.tmp.name)/'articles'),patch.object(routes,'_selection',return_value=(facts,snapshot)),patch.object(routes,'evidence_for_selected',return_value={'analysis_tracks':[{'track_name':'Test'}]}),patch.dict(os.environ,{'OPENAI_API_KEY':'synthetic-not-a-key'}),patch('openai.OpenAI',return_value=client):
                result=routes.generate_selected_article(request,routes.GenerateRequest(confirm_paid=True))
            with store.connect() as db:
                rec=article_origin.receipt(db,result['generation_id'],user['id'])
            sent=client.responses.create.call_args.kwargs
            self.assertEqual(rec['generation']['input_json'],sent['input'])
            self.assertEqual(rec['generation']['instructions'],sent['instructions'])
            return result['generation_id'],output
        finally:auth.current_user.reset(token)

    def ai(self, rid='', output='Synthetic missing AI'):
        return self.call('/api/editorial/articles','POST',{'title':'Synthetic AI','body':output,'week_end':'2026-10-08','origin':'AI','human_authored':False,'generation_id':rid},self.writer['cookie'])

    def force(self,row,status):
        with store.connect(True) as db:db.execute('UPDATE articles SET status=? WHERE id=?',(status,row['id']))

    def visible(self):return self.call('/api/editorial/published',cookie=self.reader['cookie'])[1]

    def test_valid_ai_receipt_and_human_review(self):
        rid,text=self.receipt();status,row,_=self.ai(rid,text)
        self.assertEqual(status,201);self.submit(row)
        self.assertEqual(self.review(row)[0],200);self.assertEqual(len(self.visible()),1)

    def test_missing_ai_generation_record_is_blocked_at_creation(self):
        status,row,_=self.ai();self.assertEqual(status,409)
        self.assertEqual(self.visible(),[])
    def test_status_without_review_never_publishes_even_valid_ai(self):
        rid,text=self.receipt();_,row,_=self.ai(rid,text)
        self.force(row,'APPROVED');self.assertEqual(self.visible(),[])

    def test_ai_body_version_and_evidence_tampering_hidden(self):
        rid,text=self.receipt();_,row,_=self.ai(rid,text);self.submit(row);self.review(row)
        for field,value in [('body','Tampered'),('version',2),('evidence','{}')]:
            with self.subTest(field=field):
                with store.connect(True) as db:db.execute(f'UPDATE articles SET {field}=? WHERE id=?',(value,row['id']))
                self.assertEqual(self.visible(),[])
                with store.connect(True) as db:db.execute(f'UPDATE articles SET {field}=? WHERE id=?',(row[field],row['id']))

    def test_ai_edit_requires_new_matching_receipt_and_cannot_become_human(self):
        rid,text=self.receipt();_,row,_=self.ai(rid,text)
        path=f"/api/editorial/articles/{row['id']}"
        base={'title':'Edited','body':'Edited AI','week_end':row['week_end'],'expected_version':1,'origin':'AI','human_authored':False,'generation_id':rid}
        self.assertEqual(self.call(path,'PUT',base,self.writer['cookie'])[0],409)
        self.assertEqual(self.call(path,'PUT',dict(base,origin='HUMAN',human_authored=True,generation_id=''),self.writer['cookie'])[0],409)
        new_id,new_text=self.receipt('Edited AI')
        status,edited,_=self.call(path,'PUT',dict(base,generation_id=new_id),self.writer['cookie'])
        self.assertEqual((status,edited['version']),(200,2));self.submit(edited);self.assertEqual(self.review(edited)[0],200)

    def test_receipt_foreign_reused_forged_and_stale_evidence(self):
        rid,text=self.receipt(user=self.other)
        self.assertEqual(self.ai(rid,text)[0],409)
        self.assertEqual(self.ai('a'*48,text)[0],409)
        rid,text=self.receipt();self.assertEqual(self.ai(rid,text)[0],201)
        self.assertEqual(self.ai(rid,text)[0],409)
        rid,text=self.receipt('New generation');self.evidence['changed']=True
        self.assertEqual(self.ai(rid,text)[0],409)

    def test_corrupt_generation_input_prompt_output_and_method_rejected(self):
        # Malformed receipts injected only as synthetic owner fixture; all server validators run.
        from news.weekly_facts import digest
        record=generation_record({'x':1})
        for key,value in [('input_json','{}'),('instructions','tampered'),('input_sha256','0'*64),('instructions_sha256','0'*64),('prompt_version','unknown')]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                with store.connect(True) as db:article_origin.issue_receipt(db,self.writer['id'],record=dict(record,**{key:value}),output='x',model='stub',week='2026-10-08',evidence_hash=digest(self.evidence))
        with store.connect(True) as db:
            store.audit(db,self.writer['id'],'AI_GENERATED','b'*48,{'schema':1,'method':'TEMPLATE','model':'stub','generation':record,'output':'x','output_sha256':'0'*64,'week_end':'2026-10-08','evidence_hash':digest(self.evidence)})
        self.assertEqual(self.ai('b'*48,'x')[0],409)
        with store.connect(True) as db:
            store.audit(db,self.writer['id'],'AI_GENERATED','c'*48,{'schema':1,'method':'AI','model':'stub','generation':record,'output':'x','output_sha256':'0'*64,'week_end':'2026-10-08','evidence_hash':digest(self.evidence)})
        self.assertEqual(self.ai('c'*48,'x')[0],409)

    def test_human_needs_no_generation_and_editor_must_confirm_origin(self):
        row=self.create();self.submit(row)
        self.assertEqual(self.review(row,authorship_confirmed=False)[0],409)
        self.assertEqual(self.review(row)[0],200)
        with store.connect() as db:self.assertEqual(len(article_origin.events(db,'AI_GENERATED')),0)

    def test_unknown_historical_approved_row_not_backfilled(self):
        from tests.test_editorial_auth import request
        import asyncio
        status,row,_=asyncio.run(request('/api/editorial/articles','POST',{'title':'Old client','body':'Unknown origin','week_end':'2026-10-08'},self.writer['cookie']))
        self.assertEqual(status,201);self.force(row,'APPROVED')
        self.assertEqual(self.visible(),[])
        with store.connect() as db:self.assertEqual(db.execute('SELECT status FROM articles WHERE id=?',(row['id'],)).fetchone()[0],'APPROVED')

    def test_all_four_legacy_drafts_blocked_and_exact_human_relabel_rejected(self):
        files=list((REFERENCE/'articles').glob('draft_openai*.json'));self.assertEqual(len(files),4)
        for p in files:
            data=json.loads(p.read_text(encoding='utf-8'));text=data['article'].strip()
            with self.subTest(file=p.name):
                status,_,_=self.ai(output=text);self.assertEqual(status,409)
                self.assertEqual(self.visible(),[])
                status,_,_=self.call('/api/editorial/articles','POST',{'title':'Relabel','body':text,'week_end':'2026-10-08','origin':'HUMAN','human_authored':True},self.writer['cookie'])
                self.assertEqual(status,409)
