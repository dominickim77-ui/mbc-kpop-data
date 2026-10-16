"""K-POP DATA LAB: 동일 페이지 기사 조회/생성 API (교육용 로컬 서버).

GET  /api/news/article?variant=edited|ai|template : 저장된 기사 읽기 (무료)
POST /api/news/generate {"confirm_paid": true} : OpenAI 요청 1회, 별도 파일 저장

기사 데이터는 news/generation.py의 기존 검증 Fact Sheet만 이용합니다.
기존 검색 화면, MySQL 데이터, 기존 생성 기사 파일을 수정하지 않습니다.
"""
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from news.generation import (
    ROOT, FACT_PATH, check_fact_sheet, generate_openai_article,
)

router = APIRouter(prefix='/api/news', tags=['K-POP News Analysis'])
_lock = threading.Lock()
ARTICLES = ROOT / 'articles'
SAVED_ARTICLES = {
    'edited': ARTICLES / 'revised_editorial_v1_20261008.md',
    'ai': ARTICLES / 'draft_openai_20261008.md',
    'template': ARTICLES / 'draft_template_20261008.md',
}


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    confirm_paid: bool = False


def _read_facts() -> dict:
    try:
        facts = json.loads(FACT_PATH.read_text(encoding='utf-8'))
        check_fact_sheet(facts)
        return facts
    except FileNotFoundError:
        raise HTTPException(404, '기사용 Fact Sheet 파일이 없습니다.') from None
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(422, f'Fact Sheet 검증 실패: {exc}') from None


def _same_origin(request: Request) -> bool:
    # localhost 로컬 교육용: 다른 사이트에서 사용자의 키로 유료 요청하는 상황 방지
    origin = request.headers.get('origin', '')
    host = request.headers.get('host', '')
    return origin in (f'http://{host}', f'https://{host}') and host.split(':')[0] in {'localhost', '127.0.0.1'}


@router.get('/article')
def get_saved_article(variant: str = 'edited'):
    path = SAVED_ARTICLES.get(variant)
    if path is None:
        raise HTTPException(422, '허용된 기사 종류는 edited, ai, template입니다.')
    try:
        content = path.read_text(encoding='utf-8').strip()
    except FileNotFoundError:
        raise HTTPException(404, f'저장된 기사 파일을 찾을 수 없습니다: {path.name}') from None
    return {
        'article': content,
        'source': path.relative_to(ROOT).as_posix(),
        'mode': 'saved_editorial' if variant == 'edited' else variant,
        'ai_generated_now': False,
        'review_required': True,
        'publication_approved': False,
    }


@router.post('/generate')
def generate_article(request: Request, body: GenerateRequest):
    if not _same_origin(request) or request.headers.get('x-requested-with') != 'KpopNewsPanel':
        raise HTTPException(403, '이 기능은 동일한 로컬 웹사이트의 버튼에서만 실행할 수 있습니다.')
    if not request.headers.get('content-type', '').startswith('application/json'):
        raise HTTPException(415, 'JSON 요청만 허용합니다.')
    if body.confirm_paid is not True:
        raise HTTPException(400, 'API 비용 발생 가능성을 확인해야 합니다.')
    if not _lock.acquire(blocking=False):
        raise HTTPException(429, '이미 기사 생성이 진행 중입니다. 완료될 때까지 기다려 주세요.')

    try:
        facts = _read_facts()
        # 아래 함수에서 OpenAI API를 실제로 1번 호출한다. 자동 재시도 없음.
        try:
            article, model = generate_openai_article(facts)
        except RuntimeError as exc:
            raise HTTPException(502, str(exc)) from None
        except Exception:
            raise HTTPException(502, 'AI 기사 생성 요청이 실패했습니다. 재시도 전 API 사용 내역을 확인하세요.') from None
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        stem = f'draft_openai_web_{timestamp}'
        ARTICLES.mkdir(parents=True, exist_ok=True)
        md_path = ARTICLES / f'{stem}.md'
        json_path = ARTICLES / f'{stem}.json'
        result = {
            'article': article,
            'mode': 'openai',
            'model': model,
            'created_at_utc': datetime.now(timezone.utc).isoformat(),
            'fact_sheet': FACT_PATH.relative_to(ROOT).as_posix(),
            'review_required': True,
            'publication_approved': False,
            'article_status': 'DRAFT_NOT_FOR_PUBLICATION',
        }
        # 각각 새 이름으로 생성하므로 기존 기사 및 편집 수정본을 덮어쓰지 않는다.
        try:
            with md_path.open('x', encoding='utf-8') as fp:
                fp.write(article + '\n')
            with json_path.open('x', encoding='utf-8') as fp:
                json.dump(result, fp, ensure_ascii=False, indent=2)
        except OSError:
            raise HTTPException(500, '기사 저장 실패. API 요청은 발생했을 수 있으니 무작정 다시 누르지 마세요.') from None
        return {
            'article': article,
            'source': md_path.relative_to(ROOT).as_posix(),
            'mode': 'openai',
            'model': model,
            'ai_generated_now': True,
            'review_required': True,
            'publication_approved': False,
        }
    finally:
        _lock.release()
