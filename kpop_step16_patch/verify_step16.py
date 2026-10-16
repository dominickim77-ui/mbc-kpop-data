"""Free STEP16 verification: no MySQL, web, YouTube or OpenAI call."""
from __future__ import annotations

import hashlib
import importlib
import os
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAYLOAD = Path(__file__).resolve().parent / 'payload'
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)


def check() -> None:
    for name in ['news/review_candidates_step16.py', 'news/news_routes.py', 'templates/index.html',
                 'static/news_panel.js', 'static/style.css']:
        assert (ROOT / name).is_file(), name
        assert (ROOT / name).read_bytes().replace(b'\r\n', b'\n') == (PAYLOAD / name).read_bytes().replace(b'\r\n', b'\n'), name
    print('✅ STEP 16 설치 파일 5개 확인')

    from news.chart_data_manager import choose_pair
    from news.review_candidates_step16 import build_review_queue
    p, _, _ = choose_pair(root=ROOT, week_end='2026-10-08')
    assert p is not None
    selected = [
        {'artist':'BTS','track':'SWIM'},
        {'artist':'BTS','track':'NORMAL'},
        {'artist':'ROSÉ, Bruno Mars','track':'APT.'},
        {'artist':'LISA','track':'SaWaDiKa'},
        {'artist':'KATSEYE','track':'Hootie Frutti'},
        {'artist':'KATSEYE','track':'Animal'},
    ]
    source_files = [ROOT / path for path in p.files.values()]
    before = [hashlib.sha256(path.read_bytes()).hexdigest() for path in source_files]
    report = build_review_queue(selected, p, ROOT)
    statuses = {(t['artist'],t['track']):t['review_status'] for t in report['candidates']}
    assert statuses[('BTS','SWIM')] == 'SPOTIFY_ONLY_REVIEW_PENDING'
    assert statuses[('BTS','NORMAL')] == 'SPOTIFY_ONLY_REVIEW_PENDING'
    assert statuses[('ROSÉ, Bruno Mars','APT.')] == 'SPOTIFY_ONLY_REVIEW_PENDING'
    assert statuses[('LISA','SaWaDiKa')] == 'DUAL_CHART_REVIEWED'
    assert statuses[('KATSEYE','Animal')] == 'DUAL_CHART_REVIEWED'
    assert statuses[('KATSEYE','Hootie Frutti')] == 'HOLD_VERSION'
    assert report['publication_approved'] is False and report['auto_approval'] is False
    assert len(report['candidates']) == 6
    assert [hashlib.sha256(path.read_bytes()).hexdigest() for path in source_files] == before
    print('✅ BTS 2곡·ROSÉ APT.: Spotify 단독 검수 후보')
    print('✅ LISA·KATSEYE Animal 기존 교차 검수 승인 유지')
    print('✅ Hootie Frutti 버전 검수 보류 유지')
    print('✅ CSV 변경 없고 검수 자동 승인 없음')

    # Isolate the HTTP test from real MySQL and network.
    from fastapi.testclient import TestClient
    fake_mysql = types.ModuleType('mysql'); fake_mysql.__path__=[]
    fake_mysql.connector = types.ModuleType('mysql.connector')
    sys.modules['mysql'] = fake_mysql
    sys.modules['mysql.connector'] = fake_mysql.connector
    app = importlib.import_module('app')
    import news.news_routes as routes
    prior_reader = routes.read_current_selection
    routes.read_current_selection = lambda: selected
    try:
        with TestClient(app.app, base_url='http://127.0.0.1:8000') as client:
            res = client.get('/api/news/review-candidates?week_end=2026-10-08')
            assert res.status_code == 200, res.text[:500]
            data = res.json()
            assert data['selected_count'] == 6 and data['publication_approved'] is False
            assert data['candidates'][0]['review_status'] == 'SPOTIFY_ONLY_REVIEW_PENDING'
            bad = client.get('/api/news/review-candidates?week_end=2030-01-03')
            assert bad.status_code == 422
            print('✅ GET /api/news/review-candidates 200 · 미등록 주차 422')
            old = client.get('/api/news/selection?week_end=2026-10-08')
            assert old.status_code == 200 and old.json()['can_generate'] is True
            assert old.json()['publication_approved'] is False
            print('✅ 기존 기사 선택·승인 보호 기능 유지')
    finally:
        routes.read_current_selection = prior_reader
    print('🎉 STEP16 무료 검증 완료 · MySQL/YouTube/OpenAI 실호출 없음')


if __name__ == '__main__':
    try:
        check()
    except Exception as error:
        print('❌ STEP16 검증 실패:', repr(error))
        raise SystemExit(1)
