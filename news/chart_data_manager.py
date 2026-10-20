"""STEP 21: discover registered Spotify/YouTube Global Weekly CSV pairs.

No network, credentials, MySQL, OpenAI or automatic approval. New weeks require source-confirmed intake manifests; legacy weeks are hash-pinned.
"""
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPOTIFY_NAME = re.compile(r'^regional-global-weekly-(\d{4}-\d{2}-\d{2})\.csv$')
YOUTUBE_NAME = re.compile(r'^youtube-charts-top-songs-global-weekly-(\d{8})\.csv$')


class CatalogError(ValueError):
    pass


@dataclass(frozen=True)
class WeekPair:
    previous_end: date
    current_end: date
    spotify_previous: str
    spotify_current: str
    youtube_previous: str
    youtube_current: str

    @property
    def previous_start(self) -> date:
        return self.previous_end - timedelta(days=6)

    @property
    def current_start(self) -> date:
        return self.current_end - timedelta(days=6)

    @property
    def files(self) -> dict[str, str]:
        return {
            'spotify_previous': self.spotify_previous,
            'spotify_current': self.spotify_current,
            'youtube_previous': self.youtube_previous,
            'youtube_current': self.youtube_current,
        }

    @property
    def label(self) -> str:
        return f'{self.previous_start:%Y.%m.%d}~{self.previous_end:%m.%d} → {self.current_start:%Y.%m.%d}~{self.current_end:%m.%d}'


def _inventory(root: Path) -> tuple[dict[date, dict[str, str]], list[str]]:
    """STEP21: only pinned legacy files and verified intake manifests are visible."""
    from news.chart_import import registered_inventory
    try:
        return registered_inventory(Path(root).resolve())
    except (ValueError, OSError, KeyError, TypeError) as exc:
        raise CatalogError('기간 목록을 확인할 수 없습니다: ' + type(exc).__name__) from exc


def scan_chart_weeks(root: Path = ROOT) -> tuple[list[WeekPair], list[str]]:
    """Return complete consecutive two-week pairs plus audit notes for partial weeks."""
    root = Path(root)
    inventory, notes = _inventory(root)
    complete = {d for d, files in inventory.items() if set(files) == {'spotify', 'youtube'}}
    for d in sorted(inventory):
        if d not in complete:
            missing = sorted({'spotify', 'youtube'} - set(inventory[d]))
            notes.append(f'{d.isoformat()} 종료 주: {", ".join(missing)} CSV가 없어 비교에서 제외')
    pairs = []
    for current_end in sorted(complete, reverse=True):
        previous_end = current_end - timedelta(days=7)
        if previous_end not in complete:
            continue
        before, after = inventory[previous_end], inventory[current_end]
        pairs.append(WeekPair(previous_end, current_end, before['spotify'], after['spotify'],
                              before['youtube'], after['youtube']))
    if inventory and not pairs:
        notes.append('비교 가능한 연속 2주 자료가 없습니다. 운영 담당자의 자료 등록이 필요합니다.')
    if not inventory:
        notes.append('등록된 Spotify·YouTube 차트 자료가 없습니다.')
    return pairs, notes


def choose_pair(root: Path = ROOT, week_end: str = '') -> tuple[WeekPair | None, list[WeekPair], list[str]]:
    pairs, notes = scan_chart_weeks(root)
    if not pairs:
        return None, [], notes
    if not week_end:
        return pairs[0], pairs, notes  # most recent complete consecutive two weeks
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', week_end):
        raise CatalogError('주차 선택 형식 오류: YYYY-MM-DD 형식이어야 해')
    for pair in pairs:
        if pair.current_end.isoformat() == week_end:
            return pair, pairs, notes
    raise CatalogError(f'{week_end}: 현재 등록된 연속 2주 비교 목록에 없는 날짜야')


def validate_pair(pair: WeekPair, root: Path = ROOT) -> None:
    """Use STEP 12's strict column, rank, row count, nonnegative checks."""
    from news.weekly_chart_analysis import read_chart
    for name, relpath in pair.files.items():
        read_chart(Path(root), relpath, 'spotify' if name.startswith('spotify') else 'youtube')


def main() -> int:
    parser = argparse.ArgumentParser(description='읽기 전용: Global 주간 차트 CSV 인식·검증')
    parser.add_argument('--check', action='store_true', help='모든 비교 가능 주차의 원본 CSV 검증')
    args = parser.parse_args()
    try:
        pairs, notes = scan_chart_weeks()
        print('등록된 연속 2주 차트 비교:', len(pairs), '개')
        for pair in pairs:
            print(f'  - 종료일 {pair.current_end}: {pair.label}')
            if args.check:
                validate_pair(pair)
                print('    ✅ 4개 원본 CSV 기본 형식 검증 통과')
        for note in notes:
            print('  ⚠', note)
        if args.check and not pairs:
            return 1
    except (CatalogError, ValueError, OSError) as exc:
        print('❌ 차트 데이터 검사 실패:', exc)
        return 1
    print('주의: 파일 내용의 공식 출처·곡 버전·기사 승인 여부는 별도 검수 대상이야.')
    return 0


if __name__ == '__main__':
    # `python news/chart_data_manager.py` starts with news/ on sys.path.
    import sys
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    raise SystemExit(main())
