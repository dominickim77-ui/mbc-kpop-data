"""STEP 17B safe, one-time installer. Run from mbc-kpop-data project root."""
from __future__ import annotations

import argparse
import ast
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATCH = Path(__file__).resolve().parent
EXPECTED_HEAD_BLOBS = {
    'app.py': '23bd9a575e69b1a5dc4f0a6791dc813c5ebf62cb',
    'templates/index.html': '934ff9bde0759df7dc4ded35fa1a93e666e0582b',
}
NEW_FILES = {
    'news/youtube_video_review_step17b.py': 'youtube_video_review_step17b.py',
    'static/youtube_video_review_step17b.js': 'youtube_video_review_step17b.js',
    'static/youtube_video_review_step17b.css': 'youtube_video_review_step17b.css',
}
MARKER = 'KPOP_YOUTUBE_VIDEO_HUMAN_REVIEW_STEP17B'


def replace_exact(body: str, before: str, after: str, label: str) -> str:
    count = body.count(before)
    if count != 1:
        raise ValueError(f'{label}: 예상한 코드 위치가 {count}개 발견됐어. 변경 없이 중단해.')
    return body.replace(before, after, 1)


def patch_app(body: str) -> str:
    if MARKER in body:
        raise ValueError('STEP 17B가 이미 적용된 app.py야.')
    body = replace_exact(body, 'app.include_router(news_router)\n',
                         'app.include_router(news_router)\n'
                         'from news.youtube_video_review_step17b import router as youtube_identity_router\n'
                         'app.include_router(youtube_identity_router)  # '+MARKER+'\n',
                         'YouTube 검수 API 등록')
    body = replace_exact(body, '        JOIN youtube_stats AS y\n',
                         '        LEFT JOIN youtube_stats AS y\n', '새 곡에 YouTube 통계가 없는 경우 처리')
    body = replace_exact(body, '    dashboard_data = cursor.fetchall()\n',
                         '    dashboard_data = cursor.fetchall()\n'
                         '    from news.youtube_video_review_step17b import video_review_status\n'
                         '    for _record in dashboard_data:\n'
                         '        _record["youtube_review_status"] = video_review_status(\n'
                         '            int(_record["song_id"]), _record.get("youtube_video_id"))\n',
                         '기존 영상 검수 상태 표시')
    # There are two dashboard sorting locations. None cannot be compared to ints.
    target = 'key=lambda item: item["youtube_views"],'
    if body.count(target) != 2:
        raise ValueError('YouTube 정렬 위치가 기존 코드와 달라. 변경하지 않아.')
    body = body.replace(target, 'key=lambda item: int(item.get("youtube_views") or -1),')
    # Secondary /youtube listing must exclude not-yet-linked songs to avoid None formatting.
    body = replace_exact(body,
                         '    youtube_data = sorted(\n        dashboard_data,\n',
                         '    youtube_data = sorted(\n        [item for item in dashboard_data if item.get("youtube_video_id")],\n',
                         '보조 YouTube 페이지의 누락 영상 보호')
    start_anchor = '            # --------------------------------------------------\n            # YouTube 검색\n'
    end_anchor = '            # --------------------------------------------------\n            # Current Analysis에 곡 추가\n'
    start = body.find(start_anchor)
    end = body.find(end_anchor, start + len(start_anchor))
    if start < 0 or end < 0 or body.count(start_anchor) != 1 or body.count(end_anchor) != 1:
        raise ValueError('기존 YouTube 자동 연결 코드를 찾지 못했어. 덮어쓰지 않고 중단해.')
    replacement = (
        '            # ' + MARKER + '\n'
        '            # A search hit cannot prove official video identity.\n'
        '            # Spotify chart/track writes remain unchanged. YouTube is PENDING.\n'
        '            # The operator searches/approves candidates separately in YouTube Data.\n'
        '            messages.append(\n'
        '                f"{artist} - {track}: YouTube 영상은 아직 검수 전이야. "\n'
        '                "YouTube Data에서 후보를 직접 확인해 줘."\n'
        '            )\n\n'
    )
    body = body[:start] + replacement + body[end:]
    ast.parse(body)
    return body


def patch_html(body: str) -> str:
    if MARKER in body:
        raise ValueError('STEP 17B가 이미 적용된 index.html이야.')
    body = replace_exact(body, '</head>',
                         '<link rel="stylesheet" href="/static/youtube_video_review_step17b.css">\n</head>',
                         'YouTube 검수 스타일 연결')
    body = replace_exact(body, '                        <th>Channel</th>',
                         '                        <th>Channel</th>\n                        <th>영상 확인</th>',
                         'YouTube 표 검수 열')
    for key in ('youtube_views', 'youtube_likes', 'youtube_comments'):
        before = '{{ "{:,}".format(\n                            item.' + key + '\n                            ) }}'
        after = '{{ "{:,}".format(item.' + key + ') if item.' + key + ' is not none else "—" }}'
        body = replace_exact(body, before, after, key + ' 누락 표시')
    body = replace_exact(body, '{{ item.youtube_channel }}',
                         '{{ item.youtube_channel or "—" }}', '기존 YouTube 채널 표시')
    section_marker = '<!-- STEP12 · CURRENT SELECTION, VERIFIED GLOBAL WEEKLY CSV -->'
    position = body.find(section_marker)
    if position < 0:
        raise ValueError('YouTube 섹션 끝부분 위치를 찾지 못했어.')
    old_section_end = body.rfind('</section>', 0, position)
    if old_section_end < 0:
        raise ValueError('YouTube 섹션 종료 태그를 찾지 못했어.')
    # Only work inside the actual YouTube section, to avoid changing unrelated tables.
    start_youtube = body.rfind('<h2>▶ YouTube Data</h2>', 0, old_section_end)
    if start_youtube < 0 or body.find('<h2>▶ YouTube Data</h2>', old_section_end, position) >= 0:
        raise ValueError('YouTube Data 섹션 위치가 기존 코드와 달라.')
    prefix, suffix = body[:old_section_end], body[old_section_end:]
    before_end = '                    {% endfor %}\n\n                </tbody>\n\n            </table>'
    if prefix[start_youtube:].count(before_end) != 1:
        raise ValueError('YouTube 테이블 내용을 찾지 못했어.')
    status_cell = '''                        <td>
                            {% if item.youtube_review_status == 'MANUALLY_APPROVED' %}
                            ✅ 확인한 영상
                            {% elif item.youtube_video_id %}
                            ⚠ 기존 자동 연결 · 미검수
                            {% else %}
                            검수 대기
                            {% endif %}
                        </td>
'''
    # Only target the YouTube subsection, rather than all tables on the page.
    tbody_start = prefix.rfind('<tbody>', start_youtube)
    if tbody_start < 0:
        raise ValueError('YouTube 데이터 행을 찾지 못했어.')
    row_end = prefix.find('                    </tr>', tbody_start)
    if row_end < 0 or row_end > len(prefix):
        raise ValueError('YouTube 데이터 행의 종료를 찾지 못했어.')
    prefix = prefix[:row_end] + status_cell + prefix[row_end:]
    widget = '''
        <!-- KPOP_YOUTUBE_VIDEO_HUMAN_REVIEW_STEP17B -->
        <div id="youtube-review-step17b" data-week-end="{{ selected_week_end }}">
            <h3>🔍 YouTube 영상 ID · 공식 채널 검수</h3>
            <p>기존 자동 검색 영상은 공식 MV로 승인된 것이 아니야. 새로 추가한 곡은 YouTube 연결을 보류해. 직접 확인한 영상만 승인·기록할 수 있어.</p>
            <p class="yt17-warning">영상 후보 조회 시 YouTube Data API 할당량이 사용돼. 이 영상의 누적 조회수는 YouTube Global Weekly Top Songs의 주간 조회수가 아니야.</p>
            <div class="yt17-toolbar">
                <label for="yt17-song">검수할 곡</label>
                <select id="yt17-song" aria-label="YouTube 영상 후보를 확인할 선택곡">
                    {% for item in current_analysis %}
                    <option value="{{ item.song_id }}">{{ item.artist }} — {{ item.track }}</option>
                    {% endfor %}
                </select>
                <button type="button" id="yt17-search" {% if not current_analysis %}disabled{% endif %}>영상 후보 확인 (API 할당량 사용)</button>
            </div>
            <p id="yt17-status" role="status" aria-live="polite">자동 승인 없음. 공식 채널·곡 버전을 직접 확인하기 전에는 저장하지 않아.</p>
            <div id="yt17-candidates" hidden></div>
        </div>
'''
    body = prefix + widget + suffix
    body = replace_exact(body, '</body>',
                         '<script src="/static/youtube_video_review_step17b.js" defer></script>\n</body>',
                         'YouTube 후보 검수 JavaScript 연결')
    if MARKER not in body:
        raise ValueError('YouTube UI 검수 표식이 누락됐어.')
    return body


def git(*args: str) -> str:
    result = subprocess.run(['git', *args], cwd=ROOT, text=True, capture_output=True, check=True)
    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description='STEP 17B YouTube 영상 ID 수동 검수 설치')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    try:
        if not (ROOT / '.git').is_dir():
            raise ValueError('Git 저장소의 프로젝트 루트에서 실행해 줘.')
        branch = git('branch', '--show-current')
        if branch != 'feature/kpop-news-analysis':
            raise ValueError(f'현재 브랜치가 {branch!r}야. feature/kpop-news-analysis에서 설치해 줘.')
        for path, sha in EXPECTED_HEAD_BLOBS.items():
            if git('rev-parse', f'HEAD:{path}') != sha:
                raise ValueError(f'{path}: 현재 코드 버전이 예상과 달라. 최신 파일 검토 전 설치를 중단해.')
            if git('status', '--porcelain', '--', path):
                raise ValueError(f'{path}: 커밋하지 않은 변경이 있어. 먼저 확인해 줘.')
        for destination in NEW_FILES:
            if (ROOT / destination).exists():
                raise ValueError(f'{destination}: 파일이 이미 있어 덮어쓰지 않을게.')
        app_text = (ROOT / 'app.py').read_text(encoding='utf-8')
        html_text = (ROOT / 'templates/index.html').read_text(encoding='utf-8')
        new_app = patch_app(app_text)
        new_html = patch_html(html_text)
        print('✅ 기존 STEP 17A 코드 확인 · 자동 YouTube 첫 결과 저장 제거 가능')
        print('✅ 새 곡도 YouTube 승인 전 Current Analysis에 남도록 LEFT JOIN 준비')
        print('✅ YouTube 후보 조회·명시적 승인 UI 및 기존 데이터 구분 준비')
        if args.dry_run:
            print('✅ DRY RUN 통과: 파일은 변경하지 않았어.')
            return 0
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup = ROOT.parent / f'mbc-kpop-step17b-backup_{stamp}'
        if backup.exists():
            raise ValueError('백업 경로가 이미 있어. 잠시 후 다시 실행해 줘.')
        backup.mkdir(parents=True)
        for rel in EXPECTED_HEAD_BLOBS:
            target = backup / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, target)
        created = []
        try:
            (ROOT / 'app.py').write_text(new_app, encoding='utf-8')
            (ROOT / 'templates/index.html').write_text(new_html, encoding='utf-8')
            for rel, source in NEW_FILES.items():
                path = ROOT / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open('x', encoding='utf-8') as f:
                    f.write((PATCH / source).read_text(encoding='utf-8'))
                created.append(path)
        except Exception:
            for rel in EXPECTED_HEAD_BLOBS:
                shutil.copy2(backup / rel, ROOT / rel)
            for path in created:
                path.unlink(missing_ok=True)
            raise
        print('✅ STEP 17B 패치 설치 완료 · 기존 파일 2개 자동 백업')
        print('백업:', backup)
        print('추가: YouTube 영상 후보 API, 사용자 승인 기록, 화면 JavaScript/CSS')
        print('실행: python kpop_step17b_patch\\verify_step17b.py')
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError, SyntaxError) as exc:
        print('❌ 설치 중단:', exc)
        return 1


if __name__ == '__main__':
    sys.exit(main())
