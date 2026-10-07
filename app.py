# --------------------------------------------------
# MBC K-POP DATA LAB
# FastAPI 웹 서버
#
# 역할:
# 1. 웹 브라우저의 요청을 받는다.
# 2. MySQL에서 K-POP 데이터를 가져온다.
# 3. 데이터를 HTML 페이지에 전달한다.
# --------------------------------------------------

import os

import mysql.connector

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates


# --------------------------------------------------
# 1. .env 파일 읽기
# --------------------------------------------------

load_dotenv()

MYSQL_HOST = os.getenv("MYSQL_HOST")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE")


# --------------------------------------------------
# 2. FastAPI 애플리케이션 생성
# --------------------------------------------------

app = FastAPI()


# --------------------------------------------------
# 3. static 폴더 연결
# --------------------------------------------------

app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static",
)


# --------------------------------------------------
# 4. templates 폴더 연결
# --------------------------------------------------

templates = Jinja2Templates(directory="templates")


# --------------------------------------------------
# 5. MySQL 연결 함수
#
# 페이지에서 DB 데이터가 필요할 때
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
# 6. HOME 페이지
# --------------------------------------------------

@app.get("/")
def home(request: Request):

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "title": "K-POP DATA LAB",
        },
    )


# --------------------------------------------------
# 7. Spotify 페이지
#
# tracks와 spotify_chart를 song_id로 JOIN한다.
# Spotify 순위가 높은 곡부터 가져온다.
# --------------------------------------------------

@app.get("/spotify")
def spotify_page(request: Request):

    # MySQL 연결
    connection = get_db_connection()

    # dictionary=True를 사용하면
    # 컬럼 이름으로 데이터를 사용할 수 있다.
    cursor = connection.cursor(dictionary=True)

    # Spotify 데이터 조회
    cursor.execute(
        """
        SELECT
            t.song_id,
            t.artist,
            t.track,
            s.spotify_rank,
            s.spotify_streams,
            s.chart_date

        FROM tracks AS t

        JOIN spotify_chart AS s
            ON t.song_id = s.song_id

        ORDER BY s.spotify_rank
        """
    )

    spotify_data = cursor.fetchall()

    # DB 작업이 끝났으므로 연결 종료
    cursor.close()
    connection.close()

    # 조회한 데이터를 spotify.html로 전달
    return templates.TemplateResponse(
        request=request,
        name="spotify.html",
        context={
            "title": "Spotify Data",
            "songs": spotify_data,
        },
    )

# --------------------------------------------------
# 8. YouTube 페이지
#
# tracks와 youtube_stats를 song_id로 JOIN한다.
# YouTube 조회수가 높은 순서로 보여준다.
# --------------------------------------------------

@app.get("/youtube")
def youtube_page(request: Request):

    # MySQL 연결
    connection = get_db_connection()

    # dictionary=True를 사용하면
    # 컬럼 이름으로 데이터를 사용할 수 있다.
    cursor = connection.cursor(dictionary=True)

    # YouTube 데이터 조회
    cursor.execute(
        """
        SELECT
            t.song_id,
            t.artist,
            t.track,

            y.youtube_video_id,
            y.youtube_title,
            y.youtube_channel,
            y.youtube_views,
            y.youtube_likes,
            y.youtube_comments,
            y.collected_at

        FROM tracks AS t

        JOIN youtube_stats AS y
            ON t.song_id = y.song_id

        ORDER BY y.youtube_views DESC
        """
    )

    youtube_data = cursor.fetchall()

    # DB 연결 종료
    cursor.close()
    connection.close()

    # youtube.html로 데이터 전달
    return templates.TemplateResponse(
        request=request,
        name="youtube.html",
        context={
            "title": "YouTube Data",
            "videos": youtube_data,
        },
    )

# --------------------------------------------------
# 9. Compare 페이지
#
# Spotify와 YouTube 데이터를 한 화면에서 비교한다.
#
# 계산:
# 1. 두 숫자의 차이
# 2. YouTube 조회수가 Spotify 스트리밍의 몇 배인지
# 3. 단순 숫자 기준 어느 값이 더 큰지
#
# 주의:
# Spotify = 한 주의 스트리밍 수
# YouTube = 영상 공개 후 누적 조회수
# 따라서 "어느 플랫폼이 더 인기 있다"는 의미는 아니다.
# --------------------------------------------------

@app.get("/compare")
def compare_page(request: Request):

    # MySQL 연결
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    # 세 테이블을 song_id로 연결하고
    # 비교에 필요한 값을 SQL에서 계산한다.
    cursor.execute(
        """
        SELECT
            t.artist,
            t.track,

            s.spotify_rank,
            s.spotify_streams,
            s.chart_date,

            y.youtube_views,
            y.youtube_likes,
            y.youtube_comments,

            -- YouTube 조회수 - Spotify 주간 스트리밍
            (y.youtube_views - s.spotify_streams) AS difference,

            -- YouTube 조회수가 Spotify 스트리밍의 몇 배인지 계산
            ROUND(
                y.youtube_views / NULLIF(s.spotify_streams, 0),
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

        JOIN spotify_chart AS s
            ON t.song_id = s.song_id

        JOIN youtube_stats AS y
            ON t.song_id = y.song_id

        ORDER BY s.spotify_rank
        """
    )

    comparison_data = cursor.fetchall()

    cursor.close()
    connection.close()

    # 비교 데이터를 compare.html로 전달한다.
    return templates.TemplateResponse(
        request=request,
        name="compare.html",
        context={
            "title": "Compare Data",
            "comparisons": comparison_data,
        },
    )