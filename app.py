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
# 10. RESET ANALYSIS
#
# 중요:
# RESET ANALYSIS는 MySQL 데이터를 삭제하지 않는다.
# 현재 화면에서 비교 중인 곡 목록만 초기화한다.
# --------------------------------------------------

import os
import html
import requests

import pandas as pd
import mysql.connector

from datetime import datetime
from urllib.parse import quote_plus

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# --------------------------------------------------
# 1. 기본 설정
# --------------------------------------------------

# 현재 Dashboard에서 비교 가능한 최대 Artist 수
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

analysis_song_ids = []


# --------------------------------------------------
# 3. .env 파일 읽기
# --------------------------------------------------

load_dotenv()


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


# --------------------------------------------------
# 6. static 폴더 연결
#
# CSS / JavaScript / 이미지 같은
# 화면용 파일을 사용할 수 있게 한다.
# --------------------------------------------------

app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static",
)


# --------------------------------------------------
# 7. templates 폴더 연결
#
# HTML 파일들이 들어 있는 폴더다.
# --------------------------------------------------

templates = Jinja2Templates(directory="templates")


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


def load_spotify_csv():

    return pd.read_csv(SPOTIFY_CSV_FILE)


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
            y.collected_at,

            -- YouTube 누적 조회수 - Spotify 주간 스트리밍
            (y.youtube_views - s.spotify_streams)
                AS difference,

            -- YouTube 조회수가 Spotify 스트리밍의
            -- 몇 배인지 계산
            ROUND(
                y.youtube_views
                / NULLIF(s.spotify_streams, 0),
                2
            ) AS ratio,

            -- 단순 숫자 기준 더 큰 값을 표시
            CASE
                WHEN y.youtube_views > s.spotify_streams
                    THEN 'YouTube'

                WHEN y.youtube_views < s.spotify_streams
                    THEN 'Spotify'

                ELSE 'Same'
            END AS larger_value

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
        JOIN youtube_stats AS y
            ON t.song_id = y.song_id

            AND y.collected_at = (
                SELECT MAX(y2.collected_at)

                FROM youtube_stats AS y2

                WHERE y2.song_id = t.song_id
            )
        """)

    dashboard_data = cursor.fetchall()

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
):

    # --------------------------------------------------
    # 11-1. Artist 검색
    # --------------------------------------------------

    artist = artist.strip()

    search_results = []
    search_message = ""

    if artist:

        spotify_csv = load_spotify_csv()

        # artist_names 컬럼에서 검색어를 찾는다.
        #
        # case=False:
        # BTS / bts 모두 검색 가능
        #
        # na=False:
        # 빈 값 때문에 오류가 나지 않게 한다.
        matches = spotify_csv[
            spotify_csv["artist_names"].str.contains(
                artist,
                case=False,
                na=False,
            )
        ]

        # Spotify 순위 순서로 정렬
        matches = matches.sort_values("rank")

        # HTML에서 필요한 값만 가져온다.
        search_results = matches[
            [
                "rank",
                "artist_names",
                "track_name",
                "streams",
            ]
        ].to_dict("records")

        # 검색 결과가 없는 경우
        if not search_results:

            search_message = (
                f'"{artist}"는 현재 Spotify '
                "Weekly Global Top 200에서 "
                "찾을 수 없습니다."
            )

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
        key=lambda item: item["youtube_views"],
        reverse=True,
    )

    # --------------------------------------------------
    # 11-6. Compare 영역
    #
    # Spotify 순위 순서 사용
    # --------------------------------------------------

    comparison_data = spotify_data

    # --------------------------------------------------
    # Chart.js에 전달할 데이터 준비
    # --------------------------------------------------

    chart_labels = [f"{item['artist']} - {item['track']}" for item in comparison_data]

    chart_spotify = [int(item["spotify_streams"]) for item in comparison_data]

    chart_youtube = [int(item["youtube_views"]) for item in comparison_data]

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
            "comparison_data": comparison_data,
            "chart_labels": chart_labels,
            "chart_spotify": chart_spotify,
            "chart_youtube": chart_youtube,
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


@app.post("/add-analysis")
def add_analysis(
    selected_ranks: list[int] = Form(default=[]),
    search_artist: str = Form(default=""),
):

    # --------------------------------------------------
    # 12-1. 아무 곡도 선택하지 않은 경우
    # --------------------------------------------------

    if not selected_ranks:

        message = "분석에 추가할 곡을 선택해 주세요."

        return RedirectResponse(
            url=(
                f"/?artist={quote_plus(search_artist)}"
                f"&message={quote_plus(message)}"
            ),
            status_code=303,
        )

    # --------------------------------------------------
    # 12-2. Spotify CSV 읽기
    # --------------------------------------------------

    spotify_csv = load_spotify_csv()

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

    try:

        # --------------------------------------------------
        # 사용자가 선택한 Spotify Rank를 하나씩 처리
        # --------------------------------------------------

        for rank in selected_ranks:

            # --------------------------------------------------
            # Track 최대 10곡 제한
            # --------------------------------------------------

            if len(analysis_song_ids) >= MAX_TRACKS:

                messages.append("Track은 최대 10곡까지 " "비교할 수 있습니다.")

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

            if song_id in analysis_song_ids:

                messages.append(f"{artist} - {track}은 " "이미 Analysis에 있습니다.")

                continue

            # --------------------------------------------------
            # Artist 최대 10명 제한
            #
            # 새로운 Artist를 추가하려는 경우에만 체크한다.
            # --------------------------------------------------

            if artist not in current_artists and len(current_artists) >= MAX_ARTISTS:

                messages.append("Artist는 최대 10명까지 " "비교할 수 있습니다.")

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
                    CHART_DATE,
                    collected_at,
                ),
            )

            # --------------------------------------------------
            # YouTube 검색
            # --------------------------------------------------

            query = f"{artist} " f"{track} " "official"

            search_response = requests.get(
                "https://www.googleapis.com/youtube/v3/search",
                params={
                    "part": "snippet",
                    "q": query,
                    "type": "video",
                    "maxResults": 1,
                    "key": YOUTUBE_API_KEY,
                },
                timeout=10,
            )

            search_data = search_response.json()

            # --------------------------------------------------
            # YouTube 검색 결과가 없는 경우
            # --------------------------------------------------

            if not search_data.get("items"):

                messages.append(
                    f"{artist} - {track}: " "YouTube 영상을 찾지 못했습니다."
                )

                continue

            video = search_data["items"][0]

            youtube_video_id = video["id"]["videoId"]

            youtube_title = html.unescape(video["snippet"]["title"])

            youtube_channel = video["snippet"]["channelTitle"]

            # --------------------------------------------------
            # YouTube 영상 통계 요청
            # --------------------------------------------------

            stats_response = requests.get(
                "https://www.googleapis.com/youtube/v3/videos",
                params={
                    "part": "statistics",
                    "id": youtube_video_id,
                    "key": YOUTUBE_API_KEY,
                },
                timeout=10,
            )

            stats_data = stats_response.json()

            if not stats_data.get("items"):

                messages.append(
                    f"{artist} - {track}: " "YouTube 통계를 찾지 못했습니다."
                )

                continue

            stats = stats_data["items"][0]["statistics"]

            youtube_views = int(
                stats.get(
                    "viewCount",
                    0,
                )
            )

            youtube_likes = int(
                stats.get(
                    "likeCount",
                    0,
                )
            )

            youtube_comments = int(
                stats.get(
                    "commentCount",
                    0,
                )
            )

            # --------------------------------------------------
            # YouTube DB 저장
            #
            # 같은 video_id + collected_at이면
            # 기존 행을 UPDATE한다.
            #
            # 새로운 시간에 다시 검색하면
            # 새로운 시점의 기록으로 저장된다.
            # --------------------------------------------------

            cursor.execute(
                """
                INSERT INTO youtube_stats (
                    song_id,
                    youtube_video_id,
                    youtube_title,
                    youtube_channel,
                    youtube_views,
                    youtube_likes,
                    youtube_comments,
                    collected_at
                )

                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )

                ON DUPLICATE KEY UPDATE
                    youtube_title =
                        VALUES(youtube_title),

                    youtube_channel =
                        VALUES(youtube_channel),

                    youtube_views =
                        VALUES(youtube_views),

                    youtube_likes =
                        VALUES(youtube_likes),

                    youtube_comments =
                        VALUES(youtube_comments)
                """,
                (
                    song_id,
                    youtube_video_id,
                    youtube_title,
                    youtube_channel,
                    youtube_views,
                    youtube_likes,
                    youtube_comments,
                    collected_at,
                ),
            )

            # --------------------------------------------------
            # Current Analysis에 곡 추가
            # --------------------------------------------------

            analysis_song_ids.append(song_id)

            current_artists.add(artist)

            messages.append(f"{artist} - {track}을 " "Analysis에 추가했습니다.")

        # --------------------------------------------------
        # DB 최종 저장
        # --------------------------------------------------

        connection.commit()

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

    return RedirectResponse(
        url=(
            f"/?artist={quote_plus(search_artist)}"
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


@app.post("/remove-analysis/{song_id}")
def remove_analysis(song_id: int):

    if song_id in analysis_song_ids:

        analysis_song_ids.remove(song_id)

    return RedirectResponse(
        url="/",
        status_code=303,
    )


# --------------------------------------------------
# 14. CURRENT ANALYSIS RESET
#
# MySQL 데이터는 그대로 유지한다.
# 현재 분석 목록만 비운다.
# --------------------------------------------------


@app.post("/reset-analysis")
def reset_analysis():

    analysis_song_ids.clear()

    return RedirectResponse(
        url="/",
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
        dashboard_data,
        key=lambda item: item["youtube_views"],
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
def compare_page(request: Request):

    dashboard_data = get_dashboard_data()

    comparison_data = sorted(
        dashboard_data,
        key=lambda item: item["spotify_rank"],
    )

    return templates.TemplateResponse(
        request=request,
        name="compare.html",
        context={
            "title": "Compare Data",
            "comparisons": comparison_data,
        },
    )
