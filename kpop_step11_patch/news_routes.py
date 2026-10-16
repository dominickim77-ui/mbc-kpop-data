"""Same-page selected-song news endpoints. GET actions are free; POST is paid."""
import json
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

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


def _same_origin(request: Request) -> bool:
    origin = request.headers.get('origin', '')
    host = request.headers.get('host', '')
    return origin in (f'http://{host}', f'https://{host}') and host.split(':')[0] in {'localhost', '127.0.0.1'}


def _selection():
    try:
        facts = load_verified_facts()
        snapshot = selected_snapshot(read_current_selection(), facts)
        return facts, snapshot
    except FileNotFoundError:
        raise HTTPException(404, '기존 검수 완료 Fact Sheet를 찾지 못했습니다.') from None
    except (ValueError, KeyError, TypeError) as e:
        raise HTTPException(422, f'근거 검증 실패: {e}') from None
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


@router.get('/selection')
def current_news_selection():
    _, snapshot = _selection()
    return _public_selection(snapshot)


@router.get('/preview')
def preview_selected_article():
    facts, snapshot = _selection()
    try:
        evidence = evidence_for_selected(facts, snapshot)
    except SelectionError as e:
        raise HTTPException(422, str(e)) from None
    return {
        'article': preview_text(evidence),
        'mode': 'template',
        'ai_generated_now': False,
        'selection': _public_selection(snapshot),
        'source': 'facts/article_ready_fact_sheet_20261008.json',
        'review_required': True,
        'publication_approved': False,
    }


@router.get('/article')
def get_saved_article(variant: str = 'edited'):
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
        facts, snapshot = _selection()
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
        stem = 'draft_openai_selected_' + timestamp
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
