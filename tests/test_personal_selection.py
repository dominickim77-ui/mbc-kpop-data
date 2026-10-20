"""Personal selection boundary tests: isolated auth store, no external writes."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote_plus
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
import app as site
from security import auth, editorial_store as store


class PersonalSelectionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env = patch.dict(os.environ, {'KPOP_AUTH_DB':str(Path(tmp.name)/'auth.sqlite3')})
        env.start(); self.addCleanup(env.stop)
        store.initialize()
        with store.connect(True) as db:
            for name in ['one','two']:
                db.execute('INSERT INTO users(username,password_hash) VALUES(?,?)',(name,'unused'))
        self.token = auth.current_user.set({'id':1,'role':'READER'})
        self.addCleanup(auth.current_user.reset,self.token)
        self.rows = [dict(song_id=i,artist=f'Artist{i}',track=f'Track{i}') for i in range(1,13)]
        chart = pd.DataFrame([dict(rank=i,artist_names=f'Artist{i}',track_name=f'Track{i}',streams=100) for i in range(1,14)])
        for target, kwargs in [
            ('app.load_spotify_csv', {'return_value':chart}),
            ('app.get_dashboard_data', {'return_value':self.rows}),
            ('mysql.connector.connect', {'side_effect':AssertionError('MySQL writes forbidden')}),
            ('requests.sessions.Session.request', {'side_effect':AssertionError('API forbidden')}),
        ]:
            p=patch(target,**kwargs);p.start();self.addCleanup(p.stop)

    def add(self, ranks):
        response=site.select_analysis(ranks,'Artist','2026-10-08')
        self.assertEqual(response.status_code,303)
        return unquote_plus(response.headers['location'])

    def test_existing_and_duplicates(self):
        self.assertIn('개인 분석에 추가',self.add([1,1,2]))
        self.add([1])
        self.assertEqual(list(site.analysis_song_ids),[1,2])

    def test_missing_is_atomic(self):
        self.add([1])
        self.assertIn('저장된 데이터를 확인',self.add([2,13]))
        self.assertEqual(list(site.analysis_song_ids),[1])

    def test_invalid_and_empty(self):
        self.assertIn('분석할 곡',self.add([]))
        self.assertIn('해당 기간',self.add([999]))
        self.assertEqual(list(site.analysis_song_ids),[])

    def test_ten_limit(self):
        self.add(list(range(1,11)))
        self.assertIn('최대 10',self.add([11]))
        self.assertEqual(len(site.analysis_song_ids),10)

    def test_oversized_request(self):
        self.assertIn('최대 10',self.add(list(range(1,12))))
        self.assertEqual(list(site.analysis_song_ids),[])

    def test_isolation_remove_reset(self):
        self.add([1,2])
        token=auth.current_user.set({'id':2,'role':'READER'})
        try:
            self.assertEqual(list(site.analysis_song_ids),[])
            self.add([3])
            site.remove_analysis(1,'')
            self.assertEqual(list(site.analysis_song_ids),[3])
            site.reset_analysis('')
        finally:auth.current_user.reset(token)
        self.assertEqual(list(site.analysis_song_ids),[1,2])

    def test_concurrent_add_limit(self):
        def add_one(i):
            token=auth.current_user.set({'id':1,'role':'READER'})
            try:return self.add([i])
            finally:auth.current_user.reset(token)
        with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(add_one,range(1,13)))
        self.assertEqual(len(site.analysis_song_ids),10)

    def test_ambiguous_existing_data(self):
        self.rows.append(dict(song_id=99,artist='Artist1',track='Track1'))
        self.assertIn('확인',self.add([1]))
        self.assertEqual(list(site.analysis_song_ids),[])
