import os
import pandas as pd
import requests
from dotenv import load_dotenv

# -------------------------
# 1. 기본 설정
# -------------------------

load_dotenv()
API_KEY = os.getenv("YOUTUBE_API_KEY")

csv_file = "regional-global-weekly-2026-10-01.csv"
df = pd.read_csv(csv_file)

# 비교할 곡 목록
songs = [
    ("BTS", "SWIM"),
    ("BTS", "NORMAL"),
    ("LISA", "SaWaDiKa"),
    ("ROSÉ, Bruno Mars", "APT."),
    ("KATSEYE", "Animal"),
]

results = []

# -------------------------
# 2. 곡별 반복
# -------------------------

for artist, track in songs:

    # Spotify 데이터 찾기
    spotify_row = df[
        (df["artist_names"] == artist) &
        (df["track_name"] == track)
    ]

    if spotify_row.empty:
        print(f"Spotify에서 찾지 못함: {artist} - {track}")
        continue

    spotify_row = spotify_row.iloc[0]

    # -------------------------
    # 3. YouTube 검색
    # -------------------------

    query = f"{artist} {track} official"

    search_url = "https://www.googleapis.com/youtube/v3/search"

    search_params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": 1,
        "key": API_KEY
    }

    search_response = requests.get(search_url, params=search_params)
    search_data = search_response.json()

    if not search_data.get("items"):
        print(f"YouTube에서 찾지 못함: {artist} - {track}")
        continue

    video = search_data["items"][0]

    video_id = video["id"]["videoId"]
    youtube_title = video["snippet"]["title"]
    channel = video["snippet"]["channelTitle"]

    # -------------------------
    # 4. YouTube 통계
    # -------------------------

    video_url = "https://www.googleapis.com/youtube/v3/videos"

    video_params = {
        "part": "statistics",
        "id": video_id,
        "key": API_KEY
    }

    video_response = requests.get(video_url, params=video_params)
    video_data = video_response.json()

    stats = video_data["items"][0]["statistics"]

    # -------------------------
    # 5. 결과 저장
    # -------------------------

    results.append({
        "artist": artist,
        "track": track,
        "spotify_rank": spotify_row["rank"],
        "spotify_streams": spotify_row["streams"],
        "youtube_title": youtube_title,
        "youtube_channel": channel,
        "youtube_views": int(stats.get("viewCount", 0)),
        "youtube_likes": int(stats.get("likeCount", 0)),
        "youtube_comments": int(stats.get("commentCount", 0))
    })

# -------------------------
# 6. 표로 출력
# -------------------------

result_df = pd.DataFrame(results)
# 데이터 수집 시간 기록
result_df["collected_at"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")

# 비교 결과를 CSV 파일로 저장
result_df.to_csv(
    "kpop_comparison.csv",
    index=False,
    encoding="utf-8-sig"
)

print("✅ kpop_comparison.csv 저장 완료")

print()
print("===== K-POP Spotify + YouTube 비교 =====")
print()

print(
    result_df[
        [
            "artist",
            "track",
            "spotify_rank",
            "spotify_streams",
            "youtube_views",
            "youtube_likes",
            "youtube_comments"
        ]
    ].to_string(index=False)
)