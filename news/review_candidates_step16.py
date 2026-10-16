"""STEP16 · Human-review candidate sheet for the *currently selected* chart songs.

READ-ONLY: Spotify/YouTube weekly CSVs, editorially approved 10/08 Fact Sheet.
No API calls, MySQL mutation, auto-K-POP classification, or new approvals.
A chart's missing row is unknown outside that chart's Top N, NEVER 0 plays.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from news.chart_data_manager import WeekPair, choose_pair
from news.weekly_chart_analysis import build_weekly_rows, song_key

ROOT = Path(__file__).resolve().parent.parent


class ReviewQueueError(ValueError):
    pass


def _checked_source_links(root: Path, relpath: str, platform: str) -> dict:
    """Unambiguous chart-row source refs; YouTube URL is a *representative video*, not weekly views."""
    source = root / relpath
    is_spotify = platform == 'spotify'
    key_artist = 'artist_names' if is_spotify else 'Artist Names'
    key_track = 'track_name' if is_spotify else 'Track Name'
    key_url = 'uri' if is_spotify else 'YouTube URL'
    items: dict = {}
    with source.open('r', encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if not {key_artist, key_track, key_url}.issubset(reader.fieldnames or []):
            raise ReviewQueueError(f'{relpath}: 추적 URL 컬럼이 없어 출처 검토 불가')
        for row in reader:
            key = song_key(row[key_artist], row[key_track])
            ref = row[key_url].strip()
            if is_spotify:
                # Accept only Spotify URI track IDs, never generic user-controlled URL.
                if ref.startswith('spotify:track:') and len(ref.split(':')[-1]) == 22:
                    ref = 'https://open.spotify.com/track/' + ref.split(':')[-1]
                else:
                    ref = ''
            else:
                u = urlparse(ref)
                if u.scheme != 'https' or u.netloc not in ('www.youtube.com', 'youtube.com') or u.path != '/watch':
                    ref = ''
            items.setdefault(key, []).append(ref)
    return {k: links[0] for k, links in items.items() if len(links) == 1}


def _candidate_status(row: dict) -> tuple[str, str]:
    code = row['review_code']
    if code == 'reviewed':
        return 'DUAL_CHART_REVIEWED', '기존 사람이 검수한 두 플랫폼 Fact Sheet와 원본 CSV를 대조했어. 기사 초안 가능, 출고 승인 아님.'
    if code == 'excluded':
        return 'HOLD_VERSION', '곡 버전 대응이 불명확해서 기사 주요 분석에서 제외했어.'
    if code == 'mismatch':
        return 'HOLD_FACT_MISMATCH', '기존 Fact Sheet와 CSV 값이 달라서 새 기사 작성을 중단해야 해.'
    if code == 'ambiguous':
        return 'HOLD_AMBIGUOUS', '동일 이름·아티스트의 복수 기록이 있어 정확한 버전 식별이 필요해.'
    full_sp = row['spotify_prev'] is not None and row['spotify_current'] is not None
    full_yt = row['youtube_prev'] is not None and row['youtube_current'] is not None
    if full_sp and full_yt:
        return 'DUAL_CHART_REVIEW_PENDING', '두 주간 양쪽 차트 수치는 있어. 곡 버전·아티스트·분류·출처를 사람이 검수해야 해.'
    if full_sp and not full_yt:
        return 'SPOTIFY_ONLY_REVIEW_PENDING', 'Spotify 주간 추세는 분석 후보. YouTube Top 100에 완전한 2주 기록이 없어 교차 플랫폼 기사는 보류.'
    if full_yt and not full_sp:
        return 'YOUTUBE_ONLY_REVIEW_PENDING', 'YouTube 주간 추세는 분석 후보. Spotify Top 200에 완전한 2주 기록이 없어 교차 플랫폼 기사는 보류.'
    return 'INSUFFICIENT_OBSERVATIONS', '같은 지표의 연속 2주 기록이 부족해 변화율·추세를 단정할 수 없어.'


def build_review_queue(selected: list[dict], pair: WeekPair, root: Path = ROOT) -> dict:
    """Read validated rows, return evidence and review tasks. Never authorize new songs."""
    root = Path(root)
    rows = build_weekly_rows(selected, root=root, pair=pair)
    spotify_links = _checked_source_links(root, pair.spotify_current, 'spotify')
    youtube_links = _checked_source_links(root, pair.youtube_current, 'youtube')
    candidates = []
    for row in rows:
        key = song_key(row['artist'], row['track'])
        status, guidance = _candidate_status(row)
        candidates.append({
            'artist': row['artist'], 'track': row['track'],
            'review_status': status, 'review_note': guidance,
            'editorial_category': 'HUMAN_REVIEW_REQUIRED' if status != 'DUAL_CHART_REVIEWED' else 'EXISTING_REVIEWED_FACT_SHEET',
            'eligible_for_current_dual_chart_article': status == 'DUAL_CHART_REVIEWED',
            'spotify': {
                'previous_rank': row['spotify_prev_rank'], 'current_rank': row['spotify_curr_rank'],
                'previous_week_streams': row['spotify_prev'], 'current_week_streams': row['spotify_current'],
                'change_pct': row['spotify_pct'], 'chart_track_link': spotify_links.get(key, ''),
            },
            'youtube': {
                'previous_rank': row['youtube_prev_rank'], 'current_rank': row['youtube_curr_rank'],
                'previous_week_views': row['youtube_prev'], 'current_week_views': row['youtube_current'],
                'change_pct': row['youtube_pct'],
                'representative_video_link_only': youtube_links.get(key, ''),
            },
        })
    totals = {code: sum(item['review_status'] == code for item in candidates)
              for code in sorted({item['review_status'] for item in candidates})}
    return {
        'status': 'DRAFT_REVIEW_QUEUE_NOT_APPROVED',
        'publication_approved': False,
        'auto_approval': False,
        'region': 'Global',
        'comparison_period': {
            'previous_start': pair.previous_start.isoformat(), 'previous_end': pair.previous_end.isoformat(),
            'current_start': pair.current_start.isoformat(), 'current_end': pair.current_end.isoformat(),
        },
        'chart_scope': {'spotify': 'Top 200 songs', 'youtube': 'Top 100 songs'},
        'source_files': pair.files,
        'selected_count': len(candidates),
        'status_counts': totals,
        'candidates': candidates,
        'cautions': [
            'K-POP 분류와 곡 버전 매칭은 사람의 확인 전까지 승인하지 않는다.',
            'YouTube 주간 Top Songs 조회수는 단일 대표 영상의 누적 조회수가 아니다.',
            '차트에서 미확인된 곡은 소비량 0이 아니다.',
            'Spotify 스트리밍과 YouTube 조회수를 합산하거나 비율로 비교하지 않는다.',
            '새 주차에는 이전 Fact Sheet의 검수 승인을 이전하지 않는다.',
            '이 출력은 검수 후보표일 뿐 새로운 기사 작성 승인이나 출고 승인이 아니다.',
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='STEP 16 · 무료/읽기 전용 검수 후보표 생성')
    parser.add_argument('--week-end', default='', help='비교 종료 주차 YYYY-MM-DD, 생략 시 최신 유효 주차')
    parser.add_argument('--selected', action='append', default=[], metavar='ARTIST|TRACK',
                        help='곡 선택, 여러 번 사용 가능 (예: --selected "BTS|SWIM")')
    parser.add_argument('--from-current-analysis', action='store_true', help='로컬 MySQL 현재 선택곡 읽기')
    parser.add_argument('--export', action='store_true', help='검수 후보 JSON을 facts/에 보존 (기존 파일 덮어쓰기 금지)')
    args = parser.parse_args()
    if args.from_current_analysis and args.selected:
        parser.error('--selected와 --from-current-analysis는 함께 사용할 수 없어')
    try:
        pair, _, notes = choose_pair(root=ROOT, week_end=args.week_end)
        if pair is None:
            raise ReviewQueueError('검증된 연속 2주 차트가 없어')
        if args.from_current_analysis:
            from news.selected_news import read_current_selection
            selection = read_current_selection()
        else:
            selection = []
            for raw in (args.selected or ['BTS|SWIM', 'BTS|NORMAL', 'ROSÉ, Bruno Mars|APT.', 'LISA|SaWaDiKa']):
                if '|' not in raw:
                    raise ReviewQueueError('--selected는 ARTIST|TRACK 형식이어야 해')
                a, t = raw.split('|', 1)
                if not a.strip() or not t.strip():
                    raise ReviewQueueError('아티스트·곡명을 입력해 줘')
                selection.append({'artist': a.strip(), 'track': t.strip()})
        result = build_review_queue(selection, pair, root=ROOT)
        print(f'✅ STEP 16 · {pair.current_end} 주차 검수 후보 {result["selected_count"]}곡')
        for row in result['candidates']:
            print(f' - {row["artist"]} — {row["track"]}: {row["review_status"]}')
        for note in notes:
            print('ℹ', note)
        if args.export:
            filename = f'step16_review_queue_{pair.current_end:%Y%m%d}_{datetime.now(timezone.utc):%H%M%S%f}.json'
            target = ROOT / 'facts' / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('x', encoding='utf-8') as out:
                json.dump(result, out, ensure_ascii=False, indent=2)
            print('📄 보존:', target.relative_to(ROOT))
        print('⚠ 사람 검수가 끝나기 전에는 새 곡을 기사에 자동 포함하지 않아.')
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print('❌ 검수 후보 생성 실패:', exc)
        return 1


if __name__ == '__main__':
    import sys
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    raise SystemExit(main())
