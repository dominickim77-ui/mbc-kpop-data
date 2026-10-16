"""STEP 12 · Global weekly chart comparison on EXISTING selected tracks.

Reads four raw CSVs, NEVER YouTube Data API cumulative video views. A name/primary-
artist match is a *candidate* unless independently reviewed in the article Fact Sheet.
This module never calls OpenAI, YouTube API or MySQL and never writes data files.
"""
from __future__ import annotations

import csv
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PREVIOUS_WEEK = ('2026-09-25', '2026-10-01')
CURRENT_WEEK = ('2026-10-02', '2026-10-08')
FILES = {
    'spotify_previous': 'data/charts/spotify/regional-global-weekly-2026-10-01.csv',
    'spotify_current': 'data/charts/spotify/regional-global-weekly-2026-10-08.csv',
    'youtube_previous': 'data/charts/youtube/youtube-charts-top-songs-global-weekly-20261001.csv',
    'youtube_current': 'data/charts/youtube/youtube-charts-top-songs-global-weekly-20261008.csv',
}
SPOTIFY_REQUIRED = {'rank', 'artist_names', 'track_name', 'streams'}
YOUTUBE_REQUIRED = {'Rank', 'Artist Names', 'Track Name', 'Views'}


class ChartValidationError(ValueError):
    """CSV missing, malformed, or inconsistent with its expected chart structure."""


def normalize(value: str) -> str:
    value = unicodedata.normalize('NFKC', str(value)).casefold()
    value = re.sub(r'[^\w]+', ' ', value)
    return ' '.join(value.split())


def primary_artist(value: str) -> str:
    """Conservative, not a substitute for recording/version verification."""
    return normalize(re.split(r'\s*(?:,| & )\s*', str(value), maxsplit=1)[0])


def song_key(artist: str, track: str) -> tuple[str, str]:
    return normalize(track), primary_artist(artist)


def read_chart(root: Path, rel_path: str, platform: str) -> dict[tuple[str, str], list[dict]]:
    path = root / rel_path
    if not path.is_file():
        raise ChartValidationError(f'CSV 누락: {rel_path}. data/charts 폴더를 확인해 줘.')
    is_spotify = platform == 'spotify'
    required = SPOTIFY_REQUIRED if is_spotify else YOUTUBE_REQUIRED
    expected = 200 if is_spotify else 100
    index: dict[tuple[str, str], list[dict]] = {}
    ranks: set[int] = set()
    try:
        with path.open('r', encoding='utf-8-sig', newline='') as handle:
            reader = csv.DictReader(handle)
            missing = required - set(reader.fieldnames or [])
            if missing:
                raise ChartValidationError(f'{rel_path}: 필수 열 누락 {sorted(missing)}')
            count = 0
            for row in reader:
                count += 1
                try:
                    rank = int(row['rank' if is_spotify else 'Rank'])
                    amount = int(row['streams' if is_spotify else 'Views'])
                except (ValueError, TypeError):
                    raise ChartValidationError(f'{rel_path}: {count}행의 순위·수치가 정수가 아님') from None
                if not 1 <= rank <= expected or rank in ranks or amount < 0:
                    raise ChartValidationError(f'{rel_path}: {count}행의 중복·범위 오류 또는 음수 수치')
                ranks.add(rank)
                artist = (row['artist_names'] if is_spotify else row['Artist Names']).strip()
                track = (row['track_name'] if is_spotify else row['Track Name']).strip()
                if not artist or not track:
                    raise ChartValidationError(f'{rel_path}: {count}행의 아티스트 또는 곡명이 비어 있음')
                key = song_key(artist, track)
                index.setdefault(key, []).append({'rank': rank, 'amount': amount,
                                                    'artist': artist, 'track': track})
    except UnicodeError:
        raise ChartValidationError(f'{rel_path}: 파일 UTF-8 인코딩 확인 필요') from None
    if count != expected or ranks != set(range(1, expected + 1)):
        raise ChartValidationError(f'{rel_path}: 1~{expected}위 완전한 차트가 아님 (실제 {count}곡)')
    return index


def _get_one(index: dict, key: tuple[str, str]) -> tuple[dict | None, bool]:
    hits = index.get(key, [])
    return (hits[0] if len(hits) == 1 else None), len(hits) > 1


def _change(prior: int | None, current: int | None) -> float | None:
    if prior is None or current is None or prior == 0:
        return None
    return round((current - prior) / prior * 100, 2)


def _format_rank(prior: int | None, current: int | None) -> str:
    a = f'{prior}위' if prior is not None else '—'
    b = f'{current}위' if current is not None else '—'
    return f'{a} → {b}'


def _format_amount(prior: int | None, current: int | None, pct: float | None) -> str:
    a = f'{prior:,}' if prior is not None else '—'
    b = f'{current:,}' if current is not None else '—'
    return f'{a} → {b}' + (f' ({pct:+.2f}%)' if pct is not None else ' (증감 계산 불가)')


def _verified_tracks(root: Path) -> tuple[dict, set]:
    path = root / 'facts/article_ready_fact_sheet_20261008.json'
    if not path.is_file():
        return {}, set()
    try:
        obj = json.loads(path.read_text(encoding='utf-8'))
        if (obj.get('status') != 'DRAFT_NOT_FOR_PUBLICATION'
            or obj.get('review_stage') != 'TRACK_IDENTITY_AND_EDITORIAL_CATEGORY_APPROVED'
            or obj.get('article_publication_approved') is not False):
            raise ChartValidationError('기사 Fact Sheet의 검수·출고 상태가 예상과 다름')
        if obj.get('week_previous') != dict(start=PREVIOUS_WEEK[0], end=PREVIOUS_WEEK[1]) or \
           obj.get('week_current') != dict(start=CURRENT_WEEK[0], end=CURRENT_WEEK[1]):
            raise ChartValidationError('Fact Sheet와 CSV 집계 기간이 다름')
        verified = {
            song_key(t['artist'], t['track_name']): t
            for t in obj.get('analysis_tracks', [])
            if t.get('identity_review') == 'CONFIRMED_SAME_SONG'
            and t.get('editorial_category') in {'KPOP_RELATED_GLOBAL', 'KPOP_SOLO'}
        }
        excluded = {normalize(t['track_name']) for t in obj.get('excluded_reference_tracks', [])}
        return verified, excluded
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ChartValidationError(f'Fact Sheet 검증 실패: {exc}') from None


def _matches_reviewed_facts(t: dict, s0: dict | None, s1: dict | None,
                            y0: dict | None, y1: dict | None) -> bool:
    if not all((s0, s1, y0, y1)):
        return False
    try:
        ss, yy = t['spotify'], t['youtube']
        return (
            ss['previous_rank'] == s0['rank'] and ss['current_rank'] == s1['rank']
            and ss['previous_week_streams'] == s0['amount'] and ss['current_week_streams'] == s1['amount']
            and yy['previous_rank'] == y0['rank'] and yy['current_rank'] == y1['rank']
            and yy['previous_week_views'] == y0['amount'] and yy['current_week_views'] == y1['amount']
        )
    except (KeyError, TypeError):
        return False


def build_weekly_rows(selected: list[dict], root: Path = ROOT) -> list[dict]:
    """Returns one record per current MySQL selection; NO cross-platform ratios/difference."""
    if not selected:
        return []
    root = Path(root)
    sources = {
        name: read_chart(root, path, 'spotify' if name.startswith('spotify') else 'youtube')
        for name, path in FILES.items()
    }
    verified, excluded = _verified_tracks(root)
    rows = []
    seen = set()
    for selected_row in selected:
        artist = str(selected_row.get('artist', '')).strip()
        track = str(selected_row.get('track', '')).strip()
        key = song_key(artist, track)
        if not all(key) or key in seen:
            continue
        seen.add(key)
        snapshots = [_get_one(sources[name], key) for name in (
            'spotify_previous', 'spotify_current', 'youtube_previous', 'youtube_current')]
        s0, s1, y0, y1 = [item[0] for item in snapshots]
        ambiguous = any(item[1] for item in snapshots)
        sp0, sp1 = (s0['amount'] if s0 else None), (s1['amount'] if s1 else None)
        yt0, yt1 = (y0['amount'] if y0 else None), (y1['amount'] if y1 else None)
        sp_pct, yt_pct = _change(sp0, sp1), _change(yt0, yt1)
        if ambiguous:
            status = '중복 곡명·버전 검토 필요'
            status_code = 'ambiguous'
        elif key[0] in excluded:
            status = '버전 검수 보류 · 기사 제외'
            status_code = 'excluded'
        elif key in verified:
            if _matches_reviewed_facts(verified[key], s0, s1, y0, y1):
                status = 'Fact Sheet 수치 대조 완료 · 기사 분석 가능'
                status_code = 'reviewed'
            else:
                status = '⚠ Fact Sheet와 원본 CSV 불일치 · 기사 검수 필요'
                status_code = 'mismatch'
        elif s1 and y1:
            status = '동일 곡명·대표 아티스트 후보 · 기사 검수 전'
            status_code = 'candidate'
        else:
            status = '차트 내 자료 부족 (Top 200 / Top 100 기준)'
            status_code = 'partial'
        rows.append({
            'artist': artist, 'track': track,
            'spotify_prev_rank': s0['rank'] if s0 else None,
            'spotify_curr_rank': s1['rank'] if s1 else None,
            'spotify_prev': sp0, 'spotify_current': sp1, 'spotify_pct': sp_pct,
            'youtube_prev_rank': y0['rank'] if y0 else None,
            'youtube_curr_rank': y1['rank'] if y1 else None,
            'youtube_prev': yt0, 'youtube_current': yt1, 'youtube_pct': yt_pct,
            'spotify_rank_display': _format_rank(s0['rank'] if s0 else None, s1['rank'] if s1 else None),
            'youtube_rank_display': _format_rank(y0['rank'] if y0 else None, y1['rank'] if y1 else None),
            'spotify_amount_display': _format_amount(sp0, sp1, sp_pct),
            'youtube_amount_display': _format_amount(yt0, yt1, yt_pct),
            'review_status': status, 'review_code': status_code,
        })
    return rows


def weekly_chart_data(rows: list[dict]) -> dict[str, list]:
    """Two different scales; missing observations represented as null, never 0."""
    return {
        'labels': [f"{r['artist']} — {r['track']}" for r in rows],
        'spotify_previous': [r['spotify_prev'] for r in rows],
        'spotify_current': [r['spotify_current'] for r in rows],
        'youtube_previous': [r['youtube_prev'] for r in rows],
        'youtube_current': [r['youtube_current'] for r in rows],
    }
