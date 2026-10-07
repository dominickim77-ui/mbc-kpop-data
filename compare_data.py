import os
import pandas as pd
import requests
from dotenv import load_dotenv

# -------------------------
# 1. Spotify CSV 읽기
# -------------------------

csv_file = "regional-global-weekly-2026-10-01.csv"

df = pd.read_csv(csv_file)

spotify_song = df[
    (df["artist_names"] == "BTS") &
    (df["track_name"] == "SWIM")
].iloc[0]

# -------------------------
# 2. YouTube API Key 불러오기
# -------------------------

load_dotenv()
API_KEY = os.getenv("YOUTUBE_API_KEY")

# -------------------------
# 3. YouTube 영상 검색
# -------------------------

query = "BTS SWIM official"

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

video = search_data["items"][0]

video_id = video["id"]["videoId"]
title = video["snippet"]["title"]
channel = video["snippet"]["channelTitle"]

# -------------------------
# 4. YouTube 통계 가져오기
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
# 5. Spotify + YouTube 결과 출력
# -------------------------

print()
print("===== BTS - SWIM 데이터 비교 =====")
print()

print("[Spotify]")
print("순위:", spotify_song["rank"])
print("스트리밍:", spotify_song["streams"])
print("최고 순위:", spotify_song["peak_rank"])
print("차트 진입 주수:", spotify_song["weeks_on_chart"])

print()

print("[YouTube]")
print("영상 제목:", title)
print("채널:", channel)
print("조회수:", stats.get("viewCount"))
print("좋아요:", stats.get("likeCount"))
print("댓글:", stats.get("commentCount"))