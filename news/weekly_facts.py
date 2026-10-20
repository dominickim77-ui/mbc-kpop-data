"""STEP22: manifest-bound drafts and explicit human review; never publish or call APIs."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

from news.chart_data_manager import choose_pair
from news.chart_import import BASELINE, WEEKS, safe_path, week_date
from news.weekly_chart_analysis import read_chart, song_key, _change

ROOT = Path(__file__).resolve().parents[1]
LEGACY_WEEK = '2026-10-08'
CATEGORIES = {'KPOP_RELATED_GLOBAL', 'KPOP_SOLO'}


def digest(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def fact_path(root, week, reviewed=True):
    week_date(week)
    if week == LEGACY_WEEK and reviewed:
        return safe_path(root, 'facts/article_ready_fact_sheet_20261008.json')
    return safe_path(root, f'facts/weekly/{week}/{"reviewed" if reviewed else "draft"}.json')


def build_draft(root, week):
    root = Path(root).resolve()
    pair, _, _ = choose_pair(root, week)
    if pair is None:
        raise ValueError('등록된 연속 2주 원본이 필요합니다.')
    refs, charts = {}, {}
    for period, end in [('previous', pair.previous_end), ('current', pair.current_end)]:
        manifest = safe_path(root, WEEKS / f'{end}.json')
        if manifest.is_file():
            record = json.loads(manifest.read_text(encoding='utf-8'))
        else:
            manifest = safe_path(root, BASELINE)
            record = next(r for r in json.loads(manifest.read_text(encoding='utf-8'))['weeks']
                          if r['week_end'] == str(end))
        for platform in ('spotify', 'youtube'):
            name = f'{platform}_{period}'
            rel = pair.files[name]
            refs[name] = {'path': rel,
                          'sha256': hashlib.sha256(safe_path(root, rel).read_bytes()).hexdigest(),
                          'manifest': manifest.relative_to(root).as_posix(),
                          'manifest_record_sha256': digest(record),
                          'provenance': record.get('provenance', {}).get(platform),
                          'registration_status': record['status']}
            charts[name] = read_chart(root, rel, platform)
    candidates = []
    for key in sorted(set().union(*(set(c) for c in charts.values()))):
        hits = [row for c in charts.values() for row in c.get(key, [])]
        row = hits[0]
        item = {'candidate_id': digest(list(key)), 'artist': row['artist'], 'track_name': row['track'],
                'identity_review': 'PENDING', 'version_review': 'PENDING', 'editorial_category': None,
                'matching_status': 'AUTOMATIC_CANDIDATE_ONLY', 'source_rows': {}}
        for platform, metric in [('spotify', 'streams'), ('youtube', 'views')]:
            values = {}
            for period in ('previous', 'current'):
                matches = charts[f'{platform}_{period}'].get(key, [])
                item['source_rows'][f'{platform}_{period}'] = matches
                hit = matches[0] if len(matches) == 1 else None
                values[f'{period}_rank'] = hit['rank'] if hit else None
                values[f'{period}_week_{metric}'] = hit['amount'] if hit else None
            values[f'{metric}_change_pct'] = _change(values[f'previous_week_{metric}'], values[f'current_week_{metric}'])
            item[platform] = values
        candidates.append(item)
    result = {'schema_version': 22, 'status': 'DRAFT_NOT_FOR_PUBLICATION',
              'review_stage': 'PENDING_HUMAN_REVIEW', 'data_validation': 'CSV_AND_MANIFEST_VERIFIED',
              'article_publication_approved': False, 'region': 'Global',
              'week_previous': {'start': str(pair.previous_start), 'end': str(pair.previous_end)},
              'week_current': {'start': str(pair.current_start), 'end': str(pair.current_end)},
              'chart_cutoffs': {'spotify_top_n': 200, 'youtube_top_n': 100},
              'sources': {'spotify_charts': 'https://charts.spotify.com/', 'youtube_charts': 'https://charts.youtube.com/'},
              'source_files': list(pair.files.values()), 'source_refs': refs,
              'period_comparison': {'date_windows': 'MATCHED_BY_REGISTRATION',
                                    'timezones': {k: (v['provenance'] or {}).get('timezone', 'LEGACY_REVIEW')
                                                  for k, v in refs.items()},
                                    'review_required': 'Confirm timezone and aggregation basis before approval'},
              'candidates': candidates, 'analysis_tracks': [], 'analysis_track_count': 0,
              'excluded_reference_tracks': [], 'excluded_reference_count': 0,
              'method': 'Compare consecutive weekly charts within each platform; human identity/version review required.',
              'cautions': ['Missing observations remain null, not zero.',
                           'Weekly streams, weekly song views and lifetime video views are distinct.',
                           'No cross-platform popularity ratios or causal claims.',
                           'Article requires separate human editorial review and publication approval.']}
    result['draft_sha256'] = digest(result)
    return result


def apply_review(draft, review):
    if review.get('week_end') != draft['week_current']['end'] or review.get('draft_sha256') != draft['draft_sha256']:
        raise ValueError('검수 기록의 주차 또는 초안 지문이 다릅니다.')
    if not all(isinstance(review.get(k), str) and review[k].strip() for k in ('reviewer', 'reviewed_at')):
        raise ValueError('검수자와 검수 일시가 필요합니다.')
    if (review.get('period_review') != 'CONFIRMED_COMPARABLE_PERIODS'
            or not isinstance(review.get('period_evidence'), str) or not review['period_evidence'].strip()):
        raise ValueError('두 플랫폼 집계 기간·시간대 비교 검수 근거가 필요합니다.')
    from datetime import datetime
    if datetime.fromisoformat(review['reviewed_at']).tzinfo is None:
        raise ValueError('검수 일시에 시간대가 필요합니다.')
    candidates = {t['candidate_id']: t for t in draft['candidates']}
    approved, seen = [], set()
    for decision in review.get('tracks', []):
        cid = decision.get('candidate_id')
        if cid not in candidates or cid in seen:
            raise ValueError('검수 곡 식별자 누락·중복 또는 불일치입니다.')
        seen.add(cid)
        if (decision.get('identity_review') != 'CONFIRMED_SAME_SONG'
                or decision.get('version_review') != 'CONFIRMED_SAME_VERSION'
                or decision.get('editorial_category') not in CATEGORIES
                or not isinstance(decision.get('evidence'), str) or not decision['evidence'].strip()):
            raise ValueError('곡·버전·편집 분류 및 검수 근거가 모두 필요합니다.')
        track = copy.deepcopy(candidates[cid])
        if any(len(rows) != 1 for rows in track['source_rows'].values()):
            raise ValueError('4개 차트에서 단일 곡으로 확인되지 않은 후보입니다.')
        for platform, metric in [('spotify', 'streams'), ('youtube', 'views')]:
            if track[platform][f'{metric}_change_pct'] is None:
                raise ValueError('증감률 계산 근거가 부족합니다.')
        track.update({k: decision[k] for k in ('identity_review', 'version_review', 'editorial_category')})
        approved.append(track)
    if not approved:
        raise ValueError('검수가 완료된 곡이 없습니다.')
    result = copy.deepcopy(draft)
    result.update(review_stage='TRACK_IDENTITY_AND_EDITORIAL_CATEGORY_APPROVED',
                  analysis_tracks=approved, analysis_track_count=len(approved), human_review=review)
    return result


def validate_reviewed(facts, root=ROOT):
    fresh = build_draft(root, facts['week_current']['end'])
    expected = apply_review(fresh, facts.get('human_review', {}))
    if facts != expected:
        raise ValueError('Fact Sheet가 등록 원본·계산 결과·사람 검수 기록과 일치하지 않습니다.')


def load_reviewed(root, week):
    facts = json.loads(fact_path(root, week).read_text(encoding='utf-8'))
    if facts.get('week_current', {}).get('end') != week:
        raise ValueError('선택 주차와 Fact Sheet 주차가 다릅니다.')
    validate_reviewed(facts, root)
    return facts


def review_template(draft):
    return {'week_end': draft['week_current']['end'], 'draft_sha256': draft['draft_sha256'],
            'reviewer': '', 'reviewed_at': '', 'period_review': 'PENDING', 'period_evidence': '', 'tracks': []}


def main():
    parser = argparse.ArgumentParser(description='주차별 Fact Sheet: 기본 읽기 전용, --apply 신규 저장')
    parser.add_argument('--week-end', required=True)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--review', type=Path, help='사람이 작성한 검수 JSON. 기존 승인 이월 금지')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    root = args.root.resolve()
    if args.week_end == LEGACY_WEEK:
        raise ValueError('10/08 기존 Fact Sheet와 승인 이력은 보존합니다.')
    draft = build_draft(root, args.week_end)
    result = apply_review(draft, json.loads(args.review.read_text(encoding='utf-8'))) if args.review else draft
    if args.apply:
        target = fact_path(root, args.week_end, bool(args.review))
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('x', encoding='utf-8') as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2)
        print(target)
    else:
        print(json.dumps({'fact_sheet': result, 'review_template': review_template(draft)}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError) as exc:
        raise SystemExit(f'BLOCKED: {exc}') from None
