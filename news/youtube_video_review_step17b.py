"""STEP 17B: human-reviewed YouTube VIDEO identity, distinct from weekly song charts.

Searching costs YouTube Data API quota. Searching NEVER approves a video or writes DB.
Only explicit, fresh, same-origin operator confirmation can insert a new video snapshot.
No old youtube_stats rows are deleted or modified.
"""
from __future__ import annotations

import csv
import html
import ipaddress
import json
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parent.parent
REVIEW_DIR = ROOT / 'facts' / 'youtube_video_reviews'
VIDEO_ID = re.compile(r'^[A-Za-z0-9_-]{11}$')
ROUTER_PREFIX = '/api/youtube-video-review'
router = APIRouter(prefix=ROUTER_PREFIX, tags=['YouTube Video Identity Review'])

# Local educational server only; cache expires after 15 minutes or restart.
_sessions: dict[str, dict] = {}
_cache_lock = threading.Lock()
_CACHE_SECONDS = 900


def _video_id_from_url(url: str) -> str | None:
    try:
        parsed = urlparse(url)
        if parsed.scheme != 'https' or parsed.netloc.lower() not in {'www.youtube.com', 'youtube.com'} or parsed.path != '/watch':
            return None
        ids = parse_qs(parsed.query).get('v', [])
        return ids[0] if len(ids) == 1 and VIDEO_ID.fullmatch(ids[0]) else None
    except (TypeError, ValueError):
        return None


def _chart_reference(artist: str, track: str, week_end: str) -> str | None:
    """The official weekly CSV's link is a REPRESENTATIVE VIDEO, not a review approval."""
    from news.chart_data_manager import choose_pair
    from news.weekly_chart_analysis import song_key

    pair, _, _ = choose_pair(root=ROOT, week_end=week_end)
    if pair is None:
        return None
    file = ROOT / pair.youtube_current
    key = song_key(artist, track)
    matches = []
    with file.open('r', encoding='utf-8-sig', newline='') as fh:
        for row in csv.DictReader(fh):
            if song_key(row['Artist Names'], row['Track Name']) == key:
                video = _video_id_from_url(row.get('YouTube URL', ''))
                if video:
                    matches.append(video)
    return matches[0] if len(matches) == 1 else None


def _candidate_hint(title: str) -> str:
    """Only editorial cues, never automatic 'official' classification."""
    normalized = title.casefold()
    words = {
        'remix': '리믹스 가능성', 'live': '라이브 영상 가능성',
        'reaction': '리액션 영상 가능성', 'cover': '커버 영상 가능성',
        'dance practice': '댄스 연습 영상 가능성', 'lyrics': '가사 영상 가능성',
        'lyric video': '가사 영상 가능성', 'sped up': '변속 버전 가능성',
    }
    return ' · '.join(text for term, text in words.items() if term in normalized) or '버전·채널 확인 필요'


def _require_local_request(request: Request, *, approval: bool = False) -> None:
    host_header = request.headers.get('host', '')
    hostname = host_header.rsplit(':', 1)[0].strip('[]')
    try:
        is_loopback = hostname == 'localhost' or ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        is_loopback = False
    if not is_loopback or request.headers.get('x-requested-with') != 'KpopYouTubeReview':
        raise HTTPException(403, '로컬 K-POP DATA LAB 검수 버튼에서만 사용할 수 있습니다.')
    if approval and request.headers.get('origin') != 'http://' + host_header:
        raise HTTPException(403, '동일 출처의 명시적 승인 요청이 필요합니다.')


def _get_selected_track(song_id: int) -> dict:
    import app as site
    if song_id not in site.analysis_song_ids:
        raise HTTPException(409, '현재 Current Analysis에서 선택하지 않은 곡입니다.')
    db = site.get_db_connection()
    cur = None
    try:
        cur = db.cursor(dictionary=True)
        cur.execute('SELECT song_id, artist, track FROM tracks WHERE song_id=%s', (song_id,))
        result = cur.fetchone()
        if result is None:
            raise HTTPException(404, '곡 정보를 찾을 수 없습니다.')
        return result
    finally:
        if cur is not None:
            cur.close()
        db.close()


def _youtube_json(endpoint: str, params: dict) -> dict:
    """Never expose URL/error details because API requests contain a secret key."""
    try:
        response = requests.get('https://www.googleapis.com/youtube/v3/' + endpoint, params=params, timeout=12)
    except requests.RequestException:
        raise HTTPException(502, 'YouTube API 네트워크 요청 실패. 서버 연결을 확인해 주세요.') from None
    if response.status_code == 403:
        raise HTTPException(429, 'YouTube API 할당량 또는 접근 권한을 확인해 주세요.')
    if response.status_code in (400, 401):
        raise HTTPException(502, 'YouTube API 키 또는 요청 권한을 확인해 주세요.')
    if not response.ok:
        raise HTTPException(502, 'YouTube API 응답 오류가 발생했습니다.')
    try:
        data = response.json()
    except ValueError:
        raise HTTPException(502, 'YouTube API 결과가 JSON이 아닙니다.') from None
    if not isinstance(data, dict):
        raise HTTPException(502, 'YouTube API 결과 형식이 올바르지 않습니다.')
    return data


def _prune_cache(now: float) -> None:
    for token, info in list(_sessions.items()):
        if now - info['at'] > _CACHE_SECONDS:
            _sessions.pop(token, None)
    if len(_sessions) > 50:
        for token in sorted(_sessions, key=lambda x: _sessions[x]['at'])[:-50]:
            _sessions.pop(token, None)


def _video_stats(item: dict) -> dict:
    video_id = item.get('id', '')
    snippet = item.get('snippet') or {}
    stats = item.get('statistics') or {}
    if not VIDEO_ID.fullmatch(str(video_id)) or not isinstance(snippet, dict):
        raise HTTPException(502, 'YouTube 영상 정보 형식이 올바르지 않습니다.')
    try:
        views = int(stats['viewCount'])
        # Do not invent 0 for hidden/unpublished like or comment counts.
        likes = int(stats['likeCount'])
        comments = int(stats['commentCount'])
        if min(views, likes, comments) < 0:
            raise ValueError()
    except (TypeError, KeyError, ValueError):
        raise HTTPException(422, '선택된 영상의 공개 통계값이 없어 DB 저장을 중단했습니다.') from None
    return dict(video_id=video_id, title=html.unescape(str(snippet.get('title', ''))),
                channel_title=str(snippet.get('channelTitle', '')),
                channel_id=str(snippet.get('channelId', '')),
                published_at=str(snippet.get('publishedAt', '')),
                cumulative_views=views, cumulative_likes=likes,
                cumulative_comments=comments)


def _detail_list(video_ids: list[str], api_key: str) -> list[dict]:
    if not video_ids:
        return []
    data = _youtube_json('videos', {'part': 'snippet,statistics,contentDetails',
                                    'id': ','.join(video_ids), 'key': api_key})
    valid = []
    for item in data.get('items', []):
        try:
            valid.append(_video_stats(item))
        except HTTPException:
            # Existing MySQL schema requires full numeric video statistics.
            # Never replace unavailable likes/comments with fabricated zero.
            continue
    return valid


def video_review_status(song_id: int, current_video_id: str | None) -> str:
    """An old DB row is not approved merely because it exists."""
    if not current_video_id or not VIDEO_ID.fullmatch(str(current_video_id)):
        return 'PENDING_NO_VIDEO'
    if not REVIEW_DIR.is_dir():
        return 'LEGACY_UNVERIFIED'
    for path in sorted(REVIEW_DIR.glob(f'song_{song_id}_*.json'), reverse=True):
        try:
            record = json.loads(path.read_text(encoding='utf-8'))
            if record.get('db_status') == 'DB_STORED' and record.get('video_id') == current_video_id:
                return 'MANUALLY_APPROVED'
        except (OSError, ValueError):
            continue
    return 'LEGACY_UNVERIFIED'


@router.get('/candidates')
def get_candidates(request: Request, song_id: int, week_end: str = ''):
    _require_local_request(request)
    track = _get_selected_track(song_id)
    from news.chart_data_manager import choose_pair, CatalogError
    try:
        pair, _, _ = choose_pair(root=ROOT, week_end=week_end)
    except CatalogError as exc:
        raise HTTPException(422, str(exc)) from None
    if pair is None:
        raise HTTPException(422, '선택 가능한 주간 차트가 없습니다.')
    week_end = pair.current_end.isoformat()
    key = os.getenv('YOUTUBE_API_KEY', '').strip()
    if not key:
        raise HTTPException(503, '.env에 YOUTUBE_API_KEY가 설정되어 있지 않습니다.')
    now = time.monotonic()
    with _cache_lock:
        _prune_cache(now)
        for token, obj in _sessions.items():
            if obj['song_id'] == song_id and obj['week_end'] == week_end:
                return dict(song_id=song_id, artist=track['artist'], track=track['track'],
                            review_token=token, candidates=obj['candidates'], cached=True,
                            approval_required=True, statistics_kind='INDIVIDUAL_VIDEO_LIFETIME')
    query = f"{track['artist']} {track['track']} official music video"
    search = _youtube_json('search', {'part': 'snippet', 'q': query,
                                      'type': 'video', 'maxResults': 5, 'key': key})
    ids = []
    for item in search.get('items', []):
        video_id = (item.get('id') or {}).get('videoId', '')
        if VIDEO_ID.fullmatch(str(video_id)) and video_id not in ids:
            ids.append(video_id)
    try:
        reference_id = _chart_reference(track['artist'], track['track'], week_end)
    except (OSError, ValueError, KeyError):
        reference_id = None
    if reference_id and reference_id not in ids:
        ids.append(reference_id)
    details = _detail_list(ids, key)
    candidates = [dict(**d,
                       video_url='https://www.youtube.com/watch?v=' + d['video_id'],
                       source=('WEEKLY_CHART_REFERENCE' if d['video_id'] == reference_id else 'SEARCH_RESULT'),
                       review_hint=_candidate_hint(d['title']),
                       status='PENDING_HUMAN_REVIEW') for d in details]
    if not candidates:
        raise HTTPException(404, '검토 가능한 영상 후보를 찾지 못했습니다. 자동 매칭은 하지 않습니다.')
    token = uuid.uuid4().hex
    with _cache_lock:
        _prune_cache(now)
        _sessions[token] = dict(at=now, song_id=song_id, week_end=week_end,
                                candidates=candidates)
    return dict(song_id=song_id, artist=track['artist'], track=track['track'],
                review_token=token, candidates=candidates, cached=False,
                approval_required=True, statistics_kind='INDIVIDUAL_VIDEO_LIFETIME')


class ApproveRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    song_id: int = Field(ge=1)
    video_id: str
    review_token: str
    verified_channel: bool
    verified_track_version: bool
    understood_lifetime_metric: bool


@router.post('/approve')
def approve_video(request: Request, body: ApproveRequest):
    _require_local_request(request, approval=True)
    if not all((body.verified_channel, body.verified_track_version,
                body.understood_lifetime_metric)):
        raise HTTPException(422, '공식 채널·곡 버전·누적 조회수 조건을 직접 확인해야 합니다.')
    if not VIDEO_ID.fullmatch(body.video_id):
        raise HTTPException(422, '유효하지 않은 YouTube Video ID입니다.')
    with _cache_lock:
        _prune_cache(time.monotonic())
        session = _sessions.get(body.review_token)
        if session is None or session['song_id'] != body.song_id:
            raise HTTPException(409, '검수 세션이 만료됐습니다. 후보를 다시 검색해 주세요.')
        matches = [x for x in session['candidates'] if x['video_id'] == body.video_id]
        if len(matches) != 1:
            raise HTTPException(422, '후보 목록에 없는 영상은 승인할 수 없습니다.')
        candidate = matches[0]
        # One-use token. Prevent repeated clicks/double DB insert.
        _sessions.pop(body.review_token, None)
    track = _get_selected_track(body.song_id)
    key = os.getenv('YOUTUBE_API_KEY', '').strip()
    if not key:
        raise HTTPException(503, '.env에 YOUTUBE_API_KEY가 없습니다.')
    details = _detail_list([body.video_id], key)
    if len(details) != 1 or details[0]['channel_id'] != candidate['channel_id']:
        raise HTTPException(409, '영상 상세 정보가 변경됐습니다. 후보를 다시 검토해 주세요.')
    new = details[0]
    now = datetime.now(timezone.utc)
    collected_at_utc = now.replace(tzinfo=None)
    approval_id = now.strftime('%Y%m%dT%H%M%S%fZ') + '_' + uuid.uuid4().hex[:8]
    record = dict(status='VIDEO_IDENTITY_REVIEW', db_status='PENDING_DB_WRITE',
                  song_id=body.song_id, artist=track['artist'], track=track['track'],
                  video_id=body.video_id, video_title=new['title'],
                  youtube_channel=new['channel_title'], channel_id=new['channel_id'],
                  approved_at_utc=now.isoformat(), week_end=session['week_end'],
                  manually_checked_channel=True, manually_checked_track_version=True,
                  cumulative_view_count=new['cumulative_views'],
                  youtube_metric='INDIVIDUAL_VIDEO_LIFETIME',
                  publication_approved=False,
                  original_candidate=candidate)
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    output = REVIEW_DIR / f'song_{body.song_id}_{approval_id}.json'
    with output.open('x', encoding='utf-8') as fh:
        json.dump(record, fh, ensure_ascii=False, indent=2)

    import app as site
    connection = None
    cursor = None
    committed = False
    try:
        connection = site.get_db_connection()
        cursor = connection.cursor()
        cursor.execute('''INSERT INTO youtube_stats
            (song_id, youtube_video_id, youtube_title, youtube_channel,
             youtube_views, youtube_likes, youtube_comments, collected_at)
             VALUES (%s,%s,%s,%s,%s,%s,%s,%s)''',
             (body.song_id, new['video_id'], new['title'], new['channel_title'],
              new['cumulative_views'], new['cumulative_likes'],
              new['cumulative_comments'], collected_at_utc))
        connection.commit()
        committed = True
    except Exception:
        if connection is not None:
            connection.rollback()
        output.unlink(missing_ok=True)
        raise HTTPException(503, '승인 영상의 DB 저장에 실패했습니다. MySQL 연결을 확인해 주세요.') from None
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()
    if committed:
        record['db_status'] = 'DB_STORED'
        pending = output.with_suffix('.tmp')
        try:
            with pending.open('x', encoding='utf-8') as fh:
                json.dump(record, fh, ensure_ascii=False, indent=2)
            pending.replace(output)
        except OSError:
            raise HTTPException(500, 'DB에는 저장됐지만 검수 기록 완료에 실패했습니다. 재요청 전 관리자 확인이 필요합니다.') from None
    return dict(status='MANUALLY_APPROVED', song_id=body.song_id,
                video_id=body.video_id, cumulative_views=new['cumulative_views'],
                source=output.relative_to(ROOT).as_posix(),
                publication_approved=False)
