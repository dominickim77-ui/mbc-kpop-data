"""MBC K-POP 데이터 저널리즘 STEP 07 — 검증된 Fact Sheet로 기사 초안 생성.

사용법 (프로젝트 최상위 폴더에서):
    python news\\generation.py --mode template

템플릿은 AI/API 없이 동작합니다. 외부 유료 API는 명시적으로 선택할 때만 호출합니다:
    python news\\generation.py --mode openai --confirm-paid

결과물: articles/draft_template_20261008.md + .json (AI 실행 시 draft_openai_*).
기존 Fact Sheet 및 웹사이트는 수정하지 않습니다. 기사 자동 게시도 하지 않습니다.
"""

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FACT_PATH = ROOT / 'facts' / 'article_ready_fact_sheet_20261008.json'
OUTPUT_DIR = ROOT / 'articles'
DEFAULT_MODEL = 'gpt-5.4-mini-2026-03-17'


class FactSheetError(ValueError):
    """Fact Sheet 검수 요건이 만족되지 않은 경우."""


def check_fact_sheet(facts: dict) -> None:
    """구조, 검수 상태 및 주요 수치를 검사합니다. 자동 팩트체크 완료를 뜻하지 않습니다."""
    if facts.get('status') != 'DRAFT_NOT_FOR_PUBLICATION':
        raise FactSheetError('Fact Sheet 상태가 예상과 다릅니다. 임의로 승인 처리하지 마세요.')
    if facts.get('review_stage') != 'TRACK_IDENTITY_AND_EDITORIAL_CATEGORY_APPROVED':
        raise FactSheetError('곡 식별 및 편집 분류가 승인된 Fact Sheet만 사용합니다.')
    if facts.get('article_publication_approved') is not False:
        raise FactSheetError('기사 출고 여부는 이 단계에서 변경할 수 없습니다.')
    if facts.get('region') != 'Global':
        raise FactSheetError('기사의 비교 지역은 Global이어야 합니다.')
    if facts.get('week_previous') != {'start': '2026-09-25', 'end': '2026-10-01'}:
        raise FactSheetError('이전 주 데이터 기간이 다릅니다.')
    if facts.get('week_current') != {'start': '2026-10-02', 'end': '2026-10-08'}:
        raise FactSheetError('이번 주 데이터 기간이 다릅니다.')
    if facts.get('chart_cutoffs') != {'spotify_top_n': 200, 'youtube_top_n': 100}:
        raise FactSheetError('차트 순위 범위가 다릅니다.')

    tracks = facts.get('analysis_tracks')
    if not isinstance(tracks, list) or len(tracks) != 2 or facts.get('analysis_track_count') != 2:
        raise FactSheetError('현재 첫 기사에서 승인한 분석 대상은 2곡입니다.')
    expected = {'Animal': ('KATSEYE', 'KPOP_RELATED_GLOBAL'),
                'SaWaDiKa': ('LISA', 'KPOP_SOLO')}
    if {track.get('track_name') for track in tracks} != set(expected):
        raise FactSheetError('승인된 두 곡(Animal, SaWaDiKa)만 주요 분석에 사용할 수 있습니다.')
    for track in tracks:
        name = track['track_name']
        artist, category = expected[name]
        if (track.get('artist'), track.get('editorial_category'), track.get('identity_review')) != (
                artist, category, 'CONFIRMED_SAME_SONG'):
            raise FactSheetError(f'{name}: 아티스트·편집 분류·곡 검수 상태를 확인하세요.')
        for platform, metric, rate in (('spotify', 'streams', 'streams_change_pct'),
                                       ('youtube', 'views', 'views_change_pct')):
            p = track.get(platform)
            if not isinstance(p, dict):
                raise FactSheetError(f'{name}: {platform} 값이 없습니다.')
            prev = p.get(f'previous_week_{metric}')
            current = p.get(f'current_week_{metric}')
            prev_rank, curr_rank = p.get('previous_rank'), p.get('current_rank')
            if any(type(v) is not int or v <= 0 for v in (prev, current, prev_rank, curr_rank)):
                raise FactSheetError(f'{name}: {platform}의 순위·집계량은 양의 정수여야 합니다.')
            limit = 200 if platform == 'spotify' else 100
            if prev_rank > limit or curr_rank > limit:
                raise FactSheetError(f'{name}: {platform} 순위 범위가 잘못됐습니다.')
            calculated = round((current - prev) / prev * 100, 2)
            recorded = p.get(rate)
            if type(recorded) not in (float, int) or abs(calculated - recorded) > 0.015:
                raise FactSheetError(f'{name}: {platform} 변화율 불일치 ({calculated} vs {recorded})')

    exclusions = facts.get('excluded_reference_tracks', [])
    if (facts.get('excluded_reference_count') != 1 or len(exclusions) != 1
            or exclusions[0].get('track_name') != 'Hootie Frutti'):
        raise FactSheetError('리믹스 버전 검수가 필요한 Hootie Frutti가 제외되어야 합니다.')
    if not isinstance(facts.get('source_files'), list) or len(facts['source_files']) < 4:
        raise FactSheetError('원자료 파일 기록이 부족합니다.')
    if not isinstance(facts.get('sources'), dict) or not all(
            facts['sources'].get(k) for k in ('spotify_charts', 'youtube_charts')):
        raise FactSheetError('공식 차트 출처 정보가 필요합니다.')


def fmt(n):
    return f'{n:,}'


def template_article(facts: dict) -> str:
    """고정 기사 문장. 생성형 AI를 호출하지 않습니다."""
    entries = {t['track_name']: t for t in facts['analysis_tracks']}
    a, l = entries['Animal'], entries['SaWaDiKa']

    def describe(t):
        s, y = t['spotify'], t['youtube']
        particle = '는' if t['track_name'] == 'SaWaDiKa' else '은'
        return (f"{t['artist']}의 '{t['track_name']}'{particle} Spotify {s['previous_rank']}→{s['current_rank']}위"
                f"(주간 스트리밍 {fmt(s['previous_week_streams'])}→{fmt(s['current_week_streams'])}회, "
                f"{s['streams_change_pct']:+.2f}%), YouTube {y['previous_rank']}→{y['current_rank']}위"
                f"(주간 조회 {fmt(y['previous_week_views'])}→{fmt(y['current_week_views'])}회, "
                f"{y['views_change_pct']:+.2f}%)를 기록했다.")

    title = '[사전 점검용 고정 기사 · AI 미호출]\n순위 변화와 소비량 변화는 다르다: K-POP 관련 곡의 글로벌 차트 비교'
    paragraph1 = ('2026년 9월 25일~10월 1일과 10월 2일~8일의 글로벌 주간 차트를 비교했다. '
                  + describe(a))
    paragraph2 = (describe(l) + ' Spotify는 상위 200곡, YouTube는 상위 100곡 차트이며 '
                  '스트리밍과 조회수는 서로 다른 집계 지표다. 두 곡으로 K-POP 전체의 추세나 원인을 단정할 수 없다. '
                  '출처: Spotify Charts(https://charts.spotify.com/), YouTube Charts(https://charts.youtube.com/).')
    return f'{title}\n\n{paragraph1}\n\n{paragraph2}'


def curated_facts(facts: dict) -> dict:
    """모델에 필요한 승인된 정보만 전달합니다. 원본 CSV는 보내지 않습니다."""
    return {key: facts[key] for key in (
        'region', 'week_previous', 'week_current', 'chart_cutoffs',
        'sources', 'analysis_tracks', 'analysis_track_count', 'method', 'cautions'
    )}


def generate_openai_article(facts: dict) -> tuple[str, str]:
    """선택 실행용 유료 호출. 자동 재시도/자동 게시하지 않습니다."""
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=ROOT / '.env', override=False)
    except ImportError:
        # .env 자동 읽기가 필요하면 python-dotenv를 설치합니다.
        pass
    key = os.getenv('OPENAI_API_KEY', '').strip()
    if not key:
        raise RuntimeError('OPENAI_API_KEY가 없습니다. .env 또는 환경변수에 설정하세요. 키를 채팅에 붙이지 마세요.')
    try:
        from openai import OpenAI, APIError, APITimeoutError, AuthenticationError, RateLimitError
    except ImportError as exc:
        raise RuntimeError('OpenAI Python SDK가 없습니다. python -m pip install openai python-dotenv') from exc

    model = os.getenv('OPENAI_MODEL', DEFAULT_MODEL).strip() or DEFAULT_MODEL
    instructions = (
        '너는 K-POP 데이터 기사 작성 보조자다. 제공된 JSON 이외의 사실은 사용하지 않는다. '
        '한국어로 제목 1줄 + 본문 2문단의 짧은 기사 초안을 작성한다(가능하면 450자 이내). '
        '반드시 두 주차의 정확한 기간, Global 지역, Animal·SaWaDiKa의 플랫폼별 순위 변화 및 각 플랫폼 내부 소비량 증감률을 적는다. '
        'Spotify 주간 스트리밍과 YouTube 주간 곡 차트 조회수는 다른 지표라고 설명한다. '
        'Spotify 상위 200곡, YouTube 상위 100곡이라는 차트 범위 차이도 적는다. '
        'Spotify Charts와 YouTube Charts를 출처로 표시한다. '
        'Hootie Frutti는 검수 보류로 주요 분석에서 제외되었으니 언급하지 않는다. '
        '확인되지 않은 원인, 사용자 수, 인용문, 팬덤 규모, 인기 배수, 글로벌 K-POP 전체의 일반화는 절대 작성하지 않는다. '
        '새로운 수치를 계산하거나 창작하지 않는다. 출고 승인되었다고 표현하지 않는다.'
    )
    try:
        with OpenAI(api_key=key, timeout=30.0, max_retries=0) as client:
            opts = {'reasoning': {'effort': 'none'}} if model == DEFAULT_MODEL else {}
            response = client.responses.create(
                model=model,
                instructions=instructions,
                input=json.dumps(curated_facts(facts), ensure_ascii=False),
                max_output_tokens=750,
                store=False,
                **opts,
            )
        if response.status != 'completed':
            raise RuntimeError('모델 응답이 완전히 종료되지 않았습니다. 기사 초안으로 사용하지 않습니다.')
        article = (response.output_text or '').strip()
        if not article or len(article) > 5000:
            raise RuntimeError('유효한 기사 초안이 반환되지 않았습니다.')
        return article, model
    except AuthenticationError as exc:
        raise RuntimeError('OpenAI 인증 오류: 키·프로젝트 접근 권한을 직접 확인하세요.') from exc
    except RateLimitError as exc:
        raise RuntimeError('요청 한도 또는 잔액 오류입니다. 무작정 재시도하지 마세요.') from exc
    except APITimeoutError as exc:
        raise RuntimeError('30초 응답 대기 초과. 재시도 전 사용량·과금 내역을 확인하세요.') from exc
    except APIError as exc:
        raise RuntimeError(f'OpenAI API 요청 실패: {type(exc).__name__}') from exc


def main():
    parser = argparse.ArgumentParser(description='K-POP 차트 기사 초안 생성 (기본값: 무료 템플릿)')
    parser.add_argument('--mode', choices=('template', 'openai'), default='template')
    parser.add_argument('--confirm-paid', action='store_true', help='OpenAI 유료 호출 의사 명시')
    args = parser.parse_args()
    if args.mode == 'openai' and not args.confirm_paid:
        raise SystemExit('실제 유료 API를 호출하려면 --confirm-paid를 추가해야 합니다.')

    if not FACT_PATH.is_file():
        raise SystemExit(f'기사용 Fact Sheet가 없습니다: {FACT_PATH}')
    with FACT_PATH.open(encoding='utf-8') as fp:
        facts = json.load(fp)
    check_fact_sheet(facts)

    # 기존 결과를 덮어쓰지 않습니다. 날짜는 원자료 주차 기준으로 고정됩니다.
    prefix = 'draft_template' if args.mode == 'template' else 'draft_openai'
    out_md = OUTPUT_DIR / f'{prefix}_20261008.md'
    out_json = OUTPUT_DIR / f'{prefix}_20261008.json'
    if out_md.exists() or out_json.exists():
        raise SystemExit('기사 초안 파일이 이미 있습니다. 이전 결과를 보존하도록 실행을 중단합니다.')

    if args.mode == 'template':
        article, model = template_article(facts), None
    else:
        print('OpenAI 유료 요청 1회 실행: 계정별 권한 및 비용이 발생할 수 있습니다.')
        article, model = generate_openai_article(facts)

    result = {
        'mode': args.mode,
        'ai_generated': args.mode == 'openai',
        'model': model,
        'review_required': True,
        'publication_approved': False,
        'article_status': 'DRAFT_NOT_FOR_PUBLICATION',
        'fact_sheet': str(FACT_PATH.relative_to(ROOT)).replace('\\', '/'),
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'article': article,
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # 원본 CSV, Fact Sheet, 검수표, 기존 앱은 건드리지 않습니다.
    with out_md.open('x', encoding='utf-8') as handle:
        handle.write(article + '\n')
    with out_json.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)

    print('\n====== 생성된 기사 초안 ======\n')
    print(article)
    print('\n====== 실행 요약 ======')
    print('AI 호출 여부:', result['ai_generated'])
    print('최종 검수 필요:', result['review_required'])
    print('기사 출고 승인:', result['publication_approved'])
    print('기사 파일:', out_md.relative_to(ROOT))
    print('결과 JSON:', out_json.relative_to(ROOT))


if __name__ == '__main__':
    try:
        main()
    except (FactSheetError, OSError, ValueError, RuntimeError) as error:
        raise SystemExit(f'기사 생성 중단: {error}') from None
