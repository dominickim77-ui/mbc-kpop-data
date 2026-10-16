"""Install STEP 11 safely in the EXISTING mbc-kpop-data project.

Run from C:\\WORKSPACE\\mbc-kpop-data:
  python kpop_step11_patch\\install_step11.py

- Preserve the current selection + original app.py
- Back up all changed files in a separate adjacent directory
- Keep old news generation available for archived articles
- Disallow second application and unexpected HTML layouts
"""
from __future__ import annotations
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path.cwd()
ASSETS = Path(__file__).resolve().parent
STEP_MARKER = 'KPOP_NEWS_SELECTED_STEP11'

files = {
    'templates/index.html': ROOT / 'templates/index.html',
    'templates/compare.html': ROOT / 'templates/compare.html',
    'static/style.css': ROOT / 'static/style.css',
    'static/news_panel.js': ROOT / 'static/news_panel.js',
    'news/news_routes.py': ROOT / 'news/news_routes.py',
}
required = list(files.values()) + [ROOT / 'app.py', ROOT / 'news/generation.py', ROOT / 'facts/article_ready_fact_sheet_20261008.json']
missing = [str(p.relative_to(ROOT)) for p in required if not p.is_file()]
if missing:
    sys.exit('설치 중단: 필요한 파일이 없습니다: ' + ', '.join(missing))

html = files['templates/index.html'].read_text(encoding='utf-8-sig')
compare = files['templates/compare.html'].read_text(encoding='utf-8-sig')
css = files['static/style.css'].read_text(encoding='utf-8-sig')
if STEP_MARKER in html:
    print('STEP 11 패치가 이미 설치되어 있어. 중복 적용하지 않았어.')
    sys.exit(0)
if html.count('<section id="news-inline-panel"') != 1 or html.count('📈 Accumulated Analysis') != 1:
    sys.exit('설치 중단: 기존 뉴스 패널 또는 Accumulated Analysis 구조가 예상과 달라.')
if not (html.index('📈 Accumulated Analysis') < html.index('<section id="news-inline-panel"')):
    sys.exit('설치 중단: 뉴스 패널이 Accumulated Analysis 아래에 있지 않아. 우선 위치를 이동해 줘.')
if html.count('<h2>📊 Compare</h2>') != 1:
    sys.exit('설치 중단: 기존 Compare 영역을 찾지 못했어.')
if html.count('<script src="/static/news_panel.js" defer></script>') != 1:
    sys.exit('설치 중단: 뉴스 JavaScript 파일 위치가 중복되거나 누락됐어.')
if html.count('const spotifyStreams') != 1 or html.count('const youtubeViews') != 1:
    sys.exit('설치 중단: 기존 그래프 코드와 구조가 달라 자동 수정하지 않았어.')

# Isolate existing panel section only; preserve its location and outer <main>.
start = html.index('<section id="news-inline-panel"')
end = html.find('</section>', start)
if end < 0: sys.exit('설치 중단: 뉴스 패널 종료 태그 없음')
end += len('</section>')
news_frag = (ASSETS / 'news_panel_fragment.html').read_text(encoding='utf-8').strip()
html = html[:start] + news_frag + html[end:]

# Legacy dashboard comparison: do NOT show meaningless numeric differences or ratios.
start_h = html.index('<h2>📊 Compare</h2>')
start_s = html.rfind('<section class="dashboard-section">', 0, start_h)
end_s = html.find('</section>', start_h)
if start_s < 0 or end_s < 0: sys.exit('설치 중단: Compare 범위 확인 실패')
end_s += len('</section>')
new_compare = '''<section class="dashboard-section">
  <h2>📊 Compare — 서로 다른 지표는 별도로 확인</h2>
  <div class="notice">
    아래 자료는 <strong>10/01 종료 주간 Spotify 재생수</strong>와
    <strong>개별 YouTube 영상 누적 조회수</strong>야.
    집계 기간·대상이 달라 차이(Difference)·배율(Ratio)·우위(Larger)를 계산하지 않아.
    기사에 사용할 공식 YouTube 주간 Top Songs 값은 아래 NEWS ANALYSIS의 검증된 Fact Sheet에서 확인해.
  </div>
  <table>
    <thead><tr><th>Artist</th><th>Track</th><th>Spotify 주간 Streams (10/01)</th><th>YouTube 영상 누적 Views</th></tr></thead>
    <tbody>
    {% for item in comparison_data %}
      <tr><td>{{ item.artist }}</td><td>{{ item.track }}</td>
      <td>{{ "{:,}".format(item.spotify_streams) }}</td>
      <td>{{ "{:,}".format(item.youtube_views) }}</td></tr>
    {% endfor %}
    </tbody>
  </table>
</section>'''
html = html[:start_s] + new_compare + html[end_s:]

# Two entirely independent charts (no common axis between unlike measures).
start_h = html.index('<h2>📈 Accumulated Analysis</h2>')
start_s = html.rfind('<section class="dashboard-section">', 0, start_h)
end_s = html.find('</section>', start_h)
if start_s < 0 or end_s < 0: sys.exit('설치 중단: Accumulated Analysis 범위 확인 실패')
end_s += len('</section>')
chart_section = '''<section class="dashboard-section">
  <h2>📈 Accumulated Analysis — 지표별 시각화</h2>
  <p>선택한 곡의 주간 스트리밍과 영상 누적 조회수를 <strong>각각 다른 그래프</strong>로 표시해.</p>
  <div class="notice">주의: 기존 대시보드의 Spotify는 10/01 주간, YouTube는 개별 영상의 조회 시점까지 누적 데이터야.
  서로 같은 기간의 소비량을 의미하지 않아. 아래 두 그래프의 길이를 가로질러 비교하지 마.</div>
  {% if comparison_data %}
  <script id="chartLabels" type="application/json">{{ chart_labels | tojson }}</script>
  <script id="chartSpotify" type="application/json">{{ chart_spotify | tojson }}</script>
  <script id="chartYoutube" type="application/json">{{ chart_youtube | tojson }}</script>
  <div class="analysis-two-charts">
    <div class="analysis-chart-standalone"><h3>Spotify — 10/01 종료 주간 스트리밍</h3><div class="chart-container"><canvas id="spotifyWeeklyChart"></canvas></div></div>
    <div class="analysis-chart-standalone"><h3>YouTube — 개별 영상의 누적 조회수</h3><div class="chart-container"><canvas id="youtubeCumulativeChart"></canvas></div></div>
  </div>
  <p class="analysis-chart-hint">기사 생성은 위 그래프가 아니라 2주간의 공식 주간 차트로 작성한 검수 완료 Fact Sheet를 사용해.</p>
  {% else %}
  <p>차트를 보려면 Artist Search에서 분석할 곡을 추가해 줘.</p>
  {% endif %}
</section>'''
html = html[:start_s] + chart_section + html[end_s:]

# Replace only the existing two-series Chart.js inline script.
chartjs = '<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>'
p = html.find(chartjs)
if p < 0: sys.exit('설치 중단: Chart.js 로딩 위치 없음')
script_start = html.find('<script>', p)
script_end = html.find('</script>', script_start)
if script_start < 0 or script_end < 0 or 'const spotifyStreams' not in html[script_start:script_end]:
    sys.exit('설치 중단: 기존 Chart.js 렌더링 코드 확인 실패')
script_end += len('</script>')
js = '''<script>
  const chartLabels = JSON.parse(document.getElementById('chartLabels').textContent.trim());
  const spotifyWeekly = JSON.parse(document.getElementById('chartSpotify').textContent.trim());
  const youtubeLifetime = JSON.parse(document.getElementById('chartYoutube').textContent.trim());
  function drawSeparateChart(canvasId, label, values) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || typeof Chart === 'undefined') return;
    new Chart(canvas, {
      type:'bar',
      data:{labels:chartLabels,datasets:[{label:label,data:values}]},
      options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,
        plugins:{legend:{display:false},tooltip:{callbacks:{label:(ctx)=>label+': '+Number(ctx.raw).toLocaleString()}}},
        scales:{x:{beginAtZero:true,title:{display:true,text:label}},y:{title:{display:true,text:'Artist / Track'}}}}
    });
  }
  drawSeparateChart('spotifyWeeklyChart','Spotify Weekly Streams',spotifyWeekly);
  drawSeparateChart('youtubeCumulativeChart','YouTube Video Lifetime Views',youtubeLifetime);
</script>'''
html = html[:script_start] + js + html[script_end:]

compare_new = '''<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ title }}</title><link rel="stylesheet" href="/static/style.css"></head><body>
<header><h1>📊 Compare — 지표별 참조</h1><p>같은 기간이 아닌 자료는 배율을 계산하지 않아</p></header>
<main class="data-page"><a class="back-link" href="/">← HOME</a>
<div class="notice">Spotify는 10/01 종료 주간 스트리밍, YouTube는 개별 영상의 누적 조회수야. 서로 나누거나 뺄 수 없어.</div>
<table><thead><tr><th>Artist</th><th>Track</th><th>Spotify Rank</th><th>Spotify Weekly Streams</th><th>YouTube Video Lifetime Views</th></tr></thead>
<tbody>{% for item in comparisons %}<tr><td>{{ item.artist }}</td><td>{{ item.track }}</td>
<td>#{{ item.spotify_rank }}</td><td>{{ "{:,}".format(item.spotify_streams) }}</td>
<td>{{ "{:,}".format(item.youtube_views) }}</td></tr>{% endfor %}</tbody></table>
</main></body></html>'''

css_new = css + '\n/* STEP11 */\n' + (ASSETS / 'news_panel_extra.css').read_text(encoding='utf-8')
if (html.count('<section id="news-inline-panel"') != 1 or html.count('id="chartLabels"') != 1 or html.count("getElementById('chartLabels')") != 1):
    sys.exit('설치 중단: HTML 재검증 실패 (뉴스 패널 또는 차트 데이터 중복)')
if not (html.index('Accumulated Analysis') < html.index('news-inline-panel') < html.index('</main>')):
    sys.exit('설치 중단: NEWS 위치가 Accumulated Analysis 다음이 아니야')
if 'KPOP_NEWS_SELECTED_STEP11' not in html or 'id="news-preview-btn"' not in html:
    sys.exit('설치 중단: 뉴스 패널 변경 검증 실패')

changes = {
    files['templates/index.html']: html,
    files['templates/compare.html']: compare_new,
    files['static/style.css']: css_new,
    files['static/news_panel.js']: (ASSETS / 'news_panel.js').read_text(encoding='utf-8'),
    files['news/news_routes.py']: (ASSETS / 'news_routes.py').read_text(encoding='utf-8'),
}
new_module = ROOT / 'news' / 'selected_news.py'
if new_module.exists():
    sys.exit('설치 중단: news/selected_news.py가 이미 있어. 덮어쓰지 않을게.')

stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
backup = ROOT.parent / (ROOT.name + '_step11_backup_' + stamp)
if backup.exists():
    sys.exit('설치 중단: 백업 이름 중복')
backup.mkdir(parents=True)
for p in changes:
    dest = backup / p.relative_to(ROOT)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(p, dest)
try:
    shutil.copy2(ASSETS / 'selected_news.py', new_module)
    for p, content in changes.items():
        p.write_text(content, encoding='utf-8')
except Exception as e:
    for p in changes:
        shutil.copy2(backup / p.relative_to(ROOT), p)
    new_module.unlink(missing_ok=True)
    sys.exit(f'설치 실패: 원본 복구 완료 ({type(e).__name__})')

print('✅ STEP 11: Current Analysis 선택 기반 기사 생성 연결 완료')
print('✅ Compare의 숫자 차이/비율 제거, 지표별 그래프 분리')
print('✅ 기존 app.py 및 뉴스 기사 파일 변경 없음')
print('백업:', backup)
print('다음: python -m py_compile news/selected_news.py news/news_routes.py app.py')
print('서버 재시작: python -m uvicorn app:app --host 127.0.0.1 --port 8000')
