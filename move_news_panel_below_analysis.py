"""Move the existing K-POP NEWS ANALYSIS panel below Accumulated Analysis.

Usage (run from C:\\WORKSPACE\\mbc-kpop-data):
    python move_news_panel_below_analysis.py

Only templates/index.html is changed; an adjacent timestamped backup is made.
"""
from datetime import datetime
from pathlib import Path
import sys

root = Path.cwd()
html_path = root / 'templates' / 'index.html'
if not html_path.is_file():
    sys.exit('중단: 프로젝트 최상위 폴더에서 실행하세요 (templates/index.html 없음).')

html = html_path.read_text(encoding='utf-8-sig')
start_marker = '<!-- KPOP_NEWS_INLINE_V1 -->'
section_marker = '<section id="news-inline-panel"'
script_marker = '<script src="/static/news_panel.js" defer></script>'
analysis_marker = '<h2>📈 Accumulated Analysis</h2>'
main_end_marker = '</main>'

for marker in (start_marker, section_marker, script_marker, analysis_marker, main_end_marker):
    if html.count(marker) != 1:
        sys.exit(f'중단: 예상된 HTML 구조가 다릅니다. 확인 필요: {marker} (발견 {html.count(marker)}개)')

panel_start = html.index(start_marker)
panel_end = html.index(script_marker, panel_start) + len(script_marker)
analysis_pos = html.index(analysis_marker)
main_end = html.index(main_end_marker)

if panel_start > analysis_pos:
    print('이미 NEWS ANALYSIS가 Accumulated Analysis 뒤에 있습니다. 변경하지 않았습니다.')
    sys.exit(0)
if not (panel_start < panel_end < analysis_pos < main_end):
    sys.exit('중단: 배치 순서가 예상과 다릅니다. 파일을 변경하지 않았습니다.')

panel = html[panel_start:panel_end].strip()
without = html[:panel_start] + html[panel_end:]
new_main_end = without.index(main_end_marker)
# The Accumulated Analysis section is the final section of the main dashboard.
last_section_end = without.rfind('</section>', 0, new_main_end)
if last_section_end < without.index(analysis_marker):
    sys.exit('중단: Accumulated Analysis 종료 지점을 찾지 못했습니다.')

new_html = (without[:new_main_end].rstrip() + '\n\n        ' + panel + '\n\n    ' + without[new_main_end:])
if (new_html.count(section_marker) != 1 or new_html.count(script_marker) != 1
        or not (new_html.index(analysis_marker) < new_html.index(section_marker) < new_html.index(main_end_marker))):
    sys.exit('중단: 이동 후 구조 검증 실패. 파일을 변경하지 않았습니다.')

backup = root / 'templates' / ('index_before_news_move_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '.html.bak')
if backup.exists():
    sys.exit('중단: 같은 이름의 백업 파일이 이미 있습니다.')
backup.write_bytes(html_path.read_bytes())
html_path.write_text(new_html, encoding='utf-8')
print('✅ NEWS ANALYSIS 패널 이동 완료')
print('순서: Artist Search → Current Analysis → Spotify Data → YouTube Data → Compare → Accumulated Analysis → NEWS ANALYSIS')
print('변경 파일: templates/index.html')
print('백업:', backup.relative_to(root))
print('브라우저에서 Ctrl + F5로 새로고침하고 하단 위치를 확인하세요.')
