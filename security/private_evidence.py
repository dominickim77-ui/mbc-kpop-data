"""Exact evidence bytes in the existing immutable audit table; no new grants."""
import base64
import hashlib
import json
import re
from fastapi import HTTPException
from security.editorial_store import audit

ACTION = 'PRIVATE_EVIDENCE_V1'
MAX_BYTES = 1024 * 1024
SOURCE_KEYS = frozenset(('spotify_previous','spotify_current','youtube_previous','youtube_current'))


def _source_bytes(evidence):
    from news.selected_news import ROOT
    from news.chart_import import safe_path
    hashes=evidence['source_sha256']
    if not isinstance(hashes,dict) or set(hashes)!=SOURCE_KEYS:
        raise ValueError('All four registered source CSVs are required')
    refs=evidence['facts'].get('source_refs')
    if refs is None:
        from news.chart_data_manager import choose_pair
        pair=choose_pair(root=ROOT,week_end=evidence['facts']['week_current']['end'])[0]
        if pair is None:raise ValueError('Missing registered source pair')
        paths=pair.files
    else:
        if set(refs)!=SOURCE_KEYS:raise ValueError('Incomplete Fact Sheet source references')
        paths={key:refs[key]['path'] for key in SOURCE_KEYS}
        if any(refs[key]['sha256']!=hashes[key] for key in SOURCE_KEYS):
            raise ValueError('Fact Sheet/source hash mismatch')
    if len(set(paths.values()))!=4:raise ValueError('Duplicate source paths')
    objects={}
    for key in sorted(SOURCE_KEYS):
        if not re.fullmatch(r'[a-f0-9]{64}',hashes[key]):raise ValueError('Invalid source hash')
        raw=safe_path(ROOT,paths[key]).read_bytes()
        if not raw or hashlib.sha256(raw).hexdigest()!=hashes[key]:
            raise ValueError('Source bytes missing or changed')
        objects[paths[key]]=raw
    return objects


def _fact_bytes(db,article):
    ref=article['fact_ref']
    prefix='editorial-db:fact_reviews/'
    if ref.startswith(prefix):
        rid=ref[len(prefix):]
        if not re.fullmatch(r'[1-9][0-9]*',rid):raise ValueError('Invalid Fact Sheet reference')
        row=db.execute('SELECT week_end,facts FROM fact_reviews WHERE id=?',(int(rid),)).fetchone()
        if row is None or row['week_end']!=article['week_end']:raise ValueError('Stored Fact Sheet missing or wrong week')
        return row['facts'].encode('utf-8')
    from news.selected_news import ROOT
    from news.chart_import import safe_path
    return safe_path(ROOT,ref).read_bytes()


def expected_objects(db,article,evidence):
    from news.weekly_facts import digest
    if not isinstance(evidence,dict) or digest(evidence)!=article['evidence_hash']:
        raise ValueError('Article evidence hash mismatch')
    if evidence['facts']['week_current']['end']!=article['week_end']:
        raise ValueError('Article/Fact Sheet period mismatch')
    if json.loads(_fact_bytes(db,article))!=evidence['facts']:
        raise ValueError('Actual stored Fact Sheet differs from article evidence')
    objects=_source_bytes(evidence)
    if len(objects)!=4:raise ValueError('Four source CSVs required')
    objects['evidence.json']=json.dumps(evidence,ensure_ascii=False).encode('utf-8')
    return objects


def require_archive(db,article):
    """Require a complete, unique set bound to actual sources, facts and version."""
    try:
        evidence=json.loads(article['evidence'])
        expected=expected_objects(db,article,evidence)
        records=db.execute('SELECT actor_id,target,data FROM audit WHERE action=? AND target LIKE ? ORDER BY id',
            (ACTION,f"{article['id']}:{article['version']}:%")).fetchall()
        if len(records)!=len(expected):raise ValueError('Missing or duplicate archived evidence')
        seen=set();result=[]
        for record in records:
            obj=json.loads(record['data']);name=obj['name']
            if (name not in expected or name in seen or obj['schema']!=1
                    or obj['article_id']!=article['id'] or obj['version']!=article['version']
                    or record['actor_id']!=article['author_id']
                    or record['target']!=f"{article['id']}:{article['version']}:{name}"):
                raise ValueError('Archived evidence binding mismatch')
            raw=verify_record(obj)
            # JSON semantic equality allows formatting differences; both SHA and
            # original CSV bytes must match the actual stored sources exactly.
            if name=='evidence.json':
                if json.loads(raw)!=evidence:raise ValueError('Archived Fact Sheet/evidence mismatch')
            elif raw!=expected[name]:raise ValueError('Archived source differs from actual source')
            seen.add(name);result.append({k:obj[k] for k in ('name','sha256','bytes','version')})
        return sorted(result,key=lambda x:x['name'])
    except PermissionError:
        raise HTTPException(503,'근거 저장소에 접근할 수 없습니다.') from None
    except (ValueError,KeyError,TypeError,UnicodeError,FileNotFoundError):
        raise HTTPException(409,'필수 보관 근거·Fact Sheet·원본·SHA-256 검증에 실패했습니다.') from None
    except Exception:
        raise HTTPException(503,'근거 저장소 확인에 실패했습니다.') from None


def archive(db, actor, article, evidence):
    try:objects=expected_objects(db,article,evidence)
    except PermissionError:raise HTTPException(503,'근거 저장소에 접근할 수 없습니다.') from None
    except (ValueError,KeyError,TypeError,OSError):raise HTTPException(409,'필수 근거가 누락되거나 변경되어 기사를 저장할 수 없습니다.') from None
    for name, content in objects.items():
        if len(content)>MAX_BYTES:
            raise ValueError('Evidence exceeds archival size limit')
        audit(db,actor,ACTION,f"{article['id']}:{article['version']}:{name}",{
            'schema':1,'article_id':article['id'],'version':article['version'],
            'name':name,'sha256':hashlib.sha256(content).hexdigest(),
            'bytes':len(content),'base64':base64.b64encode(content).decode('ascii')})
    require_archive(db,article)


def verify_record(record):
    raw = base64.b64decode(record['base64'],validate=True)
    if (len(raw)>MAX_BYTES or len(raw)!=record['bytes']
            or hashlib.sha256(raw).hexdigest()!=record['sha256']):
        raise ValueError('Immutable evidence hash mismatch')
    return raw
