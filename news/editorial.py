"""Human article approval, independent of song/video/data approval."""
import hashlib
import json
from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from security.auth import require_role, STAFF
from security.editorial_store import connect, audit
from news import selected_news
from news.weekly_facts import digest, fact_path

router = APIRouter(prefix='/api/editorial', tags=['Editorial'])


class FactReviewInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    draft_sha256: str
    period_evidence: str = Field(min_length=1, max_length=5000)
    period_review: str
    tracks: list[dict] = Field(max_length=300)


@router.get('/fact-drafts/{week}')
def fact_draft(week: str):
    require_role('EDITOR', 'ADMIN')
    from news.weekly_facts import build_draft
    try:
        return build_draft(selected_news.ROOT, week)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(409, str(exc)) from None


@router.post('/fact-drafts/{week}/review')
def review_fact_draft(week: str, body: FactReviewInput):
    user = require_role('EDITOR', 'ADMIN')
    if week == '2026-10-08':
        raise HTTPException(409, '기존 10/08 검수는 보존합니다.')
    from datetime import datetime, timezone
    from news.weekly_facts import build_draft, apply_review
    try:
        draft = build_draft(selected_news.ROOT, week)
        review = dict(body.model_dump(), week_end=week, reviewer=f"user:{user['id']}",
                      reviewed_at=datetime.now(timezone.utc).isoformat())
        facts = apply_review(draft, review)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(409, str(exc)) from None
    with connect(True) as db:
        rid = db.execute('INSERT INTO fact_reviews(week_end,reviewer_id,facts) VALUES(?,?,?)',
                         (week, user['id'], json.dumps(facts, ensure_ascii=False))).lastrowid
        audit(db, user['id'], 'FACT_REVIEWED', rid, {'week': week, 'draft_sha256': draft['draft_sha256']})
    return {'id': rid, 'week_end': week, 'article_publication_approved': False}


def fresh_evidence(week):
    try:
        if date.fromisoformat(week).isoformat() != week:
            raise ValueError('invalid date')
        facts = selected_news.load_verified_facts(week)
        from news.chart_data_manager import choose_pair
        pair = choose_pair(root=selected_news.ROOT, week_end=week)[0]
        if not pair:
            raise ValueError('missing sources')
        source_hashes = {name: hashlib.sha256((selected_news.ROOT / path).read_bytes()).hexdigest()
                         for name, path in pair.files.items()}
        evidence = {'facts': facts, 'source_sha256': source_hashes}
        ref = fact_path(selected_news.ROOT, week).relative_to(selected_news.ROOT).as_posix()
        from security.editorial_store import available
        from news.weekly_facts import ROOT
        if week != '2026-10-08' and selected_news.ROOT.resolve() == ROOT.resolve() and available():
            with connect() as db:
                row = db.execute('SELECT id FROM fact_reviews WHERE week_end=? ORDER BY id DESC LIMIT 1', (week,)).fetchone()
            if row: ref = f"editorial-db:fact_reviews/{row['id']}"
        return evidence, digest(evidence), ref
    except (ValueError, OSError, KeyError, TypeError) as exc:
        raise HTTPException(409, 'Fact Sheet·원본·주차 검증 실패: ' + str(exc)) from None


def readable(db, aid, user):
    row = db.execute('SELECT * FROM articles WHERE id=?', (aid,)).fetchone()
    if not row or (user['role'] not in {'EDITOR', 'ADMIN'} and row['author_id'] != user['id']):
        raise HTTPException(404, '접근 가능한 기사가 없습니다.')
    return dict(row)


def save_revision(db, row, actor):
    db.execute('INSERT INTO revisions(article_id,version,actor_id,snapshot) VALUES(?,?,?,?)',
               (row['id'], row['version'], actor, json.dumps(row, ensure_ascii=False)))


class ArticleInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=100000)
    week_end: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}$')


class ArticleEdit(ArticleInput):
    expected_version: int = Field(ge=1)


class VersionInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_version: int = Field(ge=1)


class Checklist(BaseModel):
    model_config = ConfigDict(extra='forbid')
    numbers: StrictBool
    period_units: StrictBool
    no_unsupported_claims: StrictBool
    sources: StrictBool


class ReviewInput(VersionInput):
    evidence_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    checklist: Checklist
    comment: str = Field(min_length=1, max_length=5000)
    decision: str = Field(pattern=r'^(APPROVED|ON_HOLD)$')


@router.get('/facts/{week}')
def facts(week: str):
    require_role(*STAFF)
    evidence, fingerprint, ref = fresh_evidence(week)
    return {'evidence': evidence, 'evidence_hash': fingerprint, 'fact_ref': ref}


@router.get('/articles')
def articles():
    user = require_role(*STAFF)
    with connect() as db:
        sql = 'SELECT id,author_id,title,week_end,status,version,updated_at FROM articles'
        params = ()
        if user['role'] not in {'EDITOR', 'ADMIN'}:
            sql += ' WHERE author_id=?'
            params = (user['id'],)
        return [dict(row) for row in db.execute(sql+' ORDER BY id DESC', params)]


@router.post('/articles', status_code=201)
def create_article(body: ArticleInput):
    user = require_role(*STAFF)
    evidence, fingerprint, ref = fresh_evidence(body.week_end)
    with connect(True) as db:
        aid = db.execute("INSERT INTO articles(author_id,title,body,week_end,fact_ref,evidence,evidence_hash,status) "
                         "VALUES(?,?,?,?,?,?,?,'DRAFT')", (user['id'], body.title, body.body, body.week_end,
                         ref, json.dumps(evidence, ensure_ascii=False), fingerprint)).lastrowid
        row = readable(db, aid, user)
        save_revision(db, row, user['id'])
        audit(db, user['id'], 'ARTICLE_CREATED', aid, {'version': 1})
    return row


@router.get('/articles/{aid}')
def article(aid: int):
    user = require_role(*STAFF)
    with connect() as db:
        row = readable(db, aid, user)
        row['reviews'] = [dict(r) for r in db.execute('SELECT * FROM reviews WHERE article_id=? ORDER BY id', (aid,))]
        row['revisions'] = [dict(r) for r in db.execute('SELECT * FROM revisions WHERE article_id=? ORDER BY version', (aid,))]
    row['evidence'] = json.loads(row['evidence'])
    try:
        current, fingerprint, _ = fresh_evidence(row['week_end'])
        row['evidence_current'] = fingerprint == row['evidence_hash']
        row['current_evidence'] = current
    except HTTPException:
        row['evidence_current'] = False
        row['current_evidence'] = None
    return row


@router.put('/articles/{aid}')
def edit_article(aid: int, body: ArticleEdit):
    user = require_role(*STAFF)
    evidence, fingerprint, ref = fresh_evidence(body.week_end)
    with connect(True) as db:
        row = readable(db, aid, user)
        if row['author_id'] != user['id']:
            raise HTTPException(403, '작성자만 본문을 수정할 수 있습니다.')
        if row['version'] != body.expected_version or row['status'] == 'WITHDRAWN':
            raise HTTPException(409, '기사 버전이나 상태가 변경되었습니다.')
        status = 'DRAFT' if row['status'] == 'DRAFT' else 'REVISED'
        db.execute('UPDATE articles SET title=?,body=?,week_end=?,fact_ref=?,evidence=?,evidence_hash=?, '
                   'version=version+1,status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',
                   (body.title, body.body, body.week_end, ref, json.dumps(evidence, ensure_ascii=False), fingerprint, status, aid))
        row = readable(db, aid, user)
        save_revision(db, row, user['id'])
        audit(db, user['id'], 'ARTICLE_EDITED', aid, {'version': row['version']})
    return row


@router.post('/articles/{aid}/submit')
def submit(aid: int, body: VersionInput):
    user = require_role(*STAFF)
    with connect(True) as db:
        row = readable(db, aid, user)
        if row['author_id'] != user['id']:
            raise HTTPException(403, '작성자만 검수를 요청할 수 있습니다.')
        if row['version'] != body.expected_version or row['status'] not in {'DRAFT', 'REVISED'}:
            raise HTTPException(409, '수정한 최신 기사만 검수를 요청할 수 있습니다.')
        if fresh_evidence(row['week_end'])[1] != row['evidence_hash']:
            raise HTTPException(409, '근거가 변경되었습니다. 기사를 다시 저장하세요.')
        db.execute("UPDATE articles SET status='PENDING_REVIEW',updated_at=CURRENT_TIMESTAMP WHERE id=?", (aid,))
        audit(db, user['id'], 'REVIEW_REQUESTED', aid, {'version': row['version']})
    return {'id': aid, 'status': 'PENDING_REVIEW'}


@router.post('/articles/{aid}/review')
def review(aid: int, body: ReviewInput):
    user = require_role('EDITOR', 'ADMIN')
    if not body.comment.strip():
        raise HTTPException(422, '검수 사유를 입력하세요.')
    with connect(True) as db:
        row = readable(db, aid, user)
        if row['author_id'] == user['id']:
            raise HTTPException(403, '자신이 작성한 기사는 다른 편집자가 검수해야 합니다.')
        if row['status'] != 'PENDING_REVIEW' or row['version'] != body.expected_version:
            raise HTTPException(409, '검수 대기 상태 또는 기사 버전이 달라졌습니다.')
        if body.evidence_hash != row['evidence_hash'] or fresh_evidence(row['week_end'])[1] != row['evidence_hash']:
            raise HTTPException(409, '근거 지문이 변경되었습니다. 수정 후 재검수가 필요합니다.')
        checks = body.checklist.model_dump()
        decision = body.decision if all(checks.values()) else 'ON_HOLD'
        db.execute('INSERT INTO reviews(article_id,version,reviewer_id,evidence_hash,checklist,comment,decision) '
                   'VALUES(?,?,?,?,?,?,?)', (aid, row['version'], user['id'], row['evidence_hash'],
                   json.dumps(checks), body.comment.strip(), decision))
        db.execute('UPDATE articles SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?', (decision, aid))
        audit(db, user['id'], 'ARTICLE_REVIEWED', aid, {'version': row['version'], 'decision': decision})
    return {'id': aid, 'status': decision, 'approval_blocked': decision != body.decision}


@router.post('/articles/{aid}/withdraw')
def withdraw(aid: int, body: VersionInput):
    user = require_role(*STAFF)
    with connect(True) as db:
        row = readable(db, aid, user)
        if row['author_id'] != user['id'] and user['role'] not in {'EDITOR', 'ADMIN'}:
            raise HTTPException(403, '철회 권한이 없습니다.')
        if row['version'] != body.expected_version or row['status'] == 'WITHDRAWN':
            raise HTTPException(409, '기사 상태가 변경되었습니다.')
        db.execute("UPDATE articles SET status='WITHDRAWN',updated_at=CURRENT_TIMESTAMP WHERE id=?", (aid,))
        audit(db, user['id'], 'ARTICLE_WITHDRAWN', aid, {'version': row['version']})
    return {'id': aid, 'status': 'WITHDRAWN'}


@router.get('/published')
def published():
    require_role()
    with connect() as db:
        rows = [dict(r) for r in db.execute("SELECT * FROM articles WHERE status='APPROVED'")]
    result = []
    for row in rows:
        try:
            valid = fresh_evidence(row['week_end'])[1] == row['evidence_hash']
        except HTTPException:
            valid = False
        if valid:
            result.append({k: row[k] for k in ('id','title','body','week_end','fact_ref','version','updated_at')})
    return result
