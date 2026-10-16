"""K-POP NEWS step11: approved selection -> evidence -> free preview / paid draft.

Use only the human-reviewed article_ready Fact Sheet, not the legacy YouTube video
lifetime counts from the dashboard. Does not make any API calls until requested.
"""
from __future__ import annotations

import copy
import json
import os
import re
import unicodedata
from pathlib import Path

from news.generation import ROOT, FACT_PATH, DEFAULT_MODEL, check_fact_sheet


class SelectionError(ValueError):
    pass


def _norm(value: str) -> str:
    return ' '.join(unicodedata.normalize('NFKC', str(value)).casefold().split())


def selected_snapshot(selected_rows: list[dict], facts: dict) -> dict:
    """Pure, testable selection/filtering logic; selected_rows come from server DB."""
    check_fact_sheet(facts)
    verified = {(_norm(t['artist']), _norm(t['track_name'])): t
                for t in facts['analysis_tracks'] if
                t.get('identity_review') == 'CONFIRMED_SAME_SONG' and
                t.get('editorial_category') in {'KPOP_RELATED_GLOBAL', 'KPOP_SOLO'}}
    exclusion_names = {_norm(t['track_name']) for t in facts.get('excluded_reference_tracks', [])}
    selected, approved, rejected, used = [], [], [], set()
    for row in selected_rows:
        artist, track = str(row['artist']).strip(), str(row['track']).strip()
        key = (_norm(artist), _norm(track))
        if not all(key) or key in used:
            continue
        used.add(key)
        selected.append({'artist': artist, 'track': track})
        if key in verified:
            approved.append(copy.deepcopy(verified[key]))
        else:
            reason = ('곡 버전 차이가 확인되어 이번 기사 분석에서 제외됨' if key[1] in exclusion_names
                      else '동일 주차 두 플랫폼 차트 및 곡 식별에 대한 사람 검수가 완료되지 않음')
            rejected.append({'artist': artist, 'track': track, 'reason': reason})
    return {
        'selected_tracks': selected,
        'approved_tracks': approved,
        'excluded_tracks': rejected,
        'can_generate': bool(approved),
        'week_previous': facts['week_previous'],
        'week_current': facts['week_current'],
        'chart_cutoffs': facts['chart_cutoffs'],
        'publication_approved': False,
    }


def load_verified_facts() -> dict:
    facts = json.loads(FACT_PATH.read_text(encoding='utf-8'))
    check_fact_sheet(facts)
    return facts


def read_current_selection() -> list[dict]:
    """Use the *current server selection*, not editable names sent by the browser."""
    import app as app_module  # lazy: app includes the news router during import
    ids = list(app_module.analysis_song_ids)
    if not ids:
        return []
    conn = app_module.get_db_connection()
    cursor = None
    try:
        cursor = conn.cursor(dictionary=True)
        placeholders = ','.join(['%s'] * len(ids))
        cursor.execute(f'SELECT song_id, artist, track FROM tracks WHERE song_id IN ({placeholders})', tuple(ids))
        by_id = {int(r['song_id']): r for r in cursor.fetchall()}
        return [by_id[i] for i in ids if i in by_id]
    finally:
        if cursor is not None:
            cursor.close()
        conn.close()


def evidence_for_selected(facts: dict, snapshot: dict) -> dict:
    if not snapshot['approved_tracks']:
        raise SelectionError('선택된 곡 중 검증된 주간 양쪽 차트 근거가 없습니다. 검수가 완료된 Animal 또는 SaWaDiKa를 선택해 주세요.')
    return {
        'region': facts['region'],
        'week_previous': facts['week_previous'],
        'week_current': facts['week_current'],
        'chart_cutoffs': facts['chart_cutoffs'],
        'sources': facts['sources'],
        'analysis_tracks': snapshot['approved_tracks'],
        'analysis_track_count': len(snapshot['approved_tracks']),
        'method': facts['method'],
        'cautions': facts['cautions'],
        'article_publication_approved': False,
    }


def preview_text(evidence: dict) -> str:
    names = ', '.join(f"{t['artist']} '{t['track_name']}'" for t in evidence['analysis_tracks'])
    start1, end1 = evidence['week_previous']['start'], evidence['week_previous']['end']
    start2, end2 = evidence['week_current']['start'], evidence['week_current']['end']
    details = []
    for t in evidence['analysis_tracks']:
        s, y = t['spotify'], t['youtube']
        details.append(
            f"{t['artist']} '{t['track_name']}': "
            f"Spotify {s['previous_rank']}위→{s['current_rank']}위, "
            f"주간 스트리밍 {s['previous_week_streams']:,}→{s['current_week_streams']:,}회 "
            f"({s['streams_change_pct']:+.2f}%); "
            f"YouTube 주간 Top Songs {y['previous_rank']}위→{y['current_rank']}위, "
            f"주간 조회수 {y['previous_week_views']:,}→{y['current_week_views']:,}회 "
            f"({y['views_change_pct']:+.2f}%)."
        )
    return (
        '[무료 사전 점검 · AI 미호출] 현재 선택한 곡의 차트 요약\n'
        f"{start1}~{end1}과 {start2}~{end2}, Global 주간 차트에서 "
        f"검수된 곡 {len(evidence['analysis_tracks'])}개({names})를 비교했다.\n\n"
        + '\n\n'.join(details) + '\n\n'
        'Spotify 주간 스트리밍과 YouTube 곡 차트의 주간 조회수는 집계 방식이 다르며, '
        '차트 범위도 각각 상위 200곡과 100곡이다. 두 수치를 합산·나눗셈하거나 '
        '이 사례만으로 K-POP 전체의 추세·원인을 단정할 수 없다.\n'
        '출처: Spotify Charts(https://charts.spotify.com/), YouTube Charts(https://charts.youtube.com/).\n'
        '상태: 검수 전 초안 / 출고 미승인'
    )


def generate_paid_article(evidence: dict) -> tuple[str, str]:
    """Single Responses API call, no automatic retries, no publication."""
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=ROOT / '.env', override=False)
    key = os.getenv('OPENAI_API_KEY', '').strip()
    if not key:
        raise RuntimeError('OPENAI_API_KEY가 없습니다. .env에 등록한 뒤 다시 확인하세요.')
    from openai import OpenAI, APIError, APITimeoutError, AuthenticationError, RateLimitError
    model = os.getenv('OPENAI_MODEL', DEFAULT_MODEL).strip() or DEFAULT_MODEL
    instructions = (
        '너는 데이터 저널리즘 기사의 초안을 작성하는 편집 보조자다. 제공된 JSON의 analysis_tracks에 '\
        '있는 곡만 다룬다. 한국어 제목 한 줄과 본문 두세 문단을 작성한다. '\
        'Global 범위, 두 주간 날짜, 각 곡의 두 플랫폼 순위 변화 및 플랫폼 내부 수치 변화율을 정확히 표기하라. '\
        'Spotify는 주간 스트리밍, YouTube는 Weekly Top Songs 주간 조회수이며 동일 지표가 아니다. '\
        '차트의 상위 200곡/100곡 범위 차이를 밝혀라. '\
        '제공된 곡 외의 곡·인터뷰·원인·팬덤 규모·인구 추정·외부 통계를 만들어내지 마라. '\
        '인기도 배율이나 플랫폼 간 수치 차이 계산을 금한다. '\
        'K-POP 전체 현상으로 일반화하지 않는다. 출처 Spotify Charts와 YouTube Charts를 적고, '\
        '검수 전 초안이며 최종 출고 미승인임을 끝에 적는다. 입력에 없는 숫자는 추가하지 마라.'
    )
    try:
        with OpenAI(api_key=key, timeout=30.0, max_retries=0) as client:
            opts = {'reasoning': {'effort': 'none'}} if model == DEFAULT_MODEL else {}
            response = client.responses.create(
                model=model,
                instructions=instructions,
                input=json.dumps(evidence, ensure_ascii=False),
                max_output_tokens=950,
                store=False,
                **opts,
            )
        if response.status != 'completed':
            raise RuntimeError('모델 응답이 완료되지 않아 기사로 사용할 수 없습니다.')
        article = (response.output_text or '').strip()
        if not article or len(article) > 8000:
            raise RuntimeError('유효한 기사 초안이 반환되지 않았습니다.')
        # Stop accidental discussion of excluded reference from becoming a news claim.
        if re.search(r'hootie\s+frutti', article, re.I) and not any(t['track_name'] == 'Hootie Frutti' for t in evidence['analysis_tracks']):
            raise RuntimeError('검수 보류곡이 기사에 포함되어 저장을 중단했습니다. 재요청 전 과금 기록을 확인하세요.')
        return article, model
    except AuthenticationError as e:
        raise RuntimeError('OpenAI 인증 오류: API 키와 프로젝트 권한을 확인하세요.') from e
    except RateLimitError as e:
        raise RuntimeError('잔액·요청 한도 오류: 사용량을 확인하세요.') from e
    except APITimeoutError as e:
        raise RuntimeError('30초 대기 시간 초과: 재시도 전 과금 사용 내역을 확인하세요.') from e
    except APIError as e:
        raise RuntimeError('OpenAI API 요청 실패: ' + type(e).__name__) from e
