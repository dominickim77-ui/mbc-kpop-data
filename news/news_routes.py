# KPOP_WEEKLY_MANAGER_STEP13
"""Same-page selected-song news endpoints. GET actions are free; POST is paid."""
import json
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from news.provenance import generation_record

from news.selected_news import (
    ROOT, SelectionError, evidence_for_selected, generate_paid_article,
    load_verified_facts, preview_text, read_current_selection, selected_snapshot,
)

router = APIRouter(prefix='/api/news', tags=['K-POP News Analysis'])
ARTICLES = ROOT / 'articles'
_lock = threading.Lock()


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    confirm_paid: bool = False
    week_end: str = ""


def _same_origin(request: Request) -> bool:
    origin = request.headers.get('origin', '')
    host = request.headers.get('host', '')
    return origin in (f'http://{host}', f'https://{host}') and host.split(':')[0] in {'localhost', '127.0.0.1'}


def _selection(week_end=''):
    try:
        facts = load_verified_facts(week_end) if week_end and week_end != '2026-10-08' else load_verified_facts()
        snapshot = selected_snapshot(read_current_selection(), facts)
        return facts, snapshot
    except FileNotFoundError:
        raise HTTPException(409 if week_end and week_end != '2026-10-08' else 404,
                            '선택 주차의 Fact Sheet 검수가 완료되지 않았습니다. 원본·곡·버전 검수를 진행하세요.') from None
    except (ValueError, KeyError, TypeError) as e:
        raise HTTPException(409 if week_end and week_end != '2026-10-08' else 422,
                            f'근거 검증 실패: {e}') from None
    except Exception:
        raise HTTPException(503, 'Current Analysis의 MySQL 데이터를 읽지 못했습니다. 연결을 확인하세요.') from None


def _public_selection(snapshot):
    return {
        **{k: v for k, v in snapshot.items() if k != 'approved_tracks'},
        'approved_tracks': [
            {'artist': t['artist'], 'track': t['track_name'], 'editorial_category': t['editorial_category']}
            for t in snapshot['approved_tracks']
        ],
    }


# STEP17A_SPOTIFY_ONLY_PREVIEW: verified-format chart values, draft only.
@router.get('/spotify-only-preview')
def spotify_only_preview(week_end: str = ''):
    from news.chart_data_manager import choose_pair, CatalogError
    from news.weekly_chart_analysis import ChartValidationError
    from news.spotify_only_preview import make_spotify_only_preview, SpotifyOnlyPreviewError
    try:
        pair, _, _ = choose_pair(root=ROOT, week_end=week_end)
        if pair is None:
            raise HTTPException(409, '연속 2주간의 Spotify·YouTube 공식 차트 파일이 준비되지 않았어.')
        selected = read_current_selection()  # browser cannot inject artist names
        return make_spotify_only_preview(selected, pair, root=ROOT)
    except (CatalogError, ChartValidationError, SpotifyOnlyPreviewError) as exc:
        raise HTTPException(422, str(exc)) from None
    except HTTPException:
        raise
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(422, f'Spotify 검수 자료 오류: {exc}') from None
    except Exception:
        raise HTTPException(503, '선택곡을 읽지 못했어. MySQL 연결을 확인해 줘.') from None


@router.get('/review-candidates')
def current_review_candidates(week_end: str = ''):
    # STEP16 · read-only candidate evidence; no AI requests or approvals.
    from news.chart_data_manager import choose_pair, CatalogError
    from news.weekly_chart_analysis import ChartValidationError
    from news.review_candidates_step16 import build_review_queue, ReviewQueueError
    try:
        pair, _, _ = choose_pair(root=ROOT, week_end=week_end)
        if pair is None:
            raise HTTPException(409, '선택한 주차의 연속 2주 공식 차트가 준비되지 않았어.')
        selected = read_current_selection()
        return build_review_queue(selected, pair, root=ROOT)
    except (CatalogError, ChartValidationError, ReviewQueueError) as exc:
        raise HTTPException(422, str(exc)) from None
    except HTTPException:
        raise
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(422, f'검수 후보 자료 오류: {exc}') from None
    except Exception:
        raise HTTPException(503, '선택곡 데이터베이스를 읽을 수 없어. MySQL 연결을 확인해 줘.') from None


@router.get('/selection')
def current_news_selection(week_end: str = ''):
    if week_end and week_end != '2026-10-08':
        from news.weekly_facts import build_draft
        try:
            facts, snapshot = _selection(week_end)
        except HTTPException as exc:
            if exc.status_code not in (409, 422):
                raise
            try:
                draft = build_draft(ROOT, week_end)
            except (OSError, ValueError, KeyError, TypeError):
                raise HTTPException(409, '등록 원본·기간·SHA-256 확인이 필요합니다.') from None
            selected = read_current_selection()
            return {'selected_tracks': selected, 'approved_tracks': [],
                    'excluded_tracks': [{'artist': r['artist'], 'track': r['track'],
                                         'reason': '해당 주차 곡·버전·편집 분류 검수 필요'} for r in selected],
                    'can_generate': False, 'fact_week_end': week_end, 'fact_status': 'DRAFT',
                    'week_warning': str(exc.detail), 'candidate_count': len(draft['candidates']),
                    'publication_approved': False}
    else:
        facts, snapshot = _selection()
    response = _public_selection(snapshot)
    fact_week_end = facts['week_current']['end']
    response['fact_week_end'] = fact_week_end
    response['fact_status'] = facts['review_stage']
    if week_end and week_end != fact_week_end:
        response['can_generate'] = False
        response['week_warning'] = '선택한 차트 주차의 교차 검수된 Fact Sheet가 아직 없어.'
    return response


@router.get('/preview')
def preview_selected_article(week_end: str = ''):
    facts, snapshot = _selection(week_end) if week_end and week_end != '2026-10-08' else _selection()
    if week_end and week_end != facts['week_current']['end']:
        raise HTTPException(409, '현재 비교 주차의 Fact Sheet 검수가 완료되지 않아 기사 생성을 중단했어.')
    try:
        evidence = evidence_for_selected(facts, snapshot)
    except SelectionError as e:
        raise HTTPException(422, str(e)) from None
    return {
        'article': preview_text(evidence),
        'mode': 'template',
        'ai_generated_now': False,
        'selection': _public_selection(snapshot),
        'source': ('facts/article_ready_fact_sheet_20261008.json' if facts['week_current']['end'] == '2026-10-08'
                   else f"facts/weekly/{facts['week_current']['end']}/reviewed.json"),
        'review_required': True,
        'publication_approved': False,
    }


@router.get('/article')
def get_saved_article(variant: str = 'edited', week_end: str = '2026-10-08'):
    if week_end != '2026-10-08':
        raise HTTPException(409, '이 저장 기사 예시는 10/08 주차 전용입니다. 선택 주차의 무료 미리보기를 사용하세요.')
    paths = {
        'edited': ARTICLES / 'revised_editorial_v1_20261008.md',
        'ai': ARTICLES / 'draft_openai_20261008.md',
        'template': ARTICLES / 'draft_template_20261008.md',
    }
    if variant not in paths:
        raise HTTPException(422, '허용된 기사 종류는 edited, ai, template입니다.')
    try:
        article = paths[variant].read_text(encoding='utf-8').strip()
    except FileNotFoundError:
        raise HTTPException(404, '저장된 예시 기사 파일이 없습니다.') from None
    return {
        'article': article,
        'mode': 'saved_example',
        'ai_generated_now': False,
        'source': paths[variant].relative_to(ROOT).as_posix(),
        'review_required': True,
        'publication_approved': False,
        'note': '이 예시 기사는 현재 선택과 무관한 기존 Animal·SaWaDiKa 자료입니다.',
    }


@router.post('/generate')
def generate_selected_article(request: Request, body: GenerateRequest):
    if not _same_origin(request) or request.headers.get('x-requested-with') != 'KpopNewsPanel':
        raise HTTPException(403, '현재 로컬 웹사이트의 버튼에서만 실행할 수 있습니다.')
    if not request.headers.get('content-type', '').startswith('application/json'):
        raise HTTPException(415, 'JSON 요청만 허용합니다.')
    if body.confirm_paid is not True:
        raise HTTPException(400, '유료 호출 확인이 필요합니다.')
    if not _lock.acquire(blocking=False):
        raise HTTPException(429, '이미 기사 생성이 진행 중입니다.')
    try:
        facts, snapshot = _selection(body.week_end) if body.week_end and body.week_end != '2026-10-08' else _selection()
        if body.week_end and body.week_end != facts['week_current']['end']:
            raise HTTPException(409, '현재 비교 주차와 기사 Fact Sheet 기간이 달라 유료 호출을 차단했어.')
        try:
            evidence = evidence_for_selected(facts, snapshot)
        except SelectionError as e:
            raise HTTPException(422, str(e)) from None
        try:
            article, model = generate_paid_article(evidence)
        except RuntimeError as e:
            raise HTTPException(502, str(e)) from None
        except Exception:
            raise HTTPException(502, '모델 요청 실패: 과금 기록 확인 후 다시 판단하세요.') from None

        timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        stem = 'draft_openai_selected_' + facts['week_current']['end'].replace('-', '') + '_' + timestamp
        ARTICLES.mkdir(parents=True, exist_ok=True)
        md_file, json_file = ARTICLES / (stem + '.md'), ARTICLES / (stem + '.json')
        record = {
            'article': article,
            'mode': 'openai',
            'model': model,
            'created_at_utc': datetime.now(timezone.utc).isoformat(),
            'selected_tracks': snapshot['selected_tracks'],
            'used_tracks': _public_selection(snapshot)['approved_tracks'],
            'excluded_tracks': snapshot['excluded_tracks'],
            'evidence': evidence,
            'generation_provenance': generation_record(evidence),
            'review_required': True,
            'publication_approved': False,
            'article_status': 'DRAFT_NOT_FOR_PUBLICATION',
        }
        try:
            with md_file.open('x', encoding='utf-8') as f:
                f.write(article + '\n')
            with json_file.open('x', encoding='utf-8') as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
        except OSError:
            raise HTTPException(500, '기사 저장 실패. API 호출은 처리됐을 수 있으므로 재시도 전 사용 내역을 확인하세요.') from None
        return {
            'article': article,
            'mode': 'openai',
            'model': model,
            'ai_generated_now': True,
            'selection': _public_selection(snapshot),
            'source': md_file.relative_to(ROOT).as_posix(),
            'review_required': True,
            'publication_approved': False,
        }
    finally:
        _lock.release()
