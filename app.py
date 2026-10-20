# KPOP_ARTIST_WEEK_SYNC_STEP15
# --------------------------------------------------
# MBC K-POP DATA LAB
# FastAPI 웹 서버
#
# 주요 기능:
#
# 1. Artist 이름 검색
# 2. Spotify Weekly Global Top 200 CSV 검색
# 3. 검색 결과에서 Track 선택
# 4. YouTube Data API 자동 조회
# 5. MySQL에 Spotify + YouTube 데이터 저장
# 6. 선택한 곡만 Current Analysis에 표시
# 7. Spotify / YouTube / Compare를 한 Dashboard에서 확인
# 8. Artist 최대 10명 / Track 최대 10곡
# 9. 개별 곡 제거
# 10. 선택 목록 초기화
#
# 중요:
# 선택 목록 초기화는 MySQL 데이터를 삭제하지 않는다.
# 현재 화면에서 비교 중인 곡 목록만 초기화한다.
# --------------------------------------------------

import os
import html
import requests
import threading

import pandas as pd
import mysql.connector

from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from security.analysis_origin import require_local_analysis_origin

# --------------------------------------------------
# 1. 기본 설정
# --------------------------------------------------

# 현재 Dashboard에서 비교 가능한 최대 Artist 수
BASE_DIR = Path(__file__).resolve().parent
MAX_ARTISTS = 10

# 현재 Dashboard에서 비교 가능한 최대 Track 수
MAX_TRACKS = 10

# Spotify에서 내려받은 원본 CSV
SPOTIFY_CSV_FILE = "regional-global-weekly-2026-10-01.csv"

# 현재 Spotify Weekly Chart 기준 날짜
CHART_DATE = "2026-10-01"


# --------------------------------------------------
# 2. 현재 분석 중인 곡 목록
#
# 여기에 MySQL의 song_id만 저장한다.
#
# 예:
# [1, 3, 6]
#
# MySQL 데이터 자체를 삭제하는 것이 아니라
# 현재 Dashboard에서 보여줄 곡만 기억한다.
#
# 오늘 로컬 실습용이므로
# FastAPI 서버를 완전히 종료하면 초기화된다.
# --------------------------------------------------

from security.auth import UserSelection
analysis_song_ids = UserSelection()
_analysis_write_lock = threading.Lock()


# --------------------------------------------------
# 3. .env 파일 읽기
# --------------------------------------------------

load_dotenv(dotenv_path=BASE_DIR / ".env", override=False)


# --------------------------------------------------
# 4. .env의 환경변수 가져오기
# --------------------------------------------------

# YouTube Data API Key
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

# MySQL 접속 정보
MYSQL_HOST = os.getenv("MYSQL_HOST")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE")


# --------------------------------------------------
# 5. FastAPI 애플리케이션 생성
# --------------------------------------------------

app = FastAPI()
from security.auth import AuthMiddleware, router as auth_router
from news.editorial import router as editorial_router
app.add_middleware(AuthMiddleware)
app.include_router(auth_router)
app.include_router(editorial_router)

@app.get('/account')
def account_page():
    from fastapi.responses import FileResponse
    return FileResponse(BASE_DIR / 'templates/account.html')

@app.get('/editorial')
def editorial_page():
    from fastapi.responses import FileResponse
    return FileResponse(BASE_DIR / 'templates/editorial.html')


# KPOP_NEWS_INLINE_V1: 새 뉴스 라우터만 추가 (기존 라우트 변경 없음)
from news.news_routes import router as news_router
app.include_router(news_router)
from news.youtube_video_review_step17b import router as youtube_identity_router
app.include_router(youtube_identity_router)  # KPOP_YOUTUBE_VIDEO_HUMAN_REVIEW_STEP17B

# KPOP_WEEKLY_CHARTS_STEP12: read official weekly CSVs for Compare/Accumulated Analysis
from news.weekly_chart_analysis import build_weekly_rows, weekly_chart_data, ChartValidationError, song_key
from news.chart_data_manager import choose_pair, CatalogError


# --------------------------------------------------
# 6. static 폴더 연결
#
# CSS / JavaScript / 이미지 같은
# 화면용 파일을 사용할 수 있게 한다.
# --------------------------------------------------

app.mount(
    "/static",
    StaticFiles(directory=BASE_DIR / "static"),
    name="static",
)


# --------------------------------------------------
# 7. templates 폴더 연결
#
# HTML 파일들이 들어 있는 폴더다.
# --------------------------------------------------

templates = Jinja2Templates(directory=BASE_DIR / "templates")

from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler


def analysis_redirect(url, status_code=303):
    """All selection forms return to the shared search/selection workspace."""
    return RedirectResponse(url=url + '#analysis-workspace', status_code=status_code)


@app.exception_handler(RequestValidationError)
async def form_validation_error(request, exc):
    if request.url.path.startswith(('/select-analysis', '/add-analysis', '/remove-analysis/', '/reset-analysis')):
        from fastapi.responses import JSONResponse
        message = '입력값이 올바르지 않습니다. 곡과 비교 기간을 다시 선택해 주세요.'
        if 'text/html' in request.headers.get('accept', ''):
            return analysis_redirect('/?message=' + quote_plus(message), status_code=303)
        return JSONResponse({'detail': message}, status_code=422)
    return await request_validation_exception_handler(request, exc)


@app.post('/select-analysis', dependencies=[Depends(require_local_analysis_origin)])
def select_analysis(selected_ranks: list[int] = Form(default=[]),
                    search_artist: str = Form(default=''), week_end: str = Form(default='')):
    """Personal selection only: validated chart + existing records, no collection."""
    from security.auth import require_role
    require_role()
    message = ''
    with _analysis_write_lock:
        try:
            if not selected_ranks:
                raise ValueError('분석할 곡을 선택해 주세요.')
            ranks = set(selected_ranks)
            if len(ranks) > MAX_TRACKS:
                raise ValueError('곡은 최대 10곡까지 선택할 수 있습니다.')
            chart = load_spotify_csv(week_end)
            chosen = chart[chart['rank'].isin(ranks)]
            if len(chosen) != len(ranks):
                raise ValueError('선택한 곡을 해당 기간의 차트에서 확인할 수 없습니다.')
            rows = get_dashboard_data()  # Read-only. No MySQL commit or external API.
            catalog = {}
            for row in rows:
                catalog.setdefault((row['artist'], row['track']), set()).add(row['song_id'])
            additions = []
            for row in chosen.to_dict('records'):
                candidates = catalog.get((str(row['artist_names']), str(row['track_name'])), set())
                if len(candidates) != 1:
                    raise ValueError('선택한 곡의 저장된 데이터를 확인할 수 없습니다. 운영 담당자의 데이터 확인 후 이용해 주세요. 선택 목록은 변경하지 않았습니다.')
                song_id = next(iter(candidates))
                if song_id not in additions:
                    additions.append(song_id)
            def merge(ids):
                merged = list(dict.fromkeys([*ids, *additions]))
                artists = {r['artist'] for r in rows if r['song_id'] in merged}
                if len(merged) > MAX_TRACKS or len(artists) > MAX_ARTISTS:
                    raise ValueError('아티스트는 최대 10명, 곡은 최대 10곡까지 선택할 수 있습니다.')
                ids[:] = merged
            # Read, enforce limits, and save under SQLite's cross-process write lock.
            analysis_song_ids._change(merge)
            message = '선택한 곡을 개인 분석에 추가했습니다.'
        except (CatalogError, ChartValidationError, OSError, ValueError) as exc:
            message = str(exc)
        except mysql.connector.Error:
            message = '저장된 데이터에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.'
    return analysis_redirect('/?artist=' + quote_plus(search_artist) + '&week_end=' +
                            quote_plus(week_end) + '&message=' + quote_plus(message), status_code=303)


# --------------------------------------------------
# 8. MySQL 연결 함수
#
# DB 데이터가 필요할 때마다
# 이 함수를 호출해서 MySQL에 연결한다.
# --------------------------------------------------


def get_db_connection():

    connection = mysql.connector.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
    )

    return connection


# --------------------------------------------------
# 9. Spotify CSV 읽기 함수
#
# 여러 Route에서 같은 CSV를 사용하므로
# 함수로 만들어 반복을 줄인다.
# --------------------------------------------------


def load_spotify_csv(week_end: str = ""):
    """Load validated Spotify Top 200 for the selected complete comparison week.

    The lookup is read-only; it NEVER falls back to a stale 10/01 chart.
    """
    pair, _, _ = choose_pair(week_end=week_end)
    if pair is None:
        raise CatalogError('연속 2주의 차트 자료가 없어 검색할 수 없습니다.')
    from news.weekly_chart_analysis import read_chart, ROOT as CHART_ROOT
    index = read_chart(CHART_ROOT, pair.spotify_current, 'spotify')
    return pd.DataFrame([
        {'rank': row['rank'], 'artist_names': row['artist'],
         'track_name': row['track'], 'streams': row['amount']}
        for hits in index.values() for row in hits
    ])


# --------------------------------------------------
# 10. Dashboard 데이터 조회 함수
#
# tracks
#      +
# spotify_chart
#      +
# youtube_stats
#
# 세 테이블을 song_id로 연결한다.
#
# Spotify:
# 가장 최근 chart_date
#
# YouTube:
# 가장 최근 collected_at
#
# 데이터를 사용한다.
# --------------------------------------------------


def get_dashboard_data():

    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            t.song_id,
            t.artist,
            t.track,

            s.spotify_rank,
            s.spotify_streams,
            s.chart_date,

            y.youtube_video_id,
            y.youtube_title,
            y.youtube_channel,
            y.youtube_views,
            y.youtube_likes,
            y.youtube_comments,
            y.collected_at

        FROM tracks AS t

        -- 각 곡의 가장 최근 Spotify 기록
        JOIN spotify_chart AS s
            ON t.song_id = s.song_id

            AND s.chart_date = (
                SELECT MAX(s2.chart_date)

                FROM spotify_chart AS s2

                WHERE s2.song_id = t.song_id
            )

        -- 각 곡의 가장 최근 YouTube 기록
        LEFT JOIN youtube_stats AS y
            ON t.song_id = y.song_id

            AND y.collected_at = (
                SELECT MAX(y2.collected_at)

                FROM youtube_stats AS y2

                WHERE y2.song_id = t.song_id
            )
        """)

    dashboard_data = cursor.fetchall()

        # STEP 17B: 사람이 승인한 YouTube 영상을 우선 표시
    from news.youtube_display_resolver import (
        apply_approved_youtube_videos,
    )

    dashboard_data = apply_approved_youtube_videos(
        dashboard_data, cursor, Path(__file__).resolve().parent
    )
    
    from news.youtube_video_review_step17b import video_review_status
    for _record in dashboard_data:
        _record["youtube_review_status"] = video_review_status(
            int(_record["song_id"]), _record.get("youtube_video_id"))

    cursor.close()
    connection.close()

    return dashboard_data


# --------------------------------------------------
# 11. HOME / SINGLE DASHBOARD
#
# 메인 화면 하나에서:
#
# Artist Search
# Spotify
# YouTube
# Compare
# Current Analysis
#
# 를 모두 보여준다.
# --------------------------------------------------


@app.get("/")
def home(
    request: Request,
    artist: str = "",
    message: str = "",
    week_end: str = "",
):

    # --------------------------------------------------
    # 11-1. Artist 검색
    # --------------------------------------------------

    artist = artist.strip()

    search_results = []
    search_message = ""

    if artist:
        try:
            spotify_csv = load_spotify_csv(week_end)
        except (CatalogError, ChartValidationError, OSError, ValueError) as exc:
            spotify_csv = None
            search_message = f'선택한 기간의 Spotify 자료를 사용할 수 없습니다: {exc}'

        # artist_names 컬럼에서 검색어를 찾는다.
        #
        # case=False:
        # BTS / bts 모두 검색 가능
        #
        # na=False:
        # 빈 값 때문에 오류가 나지 않게 한다.
        if spotify_csv is not None:
            matches = spotify_csv[
                spotify_csv["artist_names"].str.contains(
                    artist, case=False, na=False, regex=False
                )
            ]
            matches = matches.sort_values("rank")
            search_results = matches[
                ["rank", "artist_names", "track_name", "streams"]
            ].to_dict("records")

        # 검색 결과가 없는 경우
        if not search_results and not search_message:
            search_message = '검색 결과가 없습니다. 다른 이름으로 검색해 주세요. 검색 범위는 선택한 기간의 Spotify Global Top 200입니다.'

    # --------------------------------------------------
    # 11-2. MySQL 데이터 가져오기
    # --------------------------------------------------

    dashboard_data = get_dashboard_data()

    # --------------------------------------------------
    # 11-3. Current Analysis에 선택된 곡만 필터링
    #
    # MySQL에는 모든 데이터를 보관하지만
    # Dashboard에는 analysis_song_ids에
    # 들어 있는 곡만 보여준다.
    # --------------------------------------------------

    analysis_data = [
        item for item in dashboard_data if item["song_id"] in analysis_song_ids
    ]

    # --------------------------------------------------
    # 11-4. Spotify 영역 정렬
    #
    # Spotify Rank가 높은 곡부터
    # --------------------------------------------------

    spotify_data = sorted(
        analysis_data,
        key=lambda item: item["spotify_rank"],
    )

    # --------------------------------------------------
    # 11-5. YouTube 영역 정렬
    #
    # 조회수가 높은 곡부터
    # --------------------------------------------------

    youtube_data = sorted(
        analysis_data,
        key=lambda item: int(item.get("youtube_views") or -1),
        reverse=True,
    )

    # --------------------------------------------------
    # 11-6. Compare 영역
    #
    # Spotify 순위 순서 사용
    # --------------------------------------------------

    # STEP 12: Article and graphs use the same current selected songs,
    # but chart figures are recomputed from four *weekly raw CSV* files.
    # DO NOT mix the old YouTube Data API video lifetime counts here.
    # KPOP_WEEKLY_MANAGER_STEP13: CSV filename catalog; no MySQL/API/LLM updates.
    try:
        pair, week_pairs, week_notes = choose_pair(week_end=week_end)
        if pair is None:
            weekly_comparison = []
            weekly_chart_error = "동일 기간의 연속 2주 Spotify·YouTube 자료가 없습니다."
        else:
            weekly_comparison = build_weekly_rows(analysis_data, pair=pair)
            weekly_chart_error = None
    except (CatalogError, ChartValidationError, OSError, ValueError) as exc:
        pair = None
        week_pairs = []
        week_notes = []
        weekly_comparison = []
        weekly_chart_error = str(exc)
    weekly_graph = weekly_chart_data(weekly_comparison)
    # STEP15: The Spotify Data table must follow the selected CSV week,
    # NOT the last row in MySQL (which may belong to another week).
    weekly_by_song = {song_key(item['artist'], item['track']): item for item in weekly_comparison}
    spotify_data = []
    for old in analysis_data:
        hit = weekly_by_song.get(song_key(old['artist'], old['track']))
        rank = hit['spotify_curr_rank'] if hit else None
        amount = hit['spotify_current'] if hit else None
        spotify_data.append({**old, 'spotify_rank': rank, 'spotify_streams': amount,
                             'chart_date': pair.current_end.isoformat() if rank is not None else None})
    spotify_data.sort(key=lambda item: (item['spotify_rank'] is None,
                                        item['spotify_rank'] if item['spotify_rank'] is not None else 10**6))
    week_options = [{'end': p.current_end.isoformat(), 'label': p.label} for p in week_pairs]
    selected_week_end = pair.current_end.isoformat() if pair else ''
    previous_week_end = pair.previous_end.strftime('%m/%d') if pair else ''
    current_week_end = pair.current_end.strftime('%m/%d') if pair else ''
    previous_week_start_display = pair.previous_start.strftime('%m/%d') if pair else ''
    current_week_start_display = pair.current_start.strftime('%m/%d') if pair else ''
    selected_period_label = pair.label if pair else '등록된 주차 없음'
    # The panel verifies the selected week's Fact Sheet through /api/news/selection.
    news_week_compatible = bool(pair)

    # --------------------------------------------------
    # Chart 데이터를 JSON 문자열로 변환
    #
    # JavaScript 안에서 Jinja 문법을 직접 쓰지 않고
    # HTML data 속성으로 안전하게 전달하기 위한 단계다.
    # --------------------------------------------------

    # --------------------------------------------------
    # 11-7. 현재 Analysis 상태 계산
    # --------------------------------------------------

    analysis_artists = sorted(set(item["artist"] for item in analysis_data))

    artist_count = len(analysis_artists)

    track_count = len(analysis_data)

    # --------------------------------------------------
    # 11-8. index.html로 데이터 전달
    # --------------------------------------------------

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "title": "K-POP DATA LAB",
            # 검색 관련
            "search_artist": artist,
            "search_results": search_results,
            "search_message": search_message,
            # 알림 메시지
            "message": message,
            # Current Analysis
            "current_analysis": analysis_data,
            "analysis_artists": analysis_artists,
            "artist_count": artist_count,
            "track_count": track_count,
            # 제한
            "max_artists": MAX_ARTISTS,
            "max_tracks": MAX_TRACKS,
            # Dashboard
            "spotify_data": spotify_data,
            "youtube_data": youtube_data,
            "weekly_comparison": weekly_comparison,
            "weekly_chart_error": weekly_chart_error,
            "weekly_chart_data": weekly_graph,
            "week_options": week_options,
            "selected_week_end": selected_week_end,
            "previous_week_end": previous_week_end,
            "current_week_end": current_week_end,
            "previous_week_start_display": previous_week_start_display,
            "current_week_start_display": current_week_start_display,
            "selected_period_label": selected_period_label,
            "week_catalog_notes": week_notes,
            "news_week_compatible": news_week_compatible,
        },
    )


# --------------------------------------------------
# 12. ADD SELECTED TO ANALYSIS
#
# 검색 결과에서 사용자가 체크한 곡을:
#
# Spotify CSV
#     ↓
# YouTube API
#     ↓
# MySQL
#     ↓
# Current Analysis
#
# 순서로 추가한다.
# --------------------------------------------------


@app.post("/add-analysis", dependencies=[Depends(require_local_analysis_origin)])
def add_analysis(
    selected_ranks: list[int] = Form(default=[]),
    search_artist: str = Form(default=""),
    week_end: str = Form(default=""),
):
    # Serialize selection mutations until the DB transaction is resolved.
    with _analysis_write_lock:
        return _add_analysis(selected_ranks, search_artist, week_end)


def _add_analysis(selected_ranks: list[int], search_artist: str, week_end: str):

    # --------------------------------------------------
    # 12-1. 아무 곡도 선택하지 않은 경우
    # --------------------------------------------------

    if not selected_ranks:

        message = "분석에 추가할 곡을 선택해 주세요."

        return analysis_redirect(
            url=(
                f"/?artist={quote_plus(search_artist)}"
                f"&week_end={quote_plus(week_end)}"
                f"&message={quote_plus(message)}"
            ),
            status_code=303,
        )

    # --------------------------------------------------
    # 12-2. Spotify CSV: verify requested week BEFORE touching MySQL/API.
    # --------------------------------------------------
    try:
        pair, _, _ = choose_pair(week_end=week_end)
        if pair is None:
            raise CatalogError('선택할 수 있는 비교 기간이 없습니다.')
        spotify_csv = load_spotify_csv(pair.current_end.isoformat())
        week_end = pair.current_end.isoformat()
    except (CatalogError, ChartValidationError, OSError, ValueError) as exc:
        return analysis_redirect(
            url=f'/?artist={quote_plus(search_artist)}&week_end={quote_plus(week_end)}'
                f'&message={quote_plus("주차 확인 실패: " + str(exc))}',
            status_code=303,
        )

    # --------------------------------------------------
    # 12-3. MySQL 연결
    # --------------------------------------------------

    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)

    # --------------------------------------------------
    # 현재 Analysis에 들어 있는 Artist 확인
    #
    # Artist 최대 10명 제한을 확인하기 위해 사용한다.
    # --------------------------------------------------

    current_artists = set()

    if analysis_song_ids:

        placeholders = ",".join(["%s"] * len(analysis_song_ids))

        cursor.execute(
            f"""
            SELECT DISTINCT artist
            FROM tracks
            WHERE song_id IN ({placeholders})
            """,
            tuple(analysis_song_ids),
        )

        current_artists = {row["artist"] for row in cursor.fetchall()}

    messages = []
    pending_song_ids = []
    pending_messages = []

    try:

        # --------------------------------------------------
        # 사용자가 선택한 Spotify Rank를 하나씩 처리
        # --------------------------------------------------

        for rank in selected_ranks:

            # --------------------------------------------------
            # Track 최대 10곡 제한
            # --------------------------------------------------

            if len(analysis_song_ids) + len(pending_song_ids) >= MAX_TRACKS:

                messages.append("곡은 최대 10곡까지 " "비교할 수 있습니다.")

                break

            # --------------------------------------------------
            # Spotify CSV에서 해당 Rank의 곡 찾기
            # --------------------------------------------------

            matches = spotify_csv[spotify_csv["rank"] == rank]

            if matches.empty:
                continue

            spotify_row = matches.iloc[0]

            artist = str(spotify_row["artist_names"])

            track = str(spotify_row["track_name"])

            spotify_rank = int(spotify_row["rank"])

            spotify_streams = int(spotify_row["streams"])

            # --------------------------------------------------
            # tracks에서 같은 곡 찾기
            # --------------------------------------------------

            cursor.execute(
                """
                SELECT song_id
                FROM tracks
                WHERE artist = %s
                  AND track = %s
                """,
                (
                    artist,
                    track,
                ),
            )

            existing_track = cursor.fetchone()

            if existing_track:

                song_id = existing_track["song_id"]

            else:

                # 새 곡이면 tracks에 저장
                cursor.execute(
                    """
                    INSERT INTO tracks (
                        artist,
                        track
                    )
                    VALUES (%s, %s)
                    """,
                    (
                        artist,
                        track,
                    ),
                )

                song_id = cursor.lastrowid

            # --------------------------------------------------
            # 이미 Current Analysis에 있는 곡
            # --------------------------------------------------

            if song_id in analysis_song_ids or song_id in pending_song_ids:

                messages.append(f"{artist} - {track}은 " "이미 분석 목록에 있습니다.")

                continue

            # --------------------------------------------------
            # Artist 최대 10명 제한
            #
            # 새로운 Artist를 추가하려는 경우에만 체크한다.
            # --------------------------------------------------

            if artist not in current_artists and len(current_artists) >= MAX_ARTISTS:

                messages.append("아티스트는 최대 10명까지 " "비교할 수 있습니다.")

                continue

            # --------------------------------------------------
            # Spotify 수집 시간
            # --------------------------------------------------

            collected_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # --------------------------------------------------
            # Spotify 데이터 저장
            #
            # 같은 song_id + chart_date가 있으면
            # 기존 데이터를 UPDATE한다.
            # --------------------------------------------------

            cursor.execute(
                """
                INSERT INTO spotify_chart (
                    song_id,
                    spotify_rank,
                    spotify_streams,
                    chart_date,
                    collected_at
                )

                VALUES (%s, %s, %s, %s, %s)

                ON DUPLICATE KEY UPDATE
                    spotify_rank =
                        VALUES(spotify_rank),

                    spotify_streams =
                        VALUES(spotify_streams),

                    collected_at =
                        VALUES(collected_at)
                """,
                (
                    song_id,
                    spotify_rank,
                    spotify_streams,
                    week_end,
                    collected_at,
                ),
            )

            # Keep the notice consistent with the existing STEP18 ACTIVE authority.
            # This read never collects statistics or changes approval records.
            from news.youtube_approval_lock import latest_approved
            active_approval = latest_approved(BASE_DIR / "facts" / "youtube_video_reviews", song_id)
            if active_approval is not None:
                pending_messages.append(
                    f"{artist} - {track}: 기존 ACTIVE 승인 영상"
                    f"({active_approval['video_id']})을 유지했습니다."
                )
            else:
                pending_messages.append(
                    f"{artist} - {track}: YouTube 영상 검수가 필요합니다. "
                    "YouTube Data에서 후보를 확인해 주세요."
                )

            # --------------------------------------------------
            # Current Analysis에 곡 추가
            # --------------------------------------------------

            pending_song_ids.append(song_id)

            current_artists.add(artist)

            pending_messages.append(f"{artist} - {track}을 " "분석 목록에 추가했습니다.")

        # --------------------------------------------------
        # DB 최종 저장
        # --------------------------------------------------

        connection.commit()
        analysis_song_ids.extend(pending_song_ids)
        messages.extend(pending_messages)

    except Exception as error:

        connection.rollback()

        print()
        print("❌ Add to Analysis 오류:")
        print(error)

        messages.append("데이터 추가 중 오류가 발생했습니다.")

    finally:

        cursor.close()
        connection.close()

    # --------------------------------------------------
    # 검색 결과 Dashboard로 돌아가기
    # --------------------------------------------------

    message_text = " ".join(messages)

    return analysis_redirect(
        url=(
            f"/?artist={quote_plus(search_artist)}"
            f"&week_end={quote_plus(week_end)}"
            f"&message={quote_plus(message_text)}"
        ),
        status_code=303,
    )


# --------------------------------------------------
# 13. CURRENT ANALYSIS에서 곡 하나 제거
#
# MySQL 데이터는 삭제하지 않는다.
# 현재 화면의 분석 목록에서만 제거한다.
# --------------------------------------------------


@app.post("/remove-analysis/{song_id}", dependencies=[Depends(require_local_analysis_origin)])
def remove_analysis(song_id: int, week_end: str = Form(default="")):

    with _analysis_write_lock:
        if song_id in analysis_song_ids:
            analysis_song_ids.remove(song_id)

    return analysis_redirect(
        url='/?week_end=' + quote_plus(week_end),
        status_code=303,
    )


# --------------------------------------------------
# 14. CURRENT ANALYSIS RESET
#
# MySQL 데이터는 그대로 유지한다.
# 현재 분석 목록만 비운다.
# --------------------------------------------------


@app.post("/reset-analysis", dependencies=[Depends(require_local_analysis_origin)])
def reset_analysis(week_end: str = Form(default="")):

    with _analysis_write_lock:
        analysis_song_ids.clear()

    return analysis_redirect(
        url='/?week_end=' + quote_plus(week_end),
        status_code=303,
    )


# --------------------------------------------------
# 15. 기존 Spotify 전용 페이지
#
# 보조 페이지로 유지한다.
# DB에 저장된 모든 곡을 보여준다.
# --------------------------------------------------


@app.get("/spotify")
def spotify_page(request: Request):

    dashboard_data = get_dashboard_data()

    spotify_data = sorted(
        dashboard_data,
        key=lambda item: item["spotify_rank"],
    )

    return templates.TemplateResponse(
        request=request,
        name="spotify.html",
        context={
            "title": "Spotify Data",
            "songs": spotify_data,
        },
    )


# --------------------------------------------------
# 16. 기존 YouTube 전용 페이지
#
# 보조 페이지로 유지한다.
# --------------------------------------------------


@app.get("/youtube")
def youtube_page(request: Request):

    dashboard_data = get_dashboard_data()

    youtube_data = sorted(
        [item for item in dashboard_data if item.get("youtube_video_id")],
        key=lambda item: int(item.get("youtube_views") or -1),
        reverse=True,
    )

    return templates.TemplateResponse(
        request=request,
        name="youtube.html",
        context={
            "title": "YouTube Data",
            "videos": youtube_data,
        },
    )


# --------------------------------------------------
# 17. 기존 Compare 전용 페이지
#
# 보조 페이지로 유지한다.
# --------------------------------------------------


@app.get("/compare")
def compare_page(request: Request, week_end: str = ""):

    dashboard_data = get_dashboard_data()

    selected = [row for row in dashboard_data if row['song_id'] in analysis_song_ids]
    try:
        pair, week_pairs, week_notes = choose_pair(week_end=week_end)
        if pair is None:
            weekly_comparison = []
            weekly_chart_error = '연속 2주의 원본 자료가 없습니다.'
        else:
            weekly_comparison = build_weekly_rows(selected, pair=pair)
            weekly_chart_error = None
    except (CatalogError, ChartValidationError, OSError, ValueError) as exc:
        pair, week_pairs, week_notes = None, [], []
        weekly_comparison = []
        weekly_chart_error = str(exc)

    return templates.TemplateResponse(
        request=request,
        name="compare.html",
        context={
            "title": "Compare — Global Weekly Charts",
            "weekly_comparison": weekly_comparison,
            "weekly_chart_error": weekly_chart_error,
            "week_options": [{'end': p.current_end.isoformat(), 'label': p.label} for p in week_pairs],
            "selected_week_end": pair.current_end.isoformat() if pair else '',
            "previous_week_end": pair.previous_end.strftime('%m/%d') if pair else '',
            "current_week_end": pair.current_end.strftime('%m/%d') if pair else '',
            "selected_period_label": pair.label if pair else '등록된 주차 없음',
            "week_catalog_notes": week_notes,
        },
    )
