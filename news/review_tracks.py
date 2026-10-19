"""STEP 06-2 | 기사에 사용할 곡 3개의 검수 자료 생성 (Python 표준 라이브러리만 사용).

실행: 프로젝트 루트에서 `python news\\review_tracks.py`
기존 원자료와 Fact Sheet는 변경하지 않습니다.
YouTube Weekly Top Songs는 여러 영상·음원 사용량을 합산한 곡 차트일 수 있으므로
CSV에 적힌 YouTube URL을 '조회수 전체의 원인인 단일 영상'으로 해석하지 않습니다.
"""

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

# Keep both the historical file command and package/module imports working.
import sys
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from news.match_charts import build_matches, normalize
from news.weekly_changes import calculate

ROOT = Path(__file__).resolve().parent.parent
OUT_CSV = ROOT / 'data/processed/track_review_queue_20261008.csv'
OUT_JSON = ROOT / 'facts/track_review_queue_20261008.json'
TARGETS = ['Hootie Frutti', 'Animal', 'SaWaDiKa']

# 자동 검증이 아닌 '사람이 검토할 분류 제안'입니다.
CATEGORY_SUGGESTIONS = {
    'Hootie Frutti': 'KPOP_RELATED_GLOBAL',
    'Animal': 'KPOP_RELATED_GLOBAL',
    'SaWaDiKa': 'KPOP_SOLO',
}
CATEGORY_OPTIONS = [
    'KPOP_GROUP', 'KPOP_SOLO', 'KPOP_RELATED_GLOBAL',
    'KPOP_COLLABORATION', 'OTHER', 'UNRESOLVED',
]
REVIEW_COLUMNS = [
    'track_name', 'spotify_artists', 'youtube_artists',
    'spotify_rank', 'youtube_rank', 'spotify_weekly_streams', 'youtube_weekly_views',
    'spotify_change_pct', 'youtube_change_pct',
    'spotify_url', 'youtube_reference_url', 'youtube_link_note',
    'suggested_category', 'identity_review', 'category_review',
    'approved_category', 'reviewer_note', 'reviewed_at',
]


def spotify_web_url(track_uri):
    # Spotify URI 형식 검사. 문자열 구성은 공식 리소스 주소의 표기 변환에 한함.
    bits = track_uri.split(':')
    if len(bits) != 3 or bits[:2] != ['spotify', 'track']:
        return ''
    track_id = bits[2]
    if len(track_id) != 22 or not track_id.isalnum():
        return ''
    return f'https://open.spotify.com/track/{track_id}'


def trusted_youtube_reference(url):
    parsed = urlparse(url)
    return url if parsed.scheme == 'https' and parsed.hostname in {
        'youtube.com', 'www.youtube.com', 'youtu.be', 'www.youtu.be',
    } else ''


def existing_reviews():
    """재실행 시 CSV에 사람이 적어놓은 검수 내용을 보존합니다."""
    if not OUT_CSV.exists():
        return {}
    with OUT_CSV.open('r', encoding='utf-8-sig', newline='') as fp:
        reader = csv.DictReader(fp)
        if not {'track_name', 'identity_review', 'category_review'}.issubset(reader.fieldnames or []):
            raise ValueError('기존 검수 CSV 열이 달라 재생성을 중단했습니다. 먼저 파일을 확인하세요.')
        return {normalize(r['track_name']): r for r in reader}


def create_review_queue():
    match_rows, _ = build_matches()
    changes, _ = calculate()
    matches = {normalize(r['track_name']): r for r in match_rows}
    weekly = {normalize(r['track_name']): r for r in changes}
    prev = existing_reviews()

    out = []
    for title in TARGETS:
        key = normalize(title)
        if key not in matches or key not in weekly:
            raise ValueError(f'이번 주 차트의 일치 후보를 찾지 못했습니다: {title}')
        m, c = matches[key], weekly[key]
        old = prev.get(key, {})
        out.append({
            'track_name': title,
            'spotify_artists': m['spotify_artists'],
            'youtube_artists': m['youtube_artists'],
            'spotify_rank': m['spotify_rank'],
            'youtube_rank': m['youtube_rank'],
            'spotify_weekly_streams': m['spotify_weekly_streams'],
            'youtube_weekly_views': m['youtube_weekly_views'],
            'spotify_change_pct': c['spotify_streams_change_pct'],
            'youtube_change_pct': c['youtube_views_change_pct'],
            'spotify_url': spotify_web_url(m['spotify_track_uri']),
            'youtube_reference_url': trusted_youtube_reference(m['youtube_source_url']),
            'youtube_link_note': 'YouTube URL은 참고 링크. Weekly Top Songs의 전체 주간 조회수를 단일 영상 조회수로 해석 금지',
            'suggested_category': CATEGORY_SUGGESTIONS[title],
            'identity_review': old.get('identity_review', 'PENDING') or 'PENDING',
            'category_review': old.get('category_review', 'PENDING') or 'PENDING',
            'approved_category': old.get('approved_category', ''),
            'reviewer_note': old.get('reviewer_note', ''),
            'reviewed_at': old.get('reviewed_at', ''),
        })

    # 사람이 승인한 상태라도 최종 기사 승인을 자동으로 부여하지 않습니다.
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open('w', encoding='utf-8-sig', newline='') as fp:
        writer = csv.DictWriter(fp, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        writer.writerows(out)

    summary = {
        'status': 'DRAFT_NOT_FOR_PUBLICATION',
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'region': 'Global',
        'period_start': '2026-10-02', 'period_end': '2026-10-08',
        'review_policy': 'Manual confirmation required for track identity, version and editorial K-POP category',
        'category_options': CATEGORY_OPTIONS,
        'identity_status_options': ['PENDING', 'CONFIRMED_SAME_SONG', 'AMBIGUOUS_VERSION', 'REJECTED'],
        'category_status_options': ['PENDING', 'CONFIRMED', 'UNRESOLVED'],
        'youtube_aggregation_warning': 'Weekly Top Songs views are chart-level song totals; the representative video URL is not the sole source of those views',
        'no_auto_approval': True,
        'source_charts': ['https://charts.spotify.com/', 'https://charts.youtube.com/'],
        'review_items': out,
        'pending_identity_count': sum(r['identity_review'] == 'PENDING' for r in out),
        'pending_category_count': sum(r['category_review'] == 'PENDING' for r in out),
    }
    with OUT_JSON.open('w', encoding='utf-8') as fp:
        json.dump(summary, fp, ensure_ascii=False, indent=2)
    return summary


def main():
    result = create_review_queue()
    print(f"✅ 검토할 곡: {len(result['review_items'])}곡")
    for r in result['review_items']:
        print(f"🎵 {r['track_name']} | Spotify {r['spotify_rank']}위 / YouTube {r['youtube_rank']}위 | "
              f"동일 곡 검토: {r['identity_review']} | 분류 검토: {r['category_review']}")
    print(f'📄 검수 CSV: {OUT_CSV.relative_to(ROOT)}')
    print(f'📄 검수 JSON: {OUT_JSON.relative_to(ROOT)}')
    print('⚠️ 자동 승인 없음: 링크와 곡 정보를 직접 확인하고 사람이 검수해야 합니다.')


def cli():
    import argparse
    parser = argparse.ArgumentParser(description='명시적 실행 시 기존 결과 파일을 생성하는 오프라인 도구')
    parser.parse_args()
    main()


if __name__ == '__main__':
    cli()
