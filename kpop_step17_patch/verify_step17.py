"""Offline local checks for STEP17A. No MySQL, OpenAI or YouTube API requests."""
import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from news.chart_data_manager import choose_pair
from news.spotify_only_preview import make_spotify_only_preview, SpotifyOnlyPreviewError


def check():
    pair, periods, _ = choose_pair(root=ROOT, week_end='2026-10-08')
    assert pair and pair.current_end.isoformat() == '2026-10-08'
    selected = [
        {'artist': 'BTS', 'track': 'SWIM'},
        {'artist': 'BTS', 'track': 'NORMAL'},
        {'artist': 'ROSÉ, Bruno Mars', 'track': 'APT.'},
        {'artist': 'KATSEYE', 'track': 'Hootie Frutti'},
        {'artist': 'KATSEYE', 'track': 'Animal'},
        {'artist': 'LISA', 'track': 'SaWaDiKa'},
    ]
    result = make_spotify_only_preview(selected, pair, root=ROOT)
    tracks = {x['track']: x for x in result['evidence']['candidates']}
    assert {'SWIM', 'NORMAL', 'APT.'}.issubset(tracks)
    assert 'Hootie Frutti' not in tracks, 'Version-ambiguous song must not be included.'
    assert 'Animal' not in tracks and 'SaWaDiKa' not in tracks, 'Reviewed dual-chart subjects use existing route.'
    assert (tracks['SWIM']['previous_rank'], tracks['SWIM']['current_rank']) == (24, 20)
    assert (tracks['NORMAL']['previous_rank'], tracks['NORMAL']['current_rank']) == (123, 145)
    assert (tracks['APT.']['previous_rank'], tracks['APT.']['current_rank']) == (156, 139)
    assert result['mode'] == 'spotify_only_template' and result['ai_generated_now'] is False
    assert result['publication_approved'] is False
    assert result['evidence']['allowed_paid_ai_generation'] is False
    assert all(x['song_identity_review'] == 'PENDING' for x in tracks.values())
    assert 'YouTube' in result['article'] and '0으로' in result['article']
    try:
        make_spotify_only_preview([{'artist': 'LISA', 'track': 'SaWaDiKa'}], pair, root=ROOT)
    except SpotifyOnlyPreviewError:
        pass
    else:
        raise AssertionError('Reviewed-only selection should not become an unreviewed Spotify-only draft.')
    print('✅ Spotify 단독 검수 후보 SWIM·NORMAL·APT. 수치 확인')
    print('✅ Animal·SaWaDiKa 기존 승인 / Hootie Frutti 버전 보류 유지')
    print('✅ 무료 Template, AI 미호출, 신규 기사 미승인 상태 확인')

    # API wiring/JS markup static checks only. Avoid importing app or MySQL.
    routes = (ROOT/'news/news_routes.py').read_text(encoding='utf-8')
    js = (ROOT/'static/news_panel.js').read_text(encoding='utf-8')
    html = (ROOT/'templates/index.html').read_text(encoding='utf-8')
    assert routes.count("@router.get('/spotify-only-preview')") == 1
    assert js.count("'/api/news/spotify-only-preview' + weekQuery") == 1
    assert html.count('id="news-spotify-only-preview-btn"') == 1
    assert not list(x for x in (ROOT/'news').glob('*.py') if 'step17_temp' in x.name)
    print('✅ FastAPI URL · 버튼 · JavaScript 연결 코드 확인')
    print('⚠ 실제 MySQL·브라우저·OpenAI 유료 호출은 수행하지 않았어')


if __name__ == '__main__':
    try:
        check()
    except (AssertionError, ValueError, OSError) as exc:
        print('❌ STEP17A 검증 실패:', exc)
        sys.exit(1)
