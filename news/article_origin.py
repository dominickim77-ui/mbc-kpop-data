"""Server-owned, immutable generation receipts and per-version authorship bindings.

Uses existing append-only audit storage; never migrates or backfills old records.
Caller supplied generation JSON and hashes are never trusted as receipts.
"""
import hashlib
import json
import secrets
from pathlib import Path
from fastapi import HTTPException
from security.editorial_store import audit
from news.weekly_facts import digest
from news.provenance import validate_generation_record

def text_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def events(db, action, target=None):
    query='SELECT actor_id,target,data FROM audit WHERE action=?'
    params=[action]
    if target is not None:
        query+=' AND target=?';params.append(str(target))
    return [dict(r) for r in db.execute(query+' ORDER BY id',tuple(params))]

def issue_receipt(db, actor, *, record, output, model, week, evidence_hash):
    validate_generation_record(record)
    if not output or not model:
        raise ValueError('Incomplete generation result')
    rid=secrets.token_hex(24)
    data={'schema':1,'method':'AI','generation':record,'output':output,
          'output_sha256':text_hash(output),'model':model,'week_end':week,
          'evidence_hash':evidence_hash}
    audit(db,actor,'AI_GENERATED',rid,data)
    return rid

def receipt(db, rid, actor):
    found=events(db,'AI_GENERATED',rid)
    if len(found)!=1 or found[0]['actor_id']!=actor:
        raise ValueError('Missing or foreign generation receipt')
    data=json.loads(found[0]['data'])
    if data['schema']!=1 or data['method']!='AI' or not data['model']:
        raise ValueError('Invalid generation method')
    validate_generation_record(data['generation'])
    if text_hash(data['output'])!=data['output_sha256']:
        raise ValueError('Generated output hash mismatch')
    return data

def binding_hash(row):
    return digest({k:row[k] for k in ('id','author_id','title','body','week_end','version','evidence_hash')})

def known_ai_body(db, body, root):
    # Known exact copies cannot be relabelled HUMAN. This is not an AI detector.
    target=text_hash(body.strip())
    for p in (Path(root)/'articles').glob('draft_openai*.json'):
        obj=json.loads(p.read_text(encoding='utf-8'))
        if isinstance(obj.get('article'),str) and text_hash(obj['article'].strip())==target:
            return True
        md=p.with_suffix('.md')
        if md.is_file() and text_hash(md.read_text(encoding='utf-8').strip())==target:
            return True
    return any(text_hash(json.loads(e['data'])['output'].strip())==target for e in events(db,'AI_GENERATED'))

def bind(db,row,actor,body,root,previous=None):
    origin=body.origin
    # A known AI/Legacy lineage cannot be downgraded by editing the request label.
    if previous:
        prior=[json.loads(e['data']) for e in events(db,'ARTICLE_ORIGIN',row['id'])]
        if any(e.get('origin') in ('AI','LEGACY') for e in prior) and origin not in ('AI','LEGACY'):
            raise HTTPException(409,'AI·Legacy 기사를 직접 작성 기사로 변경할 수 없습니다.')
    if origin=='HUMAN':
        if not body.human_authored or body.generation_id:
            raise HTTPException(409,'직접 작성 확인이 필요합니다. AI 생성 기록을 함께 사용할 수 없습니다.')
        if known_ai_body(db,row['body'],root):
            raise HTTPException(409,'알려진 AI 초안은 직접 작성 기사로 등록할 수 없습니다.')
    elif origin=='AI' and not body.generation_id:
        raise HTTPException(409,'AI 기사는 실제 생성 기록이 필요합니다. 근거가 없는 초안을 새 기사로 저장할 수 없습니다.')
    elif origin=='AI' and body.generation_id:
        try:
            rec=receipt(db,body.generation_id,actor)
            if (row['body']!=rec['output'] or row['week_end']!=rec['week_end']
                    or row['evidence_hash']!=rec['evidence_hash']):
                raise ValueError('Output, week or evidence changed')
            for event in events(db,'ARTICLE_ORIGIN'):
                prior=json.loads(event['data'])
                if prior.get('generation_id')==body.generation_id and event['target']!=str(row['id']):
                    raise ValueError('Receipt already bound to another article')
        except (ValueError,KeyError,TypeError,AttributeError):
            raise HTTPException(409,'생성 기록과 작성자·본문·주차·근거가 일치하지 않습니다.') from None
    elif origin not in ('AI','UNKNOWN','LEGACY') or body.generation_id or body.human_authored:
        raise HTTPException(409,'작성 방식과 생성 기록의 조합이 올바르지 않습니다.')
    audit(db,actor,'ARTICLE_ORIGIN',row['id'],{'schema':1,'version':row['version'],
          'origin':origin,'human_authored':body.human_authored,'generation_id':body.generation_id,
          'binding_sha256':binding_hash(row)})

def eligible(db,row):
    try:
        if digest(json.loads(row['evidence']))!=row['evidence_hash']:
            return False
        matches=[e for e in events(db,'ARTICLE_ORIGIN',row['id'])
                 if json.loads(e['data']).get('version')==row['version']]
        if len(matches)!=1 or matches[0]['actor_id']!=row['author_id']:
            return False
        b=json.loads(matches[0]['data'])
        if b['schema']!=1 or b['binding_sha256']!=binding_hash(row):
            return False
        if b['origin']=='HUMAN':
            return b['human_authored'] is True and not b['generation_id']
        if b['origin']!='AI' or not b['generation_id']:
            return False
        rec=receipt(db,b['generation_id'],row['author_id'])
        return (rec['output']==row['body'] and rec['week_end']==row['week_end']
                and rec['evidence_hash']==row['evidence_hash'])
    except (ValueError,KeyError,TypeError,AttributeError):
        return False

def require_eligible(db,row):
    if not eligible(db,row):
        raise HTTPException(409,'작성 출처 또는 생성 근거가 해당 기사 버전과 연결되지 않았습니다. Legacy는 재현성 미확인 상태로 보존합니다.')

def approved_version(db,row):
    """Status alone is insufficient: require genuine current-version human review."""
    if not eligible(db,row):return False
    reviews=db.execute('SELECT reviewer_id,evidence_hash,checklist,decision FROM reviews WHERE article_id=? AND version=?',
                       (row['id'],row['version'])).fetchall()
    for r in reviews:
        try:
            checks=json.loads(r['checklist'])
            if (r['decision']=='APPROVED' and r['reviewer_id']!=row['author_id']
                and r['evidence_hash']==row['evidence_hash']
                and all(checks.get(k) is True for k in ('numbers','period_units','no_unsupported_claims','sources'))):
                for e in events(db,'ARTICLE_REVIEWED',row['id']):
                    d=json.loads(e['data'])
                    if (e['actor_id']==r['reviewer_id'] and d.get('version')==row['version']
                        and d.get('decision')=='APPROVED' and d.get('authorship_confirmed') is True
                        and d.get('binding_sha256')==binding_hash(row)):
                        return True
        except (ValueError,KeyError,TypeError,AttributeError):
            continue
    return False
