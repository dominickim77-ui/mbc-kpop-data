"""Offline weekly CSV intake. No DB, network, credentials or editorial approval.

The per-week manifest is the commit point. Objects and staging are append-only;
an interrupted writer cannot expose half a pair. Local trusted-operator CLI only.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from security.preview_data import data_root
ROOT = data_root()
BASELINE = Path('data/chart_registry/baseline.json')
WEEKS = Path('data/chart_registry/weeks')
OBJECTS = Path('data/chart_imports/objects')
STAGING = Path('data/chart_imports/staging')
MAX_BYTES = 5 * 1024 * 1024
SPECS = {
    'spotify': (200, ('rank', 'artist_names', 'track_name', 'streams'), 'charts.spotify.com', 'weekly_streams'),
    'youtube': (100, ('Rank', 'Artist Names', 'Track Name', 'Views'), 'charts.youtube.com', 'weekly_song_views'),
}


class ImportProblem(ValueError):
    def __init__(self, code, message, status='FAIL'):
        super().__init__(message)
        self.code, self.status = code, status


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')


def safe_path(root, relative):
    root = Path(root).resolve()
    path = root / relative
    if not path.resolve().is_relative_to(root):
        raise ImportProblem('PATH', '작업 폴더 밖 경로는 허용하지 않습니다.')
    # Reject symlinks/junctions even when they point inside the root.
    for part in [path, *path.parents]:
        if part == root:
            break
        if part.is_symlink() or (hasattr(part, 'is_junction') and part.is_junction()):
            raise ImportProblem('PATH', '링크 경로는 허용하지 않습니다.')
    return path


def read_bytes(path):
    with Path(path).open('rb') as handle:
        raw = handle.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ImportProblem('SIZE', '파일 크기 제한은 5 MiB입니다.')
    return raw


def read_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ImportProblem('JSON', 'JSON 키가 중복되었습니다.')
            result[key] = value
        return result
    try:
        return json.loads(read_bytes(path).decode('utf-8-sig'), object_pairs_hook=pairs)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ImportProblem('JSON', 'JSON 형식 또는 인코딩 오류입니다.') from exc


def week_date(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ImportProblem('PERIOD', '종료일은 YYYY-MM-DD 형식이어야 합니다.')
    try:
        end = date.fromisoformat(value)
    except ValueError as exc:
        raise ImportProblem('PERIOD', '유효하지 않은 날짜입니다.') from exc
    if end.weekday() != 3 or end >= datetime.now(timezone.utc).date():
        raise ImportProblem('PERIOD', '완료된 목요일 종료 주차만 가져옵니다.')
    return end


def validate_csv(raw, platform):
    count, columns, _, _ = SPECS[platform]
    try:
        reader = csv.reader(io.StringIO(raw.decode('utf-8-sig'), newline=''), strict=True)
        header = next(reader, [])
        if len(header) != len(set(header)) or not set(columns).issubset(header):
            raise ImportProblem('HEADER', f'{platform}: 필수 열 누락 또는 중복 헤더입니다.')
        ranks, identities, stable_ids, ambiguous = set(), set(), set(), []
        amounts = {}
        for line, values in enumerate(reader, 2):
            if len(values) != len(header):
                raise ImportProblem('ROW', f'{platform}: {line}행 열 개수가 다릅니다.')
            row = dict(zip(header, values))
            rank, artist, track, amount = [row[c] for c in columns]
            if not re.fullmatch(r'[0-9]+', rank) or not re.fullmatch(r'[0-9]+', amount):
                raise ImportProblem('NUMBER', f'{platform}: {line}행 순위·수치는 음수가 아닌 정수여야 합니다.')
            rank, amount = int(rank), int(amount)
            if rank not in range(1, count + 1) or rank in ranks:
                raise ImportProblem('RANK', f'{platform}: {line}행 순위 중복 또는 범위 오류입니다.')
            if not artist.strip() or not track.strip() or '\x00' in artist + track:
                raise ImportProblem('IDENTITY', f'{platform}: {line}행 아티스트·곡명 오류입니다.')
            identity = (artist.strip(), track.strip())
            if identity in identities:
                raise ImportProblem('DUPLICATE_SONG', f'{platform}: {line}행 동일 아티스트·곡명이 중복됩니다.')
            identities.add(identity)
            for key in ('uri', 'track_uri', 'Track ID'):
                if key in row and row[key].strip():
                    stable = (key, row[key].strip())
                    if stable in stable_ids:
                        raise ImportProblem('DUPLICATE_ID', f'{platform}: 곡 식별자가 중복됩니다.')
                    stable_ids.add(stable)
            ranks.add(rank)
            amounts[rank] = amount
        if ranks != set(range(1, count + 1)):
            raise ImportProblem('COUNT', f'{platform}: 완전한 Top {count}가 아닙니다.')
        from news.weekly_chart_analysis import song_key
        keys = [song_key(a, t) for a, t in identities]
        if len(keys) != len(set(keys)):
            ambiguous.append('정규화 후 곡 식별이 겹칩니다. 기존 화면에서 모호한 매칭으로 보류합니다.')
        if any(amounts[i] < amounts[i + 1] for i in range(1, count)):
            ambiguous.append('순위와 수치의 내림차순이 다릅니다. 공식 원본 재확인이 필요합니다.')
        return {'rows': count, 'sha256': sha256(raw), 'warnings': ambiguous}
    except (UnicodeError, csv.Error) as exc:
        raise ImportProblem('CSV', f'{platform}: UTF-8 또는 CSV 구문 오류입니다.') from exc


def validate_provenance(metadata, raws, end):
    if not isinstance(metadata, dict) or set(metadata) != set(SPECS):
        raise ImportProblem('SOURCE', '두 플랫폼의 출처 기록이 필요합니다.', 'BLOCKED')
    for platform, raw in raws.items():
        m = metadata[platform]
        _, _, host, metric = SPECS[platform]
        if not isinstance(m, dict):
            raise ImportProblem('SOURCE', '출처 기록은 객체여야 합니다.', 'BLOCKED')
        url = urlsplit(str(m.get('source_url', '')))
        if url.scheme != 'https' or url.netloc != host or url.query or url.fragment:
            raise ImportProblem('SOURCE_URL', f'{platform}: 토큰 없는 공식 차트 HTTPS URL을 기록하세요.', 'BLOCKED')
        if (m.get('region') != 'Global' or m.get('chart_type') != 'weekly_top_songs'
                or m.get('metric') != metric or m.get('week_end') != end.isoformat()
                or m.get('week_start') != (end - timedelta(days=6)).isoformat()):
            raise ImportProblem('SOURCE_PERIOD', f'{platform}: 지역·차트·지표·기간이 일치하지 않습니다.', 'BLOCKED')
        if m.get('sha256') != sha256(raw):
            raise ImportProblem('SOURCE_HASH', f'{platform}: 확인한 원본과 파일 지문이 다릅니다.', 'BLOCKED')
        if m.get('source_confirmed') is not True or m.get('period_confirmed') is not True:
            raise ImportProblem('UNCONFIRMED_SOURCE', f'{platform}: 공식 출처·집계 기간 확인이 필요합니다.', 'BLOCKED')
        for field in ('reviewer', 'source_evidence', 'period_basis', 'timezone', 'usage_evidence'):
            if not isinstance(m.get(field), str) or not m[field].strip():
                raise ImportProblem('EVIDENCE', f'{platform}: {field} 근거가 필요합니다.', 'BLOCKED')
        if platform == 'spotify' and m['timezone'] != 'UTC':
            raise ImportProblem('TIMEZONE', 'Spotify 집계 시간대는 UTC입니다.', 'BLOCKED')
        if m.get('usage_status') != 'confirmed_local_analysis':
            raise ImportProblem('USAGE_UNCONFIRMED', f'{platform}: 로컬 분석 이용 근거가 미확인입니다.', 'BLOCKED')
        try:
            collected = datetime.fromisoformat(m['downloaded_at'].replace('Z', '+00:00'))
            if collected.tzinfo is None or collected.date() <= end or collected > datetime.now(timezone.utc):
                raise ValueError()
        except (KeyError, ValueError, TypeError, AttributeError):
            raise ImportProblem('COLLECTED_AT', f'{platform}: 주차 종료 후의 시간대 포함 다운로드 시각이 필요합니다.', 'BLOCKED') from None


def _check_record(root, record, legacy=False):
    if not isinstance(record, dict) or record.get('version') != 1:
        raise ImportProblem('MANIFEST', '등록 기록 버전 오류입니다.')
    end = week_date(record.get('week_end'))
    if record.get('status') != ('legacy_preserved' if legacy else 'verified'):
        raise ImportProblem('MANIFEST', '검증 완료 등록 기록이 아닙니다.')
    if set(record.get('files', {})) != set(SPECS):
        raise ImportProblem('MANIFEST', '등록된 두 플랫폼 원본이 필요합니다.')
    files, raws = {}, {}
    for platform, item in record['files'].items():
        digest = item['sha256']
        if not re.fullmatch('[0-9a-f]{64}', digest):
            raise ImportProblem('HASH', '등록 지문 형식 오류입니다.')
        rel = item['path']
        if legacy:
            expected = (f'data/charts/spotify/regional-global-weekly-{end}.csv' if platform == 'spotify'
                        else f'data/charts/youtube/youtube-charts-top-songs-global-weekly-{end:%Y%m%d}.csv')
        else:
            expected = (OBJECTS / f'{digest}.csv').as_posix()
        if rel != expected:
            raise ImportProblem('PATH', '등록된 원본 경로가 허용 형식과 다릅니다.')
        raw = read_bytes(safe_path(root, rel))
        allowed_hashes = {digest}
        if legacy and item.get('working_tree_sha256'):
            allowed_hashes.add(item['working_tree_sha256'])
        if sha256(raw) not in allowed_hashes:
            raise ImportProblem('HASH', '등록 후 원본이 변경되어 해당 주차를 제외합니다.')
        validate_csv(raw, platform)
        files[platform], raws[platform] = rel, raw
    if not legacy:
        validate_provenance(record.get('provenance'), raws, end)
    return end, files


def registered_inventory(root):
    """Read only. Bad new records never remove unaffected historical weeks."""
    from security.preview_data import fixture_root, inventory
    if fixture_root(root):
        return inventory(root)
    inventory, notes = {}, []
    baseline = read_json(safe_path(root, BASELINE))
    if not isinstance(baseline, dict) or baseline.get('baseline_commit') != '916233682e9de0432b96413b030f568935102111':
        raise ImportProblem('BASELINE', '기준 커밋 목록이 없거나 손상되었습니다.')
    for record in baseline['weeks']:
        try:
            end, files = _check_record(root, record, legacy=True)
            inventory[end] = files
        except (ValueError, OSError, KeyError, TypeError) as exc:
            notes.append(f'기존 주차 검증 실패: {type(exc).__name__}')
    folder = safe_path(root, WEEKS)
    for path in sorted(folder.glob('*.json')) if folder.exists() else []:
        try:
            record = read_json(safe_path(root, path.relative_to(root)))
            end, files = _check_record(root, record)
            if path.name != f'{end}.json' or end in inventory:
                raise ImportProblem('CONFLICT', '주차 등록 충돌입니다.')
            inventory[end] = files
        except (ValueError, OSError, KeyError, TypeError) as exc:
            notes.append(f'{path.name}: 등록 검증 실패로 제외 ({type(exc).__name__})')
    return inventory, notes


def _write_new(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


@contextmanager
def writer_lock(root):
    path = safe_path(root, 'data/chart_registry/import.lock')
    try:
        _write_new(path, json_bytes({'pid': os.getpid(), 'started_at': datetime.now(timezone.utc).isoformat()}))
    except FileExistsError:
        raise ImportProblem('LOCKED', '다른 가져오기 작업 또는 중단된 잠금이 있습니다. 기록을 확인하세요.', 'BLOCKED') from None
    try:
        yield
    finally:
        path.unlink()


def import_week(root, spotify, youtube, provenance, week_end, apply=False):
    """Dry run writes nothing. Apply retains staging even on validation failure."""
    root = Path(root).resolve()
    report = {'status': 'FAIL', 'action': 'dry_run' if not apply else 'apply', 'registered': False,
              'week_end': week_end, 'checks': {}, 'phase2_news_changed': False}
    stage = None
    try:
        end = week_date(week_end)
        raws = {'spotify': read_bytes(spotify), 'youtube': read_bytes(youtube)}
        metadata = read_json(provenance)
        if apply:
            stage = safe_path(root, STAGING / uuid.uuid4().hex)
            for platform, raw in raws.items():
                _write_new(stage / f'{platform}.csv', raw)
            _write_new(stage / 'provenance.json', json_bytes(metadata))
            report['staging'] = stage.relative_to(root).as_posix()
        for platform, raw in raws.items():
            report['checks'][platform] = validate_csv(raw, platform)
        validate_provenance(metadata, raws, end)
        if any('내림차순' in w for result in report['checks'].values() for w in result['warnings']):
            raise ImportProblem('ORDER_REVIEW', '순위·수치 순서 이상: 공식 원본 재확인 후 진행하세요.', 'BLOCKED')
        record = {'version': 1, 'status': 'verified', 'week_end': str(end),
                  'registered_at': datetime.now(timezone.utc).isoformat(), 'provenance': metadata,
                  'files': {p: {'sha256': sha256(raw), 'path': (OBJECTS / f'{sha256(raw)}.csv').as_posix()}
                            for p, raw in raws.items()}}

        def preflight():
            inventory, notes = registered_inventory(root)
            destination = safe_path(root, WEEKS / f'{end}.json')
            legacy_ends = {r['week_end'] for r in read_json(safe_path(root, BASELINE))['weeks']}
            if end in inventory:
                if all(sha256(read_bytes(safe_path(root, inventory[end][p]))) == sha256(raw) for p, raw in raws.items()):
                    return 'duplicate', inventory, notes
                raise ImportProblem('CONFLICT', '같은 주차의 다른 원본입니다. 기존 데이터를 덮어쓰지 않습니다.', 'BLOCKED')
            if str(end) in legacy_ends:
                raise ImportProblem('CONFLICT', '기준 주차의 원본이 손상되었거나 누락되었습니다. 새 등록으로 대체하지 않습니다.', 'BLOCKED')
            if destination.exists():
                raise ImportProblem('CONFLICT', '해당 주차에 손상되거나 보류된 등록 기록이 있습니다.', 'BLOCKED')
            for prior, files in inventory.items():
                for platform, raw in raws.items():
                    if sha256(read_bytes(safe_path(root, files[platform]))) == sha256(raw):
                        raise ImportProblem('REUSED_WEEK', f'{platform}: {prior} 주차와 같은 파일입니다. 기간 재확인이 필요합니다.', 'BLOCKED')
            return 'new', inventory, notes

        state, inventory, notes = preflight()
        report.update(status='SKIP' if state == 'duplicate' else 'PASS', outcome=state,
                      comparable=(end - timedelta(days=7)) in inventory, notes=notes,
                      planned_files=record['files'])
        if apply and state != 'duplicate':
            with writer_lock(root):
                state, _, _ = preflight()
                if state == 'duplicate':
                    report.update(status='SKIP', outcome='duplicate')
                else:
                    for p, raw in raws.items():
                        path = safe_path(root, record['files'][p]['path'])
                        if path.exists():
                            if read_bytes(path) != raw:
                                raise ImportProblem('OBJECT_CONFLICT', '보관 원본 지문 충돌입니다.')
                        else:
                            _write_new(path, raw)
                    _check_record(root, record)
                    # READY is not success; only the final .json manifest commits a week.
                    _write_new(stage / 'result.json', json_bytes({**report, 'outcome': 'READY_TO_COMMIT'}))
                    target = safe_path(root, WEEKS / f'{end}.json')
                    pending = safe_path(root, WEEKS / f'{end}.{uuid.uuid4().hex}.pending')
                    _write_new(pending, json_bytes(record))
                    os.replace(pending, target)
                    report.update(registered=True, outcome='registered')
        if stage and not (stage / 'result.json').exists():
            _write_new(stage / 'result.json', json_bytes(report))
    except (ImportProblem, OSError, ValueError, KeyError, TypeError) as exc:
        # A manifest already committed is authoritative even if lock cleanup failed.
        if report['registered']:
            report.update(status='PASS', warning='등록은 완료됐으나 잠금 정리에 실패했습니다. 재실행 전 잠금을 확인하세요.')
            return report
        report.update(status=getattr(exc, 'status', 'FAIL'), code=getattr(exc, 'code', 'IO_OR_FORMAT'),
                      error=str(exc) if isinstance(exc, ImportProblem) else type(exc).__name__)
        if stage:
            try:
                _write_new(stage / 'failure.json', json_bytes(report))
            except OSError:
                report['log_error'] = '오류 기록 저장 실패. 출력 결과를 보존하세요.'
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description='공식 출처 확인 주간 CSV 가져오기 — 기본 Dry Run, 네트워크·DB 미사용')
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--spotify', type=Path, required=True)
    parser.add_argument('--youtube', type=Path, required=True)
    parser.add_argument('--provenance', type=Path, required=True)
    parser.add_argument('--week-end', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    result = import_week(args.root, args.spotify, args.youtube, args.provenance, args.week_end, args.apply)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['status'] in {'PASS', 'SKIP'} else 2


if __name__ == '__main__':
    raise SystemExit(main())
