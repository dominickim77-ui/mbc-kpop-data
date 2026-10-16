"""STEP 06-7 | Screenshot-based review notes (draft only).

Run at the repository root: python news\\apply_review_notes.py

Reads the human-review queue produced by news/review_tracks.py and produces
separate draft output files. It does not overwrite the queue, back-up, raw
chart CSVs, or the earlier Fact Sheets. K-POP classification and publication
approval remain PENDING.
"""

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INPUT = ROOT / 'data' / 'processed' / 'track_review_queue_20261008.csv'
OUTPUT_CSV = ROOT / 'data' / 'processed' / 'track_review_draft_20261008.csv'
OUTPUT_JSON = ROOT / 'facts' / 'track_review_draft_20261008.json'

# Evidence: Spotify track detail and reference YouTube MV screenshots
# checked together in the class session on 2026-10-16.
DECISIONS = {
    'Hootie Frutti': {
        'identity_review': 'AMBIGUOUS_VERSION',
        'reviewer_note': (
            '2026-10-16 화면 확인: Spotify 링크의 발매 정보에 '
            'Hootie Frutti (PEDRO SAMPAIO Remix)가 표시됨. '
            'YouTube 참고 링크는 HYBE LABELS의 Hootie Frutti Official MV. '
            '곡명과 아티스트는 같지만 버전이 달라 엄밀한 일대일 비교 보류. '
            'YouTube Weekly Top Songs 조회수는 해당 영상 한 편의 조회수가 아님.'
        ),
    },
    'Animal': {
        'identity_review': 'CONFIRMED_SAME_SONG',
        'reviewer_note': (
            '2026-10-16 화면 확인: Spotify 곡 Animal / KATSEYE, '
            'YouTube HYBE LABELS의 Animal Official MV. '
            '표시상 곡명·아티스트가 일치하고 리믹스 표기 없음. '
            '곡 단위 매칭은 확인, 동일 마스터 음원 여부는 미검증. '
            'YouTube 차트 주간 조회수는 단일 MV 누적 조회수가 아님.'
        ),
    },
    'SaWaDiKa': {
        'identity_review': 'CONFIRMED_SAME_SONG',
        'reviewer_note': (
            '2026-10-16 화면 확인: Spotify 곡 SaWaDiKa / LISA, '
            'YouTube LLOUD Official의 SaWaDiKa Official Music Video. '
            '표시상 곡명·아티스트가 일치하고 리믹스 표기 없음. '
            '곡 단위 매칭은 확인, 동일 마스터 음원 여부는 미검증. '
            'YouTube 차트 주간 조회수는 단일 MV 누적 조회수가 아님.'
        ),
    },
}


def main():
    if not INPUT.is_file():
        raise SystemExit(f'검수표를 찾지 못했습니다: {INPUT}')
    # Re-running must not silently replace a manually edited draft.
    for path in (OUTPUT_CSV, OUTPUT_JSON):
        if path.exists():
            raise SystemExit(f'기존 초안이 있어 덮어쓰지 않습니다: {path}')

    with INPUT.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames or []
        required = {'track_name', 'identity_review', 'category_review',
                    'approved_category', 'reviewer_note', 'reviewed_at'}
        if not required.issubset(columns):
            raise SystemExit('입력 검수표의 필수 컬럼이 누락되었습니다.')
        rows = list(reader)

    by_name = {r['track_name']: r for r in rows}
    if len(rows) != 3 or set(by_name) != set(DECISIONS):
        raise SystemExit('검수 대상 3곡이 예상한 목록과 다릅니다. 파일을 확인하세요.')
    if any(r['identity_review'] != 'PENDING' or r['category_review'] != 'PENDING'
           or r['approved_category'] or r['reviewed_at'] for r in rows):
        raise SystemExit('이미 검수 상태가 수정된 행이 있어 자동 반영을 중단합니다.')

    # Record observed evidence, not publication approval or category sign-off.
    for name, decision in DECISIONS.items():
        item = by_name[name]
        item['identity_review'] = decision['identity_review']
        item['reviewer_note'] = decision['reviewer_note']
        item['category_review'] = 'PENDING'
        item['approved_category'] = ''
        item['reviewed_at'] = ''

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open('x', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    facts = {
        'status': 'DRAFT_NOT_FOR_PUBLICATION',
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'evidence_type': 'User-provided Spotify/YouTube page screenshots',
        'evidence_checked_on': '2026-10-16',
        'scope': 'Same song/title and displayed-version review only, not audio-master verification',
        'editorial_category_approval': 'PENDING',
        'publication_approval': 'NOT_APPROVED',
        'warning': 'YouTube Weekly Top Songs view totals are NOT single-video view totals.',
        'items': rows,
    }
    with OUTPUT_JSON.open('x', encoding='utf-8') as f:
        json.dump(facts, f, ensure_ascii=False, indent=2)

    for r in rows:
        print(f"{r['track_name']}: 곡 검토={r['identity_review']} / K-POP 분류={r['category_review']}")
    print(f'검토 CSV: {OUTPUT_CSV.relative_to(ROOT)}')
    print(f'검토 JSON: {OUTPUT_JSON.relative_to(ROOT)}')
    print('기사 최종 승인 없음 · K-POP 분류는 별도 확인 필요')


if __name__ == '__main__':
    main()
