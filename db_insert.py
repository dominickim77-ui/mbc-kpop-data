# --------------------------------------------------
# K-POP 비교 데이터를 MySQL에 저장하는 프로그램
#
# 데이터 흐름:
#
# kpop_comparison.csv
#        ↓
# tracks
#        ↓ song_id
#   ┌────┴───────────┐
#   ↓                ↓
# spotify_chart   youtube_stats
#
# 목적:
# CSV에 저장된 Spotify + YouTube 데이터를
# MySQL의 3개 테이블에 나누어 저장한다.
# --------------------------------------------------

import os
import html

import pandas as pd
import mysql.connector

from dotenv import load_dotenv


# --------------------------------------------------
# 1. .env 파일에서 MySQL 접속 정보 읽기
# --------------------------------------------------

load_dotenv()

MYSQL_HOST = os.getenv("MYSQL_HOST")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE")


# --------------------------------------------------
# 2. 비교 결과 CSV 파일 읽기
# --------------------------------------------------
#
# kpop_compare.py에서 만든 최종 CSV 파일을 읽는다.
# 한 행에는 한 곡의 Spotify + YouTube 정보가 들어 있다.
# --------------------------------------------------

df = pd.read_csv("kpop_comparison.csv")


# --------------------------------------------------
# 3. MySQL 데이터베이스 연결
# --------------------------------------------------

connection = mysql.connector.connect(
    host=MYSQL_HOST,
    port=MYSQL_PORT,
    user=MYSQL_USER,
    password=MYSQL_PASSWORD,
    database=MYSQL_DATABASE,
)

# SQL 명령을 실행하기 위한 cursor를 만든다.
cursor = connection.cursor()


# --------------------------------------------------
# 4. CSV의 각 곡을 한 줄씩 처리
# --------------------------------------------------

try:
    for _, row in df.iterrows():

        # CSV에서 아티스트와 곡 제목을 가져온다.
        artist = row["artist"]
        track = row["track"]

        # --------------------------------------------------
        # 4-1. tracks 테이블 확인
        #
        # 같은 아티스트 + 곡이 이미 있는지 먼저 확인한다.
        # 이미 있으면 기존 song_id를 사용한다.
        # 없으면 새로운 곡을 INSERT한다.
        # --------------------------------------------------

        cursor.execute(
            """
            SELECT song_id
            FROM tracks
            WHERE artist = %s AND track = %s
            """,
            (artist, track),
        )

        existing_track = cursor.fetchone()

        if existing_track:
            # 이미 존재하는 곡이면 기존 song_id 사용
            song_id = existing_track[0]

            print(
                f"ℹ️ 기존 곡 사용: {artist} - {track} / song_id={song_id}"
            )

        else:
            # 새로운 곡을 tracks 테이블에 저장
            cursor.execute(
                """
                INSERT INTO tracks (artist, track)
                VALUES (%s, %s)
                """,
                (artist, track),
            )

            # AUTO_INCREMENT로 생성된 song_id를 가져온다.
            song_id = cursor.lastrowid

            print(
                f"✅ tracks 저장: {artist} - {track} / song_id={song_id}"
            )

        # --------------------------------------------------
        # 4-2. Spotify 차트 데이터 저장
        #
        # UNIQUE 규칙:
        # 같은 song_id + chart_date 데이터는 한 번만 존재한다.
        #
        # 이미 같은 주차 데이터가 있으면
        # 새로운 행을 만들지 않고 기존 값을 업데이트한다.
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
                spotify_rank = VALUES(spotify_rank),
                spotify_streams = VALUES(spotify_streams),
                collected_at = VALUES(collected_at)
            """,
            (
                song_id,
                int(row["spotify_rank"]),
                int(row["spotify_streams"]),
                row["chart_date"],
                row["collected_at"],
            ),
        )

        # --------------------------------------------------
        # 4-3. YouTube 제목 정리
        #
        # YouTube API 결과에는
        # &amp; / &quot; 같은 HTML 표현이 들어갈 수 있다.
        #
        # html.unescape()를 사용해서
        # 사람이 읽기 좋은 문자로 변환한다.
        # --------------------------------------------------

        youtube_title = html.unescape(str(row["youtube_title"]))

        # --------------------------------------------------
        # 4-4. YouTube 통계 저장
        #
        # UNIQUE 규칙:
        # 같은 youtube_video_id + collected_at 데이터는
        # 중복 저장하지 않는다.
        #
        # 같은 수집 시점이면 기존 데이터를 업데이트하고,
        # 새로운 수집 시점이면 새로운 기록으로 저장한다.
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
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)

            ON DUPLICATE KEY UPDATE
                youtube_title = VALUES(youtube_title),
                youtube_channel = VALUES(youtube_channel),
                youtube_views = VALUES(youtube_views),
                youtube_likes = VALUES(youtube_likes),
                youtube_comments = VALUES(youtube_comments)
            """,
            (
                song_id,
                row["youtube_video_id"],
                youtube_title,
                row["youtube_channel"],
                int(row["youtube_views"]),
                int(row["youtube_likes"]),
                int(row["youtube_comments"]),
                row["collected_at"],
            ),
        )

        print("   ↳ Spotify + YouTube 데이터 저장 완료")


    # --------------------------------------------------
    # 5. 모든 작업이 성공하면 DB에 최종 반영
    # --------------------------------------------------

    connection.commit()

    print()
    print("========================================")
    print("✅ 모든 K-POP 데이터 MySQL 저장 완료")
    print("========================================")


# --------------------------------------------------
# 6. 작업 중 오류가 발생하면 저장 취소
# --------------------------------------------------

except Exception as error:
    connection.rollback()

    print()
    print("❌ 데이터 저장 중 오류 발생")
    print(error)


# --------------------------------------------------
# 7. MySQL 연결 종료
# --------------------------------------------------

finally:
    cursor.close()
    connection.close()

    print("✅ MySQL 연결 종료")