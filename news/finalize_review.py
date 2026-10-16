"""STEP 06-8 | 확정한 K-POP 분류를 검수표에 반영하고 기사용 근거자료를 만듭니다.

프로젝트 최상위 폴더에서 실행:
    python news\\finalize_review.py

전제: news/apply_review_notes.py가 생성한 검수 초안을 사용합니다.
원본 차트/기존 검수 초안/기존 Fact Sheet는 건드리지 않습니다.
이미 결과 파일이 있으면 덮어쓰지 않습니다.

이 단계는 아티스트의 편집상 분류와 두 곡의 곡 단위 매칭 승인일 뿐,
기사 작성/출고/게시 승인이 아닙니다.
"""

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INPUT_CSV = ROOT / 'data/processed/track_review_draft_20261008.csv'
WEEKLY_CSV = ROOT / 'data/processed/weekly_changes_20261008.csv'
OUTPUT_CSV = ROOT / 'data/processed/track_review_classified_20261008.csv'
OUTPUT_JSON = ROOT / 'facts/article_ready_fact_sheet_20261008.json'

# 2026-10-16 대화에서 사용자가 명시적으로 확정한 편집상 분류
# 분류 확정과 기사 사용 승인(곡 동일성)은 별개로 기록합니다.
CATEGORIES = {
    'Hootie Frutti': 'KPOP_RELATED_GLOBAL',
    'Animal': 'KPOP_RELATED_GLOBAL',
    'SaWaDiKa': 'KPOP_SOLO',
}
IDENTITIES = {
    'Hootie Frutti': 'AMBIGUOUS_VERSION',
    'Animal': 'CONFIRMED_SAME_SONG',
    'SaWaDiKa': 'CONFIRMED_SAME_SONG',
}
EXCLUDED = {'Hootie Frutti'}
SOURCE_URLS = {
    'spotify_charts': 'https://charts.spotify.com/',
    'youtube_charts': 'https://charts.youtube.com/',
}


def load_csv(path, required):
    if not path.is_file():
        raise ValueError(f'파일을 찾을 수 없습니다: {path.relative_to(ROOT)}')
    with path.open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames or []
        missing = set(required) - set(columns)
        if missing:
            raise ValueError(f'{path.name}의 필수 열 누락: {sorted(missing)}')
        rows = list(reader)
    return columns, rows


def check_number(value, label):
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f'{label}이 유효한 정수가 아닙니다: {value!r}') from None


def optional_int(value):
    if value in (None, ''):
        return None
    return check_number(value, '전주 값')


def optional_float(value):
    if value in (None, ''):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f'유효하지 않은 변화율: {value!r}') from None


def main():
    # 기존 결과를 수정하거나 덮어쓰지 않도록 사전에 모두 검사합니다.
    if OUTPUT_CSV.exists() or OUTPUT_JSON.exists():
        raise SystemExit('이미 승인 분류 결과 파일이 있습니다. 기존 결과를 보존하기 위해 중단합니다.')

    required_review = {
        'track_name', 'spotify_artists', 'youtube_artists',
        'spotify_rank', 'youtube_rank', 'spotify_weekly_streams',
        'youtube_weekly_views', 'identity_review', 'category_review',
        'approved_category', 'reviewer_note', 'reviewed_at',
        'spotify_url', 'youtube_reference_url',
    }
    columns, rows = load_csv(INPUT_CSV, required_review)
    names = [r['track_name'] for r in rows]
    if len(rows) != 3 or len(set(names)) != 3 or set(names) != set(CATEGORIES):
        raise ValueError('검수표가 예상한 세 곡으로 구성되어 있지 않아 중단합니다.')

    _, weekly = load_csv(WEEKLY_CSV, {
        'track_name', 'spotify_artists', 'youtube_artists',
        'spotify_rank_20261001', 'spotify_rank_20261008',
        'spotify_streams_20261001', 'spotify_streams_20261008',
        'spotify_streams_change_pct',
        'youtube_rank_20261001', 'youtube_rank_20261008',
        'youtube_views_20261001', 'youtube_views_20261008',
        'youtube_views_change_pct',
    })
    weekly_by_name = {r['track_name']: r for r in weekly}
    if len(weekly_by_name) != len(weekly):
        raise ValueError('주간 비교 결과에서 곡명이 중복되어 있습니다.')

    approved_at_utc = datetime.now(timezone.utc).isoformat()
    approved_rows = []
    candidates = []
    excluded_items = []

    for row in rows:
        name = row['track_name']
        expected_identity = IDENTITIES[name]
        if row['identity_review'] != expected_identity:
            raise ValueError(f'{name}: 이전 검수 결과가 달라 자동 분류를 중단합니다.')
        if row['category_review'] != 'PENDING' or row['approved_category'] or row['reviewed_at']:
            raise ValueError(f'{name}: 기존에 분류 승인이 있어 덮어쓰지 않습니다.')
        if name not in weekly_by_name:
            raise ValueError(f'{name}: 주간 비교 결과를 찾을 수 없습니다.')
        w = weekly_by_name[name]
        for field, source_field in (
            ('spotify_rank', 'spotify_rank_20261008'),
            ('youtube_rank', 'youtube_rank_20261008'),
            ('spotify_weekly_streams', 'spotify_streams_20261008'),
            ('youtube_weekly_views', 'youtube_views_20261008'),
        ):
            if check_number(row[field], field) != check_number(w[source_field], source_field):
                raise ValueError(f'{name}: {field} 값이 매칭표와 주간 비교표에서 다릅니다.')

        item = row.copy()
        item['category_review'] = 'CONFIRMED'
        item['approved_category'] = CATEGORIES[name]
        item['reviewed_at'] = approved_at_utc
        note = ('편집 분류 승인(2026-10-16 사용자 결정): ' + CATEGORIES[name] + '. ')
        if name in EXCLUDED:
            note += 'Spotify 리믹스/YouTube 곡 차트 버전 대응 불명확: 주요 분석에서 제외; 참고 사례로만 사용.'
        else:
            note += '곡 단위 매칭 확인: 이번 기사의 주요 분석 후보로 포함. 출고 전 최종 기사 검수 필요.'
        item['reviewer_note'] = (item['reviewer_note'].rstrip() + ' ' + note).strip()
        approved_rows.append(item)

        detail = {
            'track_name': name,
            'artist': 'KATSEYE' if name in ('Hootie Frutti', 'Animal') else 'LISA',
            'editorial_category': CATEGORIES[name],
            'identity_review': expected_identity,
            'spotify': {
                'previous_rank': optional_int(w['spotify_rank_20261001']),
                'current_rank': check_number(w['spotify_rank_20261008'], 'Spotify 현재 순위'),
                'previous_week_streams': optional_int(w['spotify_streams_20261001']),
                'current_week_streams': check_number(w['spotify_streams_20261008'], 'Spotify 현재 재생수'),
                'streams_change_pct': optional_float(w['spotify_streams_change_pct']),
                'source_track_url': item['spotify_url'],
            },
            'youtube': {
                'previous_rank': optional_int(w['youtube_rank_20261001']),
                'current_rank': check_number(w['youtube_rank_20261008'], 'YouTube 현재 순위'),
                'previous_week_views': optional_int(w['youtube_views_20261001']),
                'current_week_views': check_number(w['youtube_views_20261008'], 'YouTube 현재 조회수'),
                'views_change_pct': optional_float(w['youtube_views_change_pct']),
                'representative_video_reference_only': item['youtube_reference_url'],
            },
            'caution': '주간 스트리밍과 주간 조회수는 서로 다른 지표; 단일 영상 누적 조회수 아님.',
        }
        if name in EXCLUDED:
            excluded_items.append({
                'track_name': name,
                'editorial_category': CATEGORIES[name],
                'reason': 'Spotify 페이지는 PEDRO SAMPAIO Remix, YouTube 대표 MV는 일반 곡명; 버전 대응 불명확',
                'use': '설명용 사례만 가능. 기사 핵심 순위 비교·통계에서 제외',
            })
        else:
            candidates.append(detail)

    if len(candidates) != 2 or len(excluded_items) != 1:
        raise ValueError('기사 분석 대상으로 선택된 곡 수가 예상과 다릅니다.')

    facts = {
        'status': 'DRAFT_NOT_FOR_PUBLICATION',
        'review_stage': 'TRACK_IDENTITY_AND_EDITORIAL_CATEGORY_APPROVED',
        'article_publication_approved': False,
        'editorial_decision_date': '2026-10-16',
        'recorded_at_utc': approved_at_utc,
        'region': 'Global',
        'week_previous': {'start': '2026-09-25', 'end': '2026-10-01'},
        'week_current': {'start': '2026-10-02', 'end': '2026-10-08'},
        'chart_cutoffs': {'spotify_top_n': 200, 'youtube_top_n': 100},
        'sources': SOURCE_URLS,
        'source_files': [
            'data/charts/spotify/regional-global-weekly-2026-10-01.csv',
            'data/charts/spotify/regional-global-weekly-2026-10-08.csv',
            'data/charts/youtube/youtube-charts-top-songs-global-weekly-20261001.csv',
            'data/charts/youtube/youtube-charts-top-songs-global-weekly-20261008.csv',
            'data/processed/track_review_draft_20261008.csv',
            'data/processed/weekly_changes_20261008.csv',
        ],
        'approved_categories': {
            'KATSEYE': 'KPOP_RELATED_GLOBAL',
            'LISA': 'KPOP_SOLO',
        },
        'analysis_tracks': candidates,
        'analysis_track_count': len(candidates),
        'excluded_reference_tracks': excluded_items,
        'excluded_reference_count': len(excluded_items),
        'review_evidence': '2026-10-16 사용자 제공 Spotify 및 공식 YouTube 영상 페이지 캡처; 최종 기사 출고 검토는 별도',
        'method': '각 플랫폼 내부에서만 전주와 금주 수치의 변화율을 계산한다.',
        'cautions': [
            'Spotify와 YouTube의 순위는 차트별 상대적 위치. 순위 차이만으로 인기도 배율을 계산하지 않는다.',
            '서로 다른 단위인 스트리밍과 조회수를 합산하거나 서로 나누지 않는다.',
            '두 플랫폼의 차트 범위는 Spotify 200곡, YouTube 100곡으로 다르다.',
            'KATSEYE는 K-POP 연계 글로벌 그룹으로, LISA는 K-POP 그룹 멤버 솔로로 분류한다.',
            '기사 주요 분석 사례 2곡만으로 K-POP 전체 또는 글로벌 팬덤에 일반화하지 않는다.',
            'YouTube Weekly Top Songs는 곡 차트의 주간 조회수이며 대표 MV 한 편의 조회수가 아니다.',
            '과거 주간 미매칭을 조회수·스트리밍 0으로 치환하지 않는다.',
            '원인이나 인과관계, 이용자 수를 추론하지 않는다.',
            '수치와 기사 본문은 추가 대조해야 하며 AI 기사 초안은 출고 승인이 아니다.',
        ],
    }

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    # 전체 검사가 통과한 뒤 새 파일로만 저장합니다.
    with OUTPUT_CSV.open('x', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(approved_rows)
    with OUTPUT_JSON.open('x', encoding='utf-8') as handle:
        json.dump(facts, handle, ensure_ascii=False, indent=2)

    for row in approved_rows:
        action = '참고만 · 기사 주요 분석 제외' if row['track_name'] in EXCLUDED else '주요 분석 후보'
        print(f"{row['track_name']}: 분류={row['approved_category']} / 곡 검토={row['identity_review']} / {action}")
    print(f'검수 완료 CSV: {OUTPUT_CSV.relative_to(ROOT)}')
    print(f'기사용 Fact Sheet: {OUTPUT_JSON.relative_to(ROOT)}')
    print('기사 주요 분석 대상 2곡 / 버전 보류 1곡 · 최종 출고 승인 아님')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as error:
        raise SystemExit(f'검수 반영 중단: {error}') from None
