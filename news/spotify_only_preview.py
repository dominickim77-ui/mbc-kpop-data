"""STEP 17A — Spotify-only candidate article preview (no AI, no approval).

Reads only verified-format official weekly Spotify CSV rows via the existing
STEP 13/16 chart logic. This is a review aid, NOT editorial approval, and
never uses cumulative YouTube video views from the legacy dashboard.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from news.chart_data_manager import WeekPair
from news.review_candidates_step16 import build_review_queue
from news.weekly_chart_analysis import normalize

from security.preview_data import data_root
ROOT = data_root()


class SpotifyOnlyPreviewError(ValueError):
    pass


def make_spotify_only_preview(selected: list[dict], pair: WeekPair, root: Path = ROOT) -> dict:
    """Return free fixed text and a traceable review-only Fact Sheet."""
    report = build_review_queue(selected, pair, root=Path(root))
    # Exclude previous reviewed dual-chart subjects (served by existing route),
    # and every ambiguous/version/fact-mismatch subject. Unreviewed candidates
    # may be previewed but never marked approved or sent to the paid API.
    allowed_statuses = {'SPOTIFY_ONLY_REVIEW_PENDING', 'DUAL_CHART_REVIEW_PENDING'}
    items = []
    for cand in report['candidates']:
        if normalize(cand['track']) == 'hootie frutti':
            continue  # human-confirmed version discrepancy; never auto-include
        if cand['review_status'] not in allowed_statuses:
            continue
        sp = cand['spotify']
        values = [sp['previous_rank'], sp['current_rank'], sp['previous_week_streams'], sp['current_week_streams']]
        if any(type(v) is not int or v <= 0 for v in values):
            continue
        # The csv-backed review report has already checked chart row integrity.
        if sp['change_pct'] is None:
            continue
        pct = round((sp['current_week_streams'] - sp['previous_week_streams']) /
                    sp['previous_week_streams'] * 100, 2)
        if abs(pct - sp['change_pct']) > .015:
            raise SpotifyOnlyPreviewError('Spotify 변화율이 원본 CSV 계산과 다릅니다.')
        items.append({
            'artist': cand['artist'], 'track': cand['track'],
            'source_track_link': sp['chart_track_link'],
            'previous_rank': sp['previous_rank'], 'current_rank': sp['current_rank'],
            'previous_week_streams': sp['previous_week_streams'],
            'current_week_streams': sp['current_week_streams'],
            'streams_change_pct': pct,
            'song_identity_review': 'PENDING',
            'editorial_kpop_category_review': 'PENDING',
            'eligible_for_paid_generation': False,
        })
    if not items:
        raise SpotifyOnlyPreviewError(
            '현재 선택곡에 Spotify 2주 자료가 있는 신규 검수 후보가 없습니다. '
            '교차 검수 완료곡은 기존 기사 미리보기에서 확인하세요.'
        )
    prev_start = pair.previous_start.isoformat()
    curr_start = pair.current_start.isoformat()
    prev_end = pair.previous_end.isoformat()
    curr_end = pair.current_end.isoformat()
    lines = [
        '[검수용 무료 초안 · AI 미호출 · 출고 미승인]',
        '선택한 곡의 Spotify 글로벌 주간 차트 변화',
        '',
        f'{prev_start}~{prev_end}과 {curr_start}~{curr_end} Spotify Global Weekly Top Songs '
        f'(상위 200곡)를 비교한 검수 후보 {len(items)}곡의 기록이다.',
        '',
    ]
    for item in items:
        lines.append(
            f"{item['artist']}의 '{item['track']}'은 Spotify {item['previous_rank']}위에서 "
            f"{item['current_rank']}위로 이동했다. 주간 스트리밍은 "
            f"{item['previous_week_streams']:,}회에서 {item['current_week_streams']:,}회로 "
            f"{item['streams_change_pct']:+.2f}% 변화했다."
        )
    lines.extend([
        '',
        '이 자료는 Spotify의 주간 스트리밍과 순위만 설명한다. YouTube 공식 차트의 '
        '미진입을 조회수 0으로 해석하지 않으며, 다른 플랫폼의 인기와 팬덤 규모, '
        '증감 원인을 추정하지 않는다. 곡 버전과 K-POP 분류는 사람이 추가 검수해야 한다.',
        '출처: Spotify Charts (https://charts.spotify.com/).',
        '상태: 검수 대기 / 유료 AI 기사 생성 불허 / 최종 출고 미승인',
    ])
    facts = {
        'status': 'SPOTIFY_ONLY_DRAFT_REVIEW_PENDING',
        'region': 'Global',
        'source': 'https://charts.spotify.com/',
        'source_files': [pair.spotify_previous, pair.spotify_current],
        'period_previous': {'start': prev_start, 'end': prev_end},
        'period_current': {'start': curr_start, 'end': curr_end},
        'chart_scope': 'Spotify Global Weekly Top Songs Top 200',
        'unit': 'streams per chart week',
        'candidates': items,
        'review_required': True,
        'article_publication_approved': False,
        'allowed_paid_ai_generation': False,
        'cautions': [
            '원본 CSV 집계값으로 작성한 무료 사전 점검일 뿐 사람이 승인한 기사가 아님.',
            'K-POP 분류, 곡/버전 동일성, 출처·발행 주차를 사람이 확인해야 함.',
            'YouTube Top 100 미진입은 조회수 0이 아님. 공식 주간 조회수를 추정하지 않음.',
            '2주 차트만으로 K-POP 전체 추세·원인·팬덤 규모 일반화 금지.',
            '기사 자동 게시 및 기존 검수 상태 변경 금지.',
        ],
    }
    return {
        'article': '\n'.join(lines),
        'evidence': facts,
        'mode': 'spotify_only_template',
        'ai_generated_now': False,
        'review_required': True,
        'publication_approved': False,
        'source': ', '.join(facts['source_files']),
        'candidate_count': len(items),
        'note': 'Spotify 단독 검수 후보 · 수치만 1차 확인 · 기사 출고·AI 유료 생성 미승인',
    }
