import os
import requests
from dotenv import load_dotenv

# .env 파일에서 API Key 불러오기
load_dotenv()
API_KEY = os.getenv("YOUTUBE_API_KEY")

# YouTube에서 검색할 내용
query = "BTS SWIM official"

# 1. 영상 검색
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

# 2. 영상 통계 가져오기
video_url = "https://www.googleapis.com/youtube/v3/videos"

video_params = {
    "part": "statistics",
    "id": video_id,
    "key": API_KEY
}

video_response = requests.get(video_url, params=video_params)
video_data = video_response.json()

stats = video_data["items"][0]["statistics"]

print("영상 제목:", title)
print("채널:", channel)
print("조회수:", stats.get("viewCount"))
print("좋아요:", stats.get("likeCount"))
print("댓글:", stats.get("commentCount"))