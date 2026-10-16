"""STEP11 free offline verification. Run in the mbc-kpop-data project root."""
import ast
import sys
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

root = Path.cwd()
sys.path.insert(0, str(root))
files = ['app.py','news/news_routes.py','news/selected_news.py','news/generation.py',
         'templates/index.html','templates/compare.html','static/news_panel.js',
         'facts/article_ready_fact_sheet_20261008.json']
missing=[p for p in files if not (root/p).is_file()]
if missing: sys.exit('검사 실패: 파일 누락 ' + ', '.join(missing))
for name in ['app.py','news/news_routes.py','news/selected_news.py','news/generation.py']:
    ast.parse((root/name).read_text(encoding='utf-8-sig'), filename=name)
for name in ['index.html','compare.html']:
    Environment(loader=FileSystemLoader(root/'templates')).get_template(name)
text = (root/'templates/index.html').read_text(encoding='utf-8')
assert text.index('Accumulated Analysis') < text.index('news-inline-panel') < text.index('</main>')
assert text.count('id="news-inline-panel"') == 1
assert text.count('id="spotifyWeeklyChart"') == 1 and text.count('id="youtubeCumulativeChart"') == 1
assert 'item.ratio' not in text and 'item.larger_value' not in text and 'item.difference' not in text
from news.selected_news import load_verified_facts, selected_snapshot, evidence_for_selected
facts=load_verified_facts()
s=selected_snapshot([{'artist':'BTS','track':'SWIM'}, {'artist':'LISA','track':'SaWaDiKa'}], facts)
assert s['can_generate'] and len(s['approved_tracks'])==1 and s['approved_tracks'][0]['track_name']=='SaWaDiKa'
assert len(s['excluded_tracks'])==1
assert len(evidence_for_selected(facts,s)['analysis_tracks'])==1
print('✅ STEP11 Python · HTML · Fact Sheet · 곡 검수 필터 검사 통과')
print('✅ 예시: BTS(SWIM) 검수 대기 / LISA(SaWaDiKa) 기사 대상')
print('✅ 실제 API 호출·MySQL 조회·과금 없음')
print('다음: 웹사이트 서버 재시작 후 무료 미리보기 테스트')
