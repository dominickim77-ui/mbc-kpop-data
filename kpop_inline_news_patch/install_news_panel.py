"""기존 프로젝트를 안전하게 확장: core 파일 백업, NEWS 버튼/라우터 추가.

사용: 프로젝트 최상위 폴더에서 python install_news_panel.py
같은 설치를 다시 실행하면 중복 적용하지 않습니다.
"""
from datetime import datetime
from pathlib import Path
import shutil
import sys

root = Path.cwd()
assets = Path(__file__).resolve().parent
app_path = root / 'app.py'
html_path = root / 'templates' / 'index.html'
css_path = root / 'static' / 'style.css'
required = [app_path, html_path, css_path, root / 'news' / 'generation.py', root / 'facts' / 'article_ready_fact_sheet_20261008.json']
missing = [str(p.relative_to(root)) for p in required if not p.is_file()]
if missing:
    sys.exit('중단: 필요한 파일이 없습니다: ' + ', '.join(missing))

app = app_path.read_text(encoding='utf-8-sig')
html = html_path.read_text(encoding='utf-8-sig')
css = css_path.read_text(encoding='utf-8-sig')

if 'KPOP_NEWS_INLINE_V1' in app and 'KPOP_NEWS_INLINE_V1' in html:
    print('이미 설치되어 있습니다. 변경하지 않았습니다.')
    sys.exit(0)
if 'KPOP_NEWS_INLINE_V1' in app or 'KPOP_NEWS_INLINE_V1' in html:
    sys.exit('중단: 부분 적용 상태입니다. 수동 검토가 필요합니다.')
if 'app = FastAPI()' not in app:
    sys.exit('중단: app.py에 예상한 FastAPI 설정이 없습니다.')
if '<main class="dashboard">' not in html:
    sys.exit('중단: index.html의 메인 위치를 찾지 못했습니다.')
if 'news-inline-panel' in html or "'/api/news/" in app:
    sys.exit('중단: 기존 뉴스 패널 또는 API가 이미 있어 중복 적용하지 않습니다.')

fragment = (assets / 'news_panel_fragment.html').read_text(encoding='utf-8')
styles = (assets / 'news_panel_styles.css').read_text(encoding='utf-8')
app_new = app.replace('app = FastAPI()', "app = FastAPI()\n\n# KPOP_NEWS_INLINE_V1: 새 뉴스 라우터만 추가 (기존 라우트 변경 없음)\nfrom news.news_routes import router as news_router\napp.include_router(news_router)", 1)
html_new = html.replace('<main class="dashboard">', '<main class="dashboard">\n\n        <!-- KPOP_NEWS_INLINE_V1 -->\n' + fragment, 1)
css_new = css + '\n/* KPOP_NEWS_INLINE_V1 */\n' + styles

out_news = root / 'news' / 'news_routes.py'
out_js = root / 'static' / 'news_panel.js'
if out_news.exists() or out_js.exists():
    sys.exit('중단: 설치 대상 뉴스 파일이 이미 있습니다. 덮어쓰지 않습니다.')

backup_dir = root.parent / (root.name + '_news_patch_backup_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
backup_dir.mkdir(parents=True, exist_ok=False)
for file, prefix in ((app_path,''),(html_path,'templates'),(css_path,'static')):
    target = backup_dir / prefix / file.name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(file, target)

# 필요한 파일을 배치한 후 기존 파일을 바꾼다.
shutil.copy2(assets / 'news' / 'news_routes.py', out_news)
shutil.copy2(assets / 'static' / 'news_panel.js', out_js)
app_path.write_text(app_new, encoding='utf-8')
html_path.write_text(html_new, encoding='utf-8')
css_path.write_text(css_new, encoding='utf-8')
print('✅ 동일 페이지 기사 생성 패널 설치 완료')
print('변경: app.py, templates/index.html, static/style.css')
print('추가: news/news_routes.py, static/news_panel.js')
print('백업:', backup_dir)
print('테스트: python -m py_compile app.py news/news_routes.py news/generation.py')
print('실행: python -m uvicorn app:app --host 127.0.0.1 --port 8000')
