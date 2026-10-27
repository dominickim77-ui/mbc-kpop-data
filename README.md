# 🎧 K-POP DATA LAB

> **Spotify + YouTube Data Journalism Dashboard**  
> MBC AI 데이터 저널리즘 수업 실습 프로젝트  
> 📅 2026.10.07

---

## 🧭 Project Overview

### 💡 무엇을 만들었나?

**K-POP DATA LAB**은 사용자가 아티스트를 검색하고 원하는 곡을 선택하면,

- 🎵 Spotify 주간 차트 데이터
- ▶️ YouTube 조회수 · 좋아요 · 댓글
- 📊 두 플랫폼의 데이터 비교
- 📈 누적 분석 Chart

를 **하나의 Dashboard에서 확인할 수 있는 데이터 저널리즘 실습 웹서비스**다.

---

## 🎯 Learning Goal

이번 프로젝트의 목표는 단순히 웹사이트를 만드는 것이 아니라,

> **데이터가 어디서 오고 → 어떻게 저장되고 → 어떻게 분석되고 → 어떻게 기사로 연결되는지 이해하는 것**

이었다.

```text
DATA
 ↓
COLLECT
 ↓
STORE
 ↓
QUERY
 ↓
ANALYZE
 ↓
VISUALIZE
 ↓
EXPLAIN
```

---

# 🧠 What I Learned

## 전체 데이터 흐름

```text
Spotify CSV
     +
YouTube Data API
     ↓
   Python
     ↓
   MySQL
     ↓
  SQL JOIN
     ↓
  FastAPI
     ↓
  Jinja2
     ↓
HTML / CSS
     ↓
 Chart.js
     ↓
K-POP DATA LAB
```

---

# 📚 Core Concepts

| 개념 | English | 쉽게 말하면 |
|---|---|---|
| API | Application Programming Interface | 다른 서비스에서 데이터를 가져오는 통로 |
| CSV | Comma-Separated Values | 표 형태 데이터를 저장한 파일 |
| Database | Database | 데이터를 정리해서 저장하는 창고 |
| ERD | Entity Relationship Diagram | 데이터베이스 구조 설계도 |
| PK | Primary Key | 각 데이터를 구분하는 고유 번호 |
| FK | Foreign Key | 서로 다른 Table을 연결하는 값 |
| JOIN | SQL JOIN | 여러 Table의 데이터를 연결해서 보는 방법 |
| FastAPI | FastAPI | Python으로 웹 서버를 만드는 도구 |
| Jinja2 | Jinja2 | Python 데이터를 HTML에 보여주는 도구 |
| Chart.js | Chart.js | 웹에서 그래프를 만드는 JavaScript Library |
| Log Scale | Logarithmic Scale | 큰 값과 작은 값을 같이 보기 쉽게 압축하는 방식 |

---

# 📊 Data Sources

## 🎵 Spotify

사용 파일:

```text
regional-global-weekly-2026-10-01.csv
```

기준:

> **Spotify Weekly Top Songs — Global**  
> 2026-09-25 ~ 2026-10-01

사용 데이터:

- Artist
- Track
- Rank
- Weekly Streams

---

## ▶️ YouTube

사용:

```text
YouTube Data API v3
```

가져온 데이터:

- Video ID
- Video Title
- Channel
- Views
- Likes
- Comments

---

# 🗃️ Database Architecture

데이터를 하나의 Table에 전부 넣지 않고 **3개의 역할별 Table**로 분리했다.

## ① `tracks`

곡의 기본정보를 저장한다.

| Column | Role |
|---|---|
| `song_id` | Primary Key |
| `artist` | Artist 이름 |
| `track` | Track 이름 |

---

## ② `spotify_chart`

Spotify 차트 데이터를 저장한다.

| Column | Role |
|---|---|
| `spotify_id` | Primary Key |
| `song_id` | tracks와 연결하는 FK |
| `spotify_rank` | Spotify 순위 |
| `spotify_streams` | 주간 스트리밍 |
| `chart_date` | 차트 날짜 |
| `collected_at` | 데이터 수집 시간 |

---

## ③ `youtube_stats`

YouTube 통계를 저장한다.

| Column | Role |
|---|---|
| `youtube_id` | Primary Key |
| `song_id` | tracks와 연결하는 FK |
| `youtube_video_id` | YouTube Video ID |
| `youtube_title` | 영상 제목 |
| `youtube_channel` | 채널 |
| `youtube_views` | 누적 조회수 |
| `youtube_likes` | 좋아요 |
| `youtube_comments` | 댓글 |
| `collected_at` | 수집 시간 |

---

# 🔗 ERD

```text
                 tracks
          ┌────────────────┐
          │ song_id   PK   │
          │ artist         │
          │ track          │
          └───────┬────────┘
                  │
         ┌────────┴────────┐
         │                 │
         ▼                 ▼

  spotify_chart       youtube_stats
 ┌──────────────┐    ┌────────────────┐
 │ spotify_id PK│    │ youtube_id PK  │
 │ song_id FK   │    │ song_id FK     │
 │ rank         │    │ video_id       │
 │ streams      │    │ views          │
 │ chart_date   │    │ likes          │
 └──────────────┘    │ comments       │
                     └────────────────┘
```

### Relationship

```text
tracks 1 → 0..N spotify_chart

tracks 1 → 0..N youtube_stats
```

---

# 🔄 Data Pipeline

## STEP 01 — Artist Search

사용자가 Artist 이름을 입력한다.

```text
[ BRUNO________________ ] [ Search ]
```

↓

Spotify CSV에서 검색한다.

---

## STEP 02 — Track Selection

한 Artist가 여러 곡을 가지고 있을 수 있기 때문에  
자동으로 한 곡을 선택하지 않는다.

```text
☐ Die With A Smile
☐ Locked out of Heaven
☐ Risk It All
☐ Just the Way You Are
☐ That's What I Like
☐ APT.
```

↓

```text
[ Add Selected to Analysis ]
```

---

## STEP 03 — YouTube API

선택된 곡을 다음 형태로 검색한다.

```text
Artist + Track + official
```

↓

YouTube Data API에서:

```text
Views
Likes
Comments
Channel
Video ID
```

를 가져온다.

---

## STEP 04 — MySQL 저장

```text
Track
 ↓
tracks
 ↓
song_id
 ├─────────────┐
 ↓             ↓
Spotify     YouTube
```

이미 존재하는 곡은 기존 `song_id`를 다시 사용한다.

---

# ♻️ Duplicate Protection

같은 데이터를 여러 번 실행했을 때 DB가 계속 쌓이지 않도록 중복 방지 기능을 넣었다.

## Spotify

```text
song_id + chart_date
```

를 UNIQUE로 설정.

## YouTube

```text
youtube_video_id + collected_at
```

을 UNIQUE로 설정.

사용한 SQL:

```sql
ON DUPLICATE KEY UPDATE
```

즉,

```text
새 데이터
→ INSERT

같은 데이터
→ UPDATE
```

---

# 🖥️ Single Dashboard

처음에는 페이지를 따로 만들었다.

```text
HOME
→ Spotify
→ YouTube
→ Compare
```

하지만 여러 페이지를 이동하면 한눈에 비교하기 어려웠다.

그래서 최종적으로:

```text
K-POP DATA LAB

🔎 Artist Search

🎯 Current Analysis

🎵 Spotify Data

▶️ YouTube Data

📊 Compare

📈 Accumulated Analysis
```

형태의 **Single Dashboard**로 변경했다.

---

# 🔎 Artist Search

Spotify Weekly Global Top 200에서 Artist를 검색한다.

예:

```text
BTS
LISA
BLACKPINK
Bruno Mars
```

검색 결과가 없으면:

> 현재 Spotify Weekly Global Top 200에서 찾을 수 없습니다.

라고 표시한다.

---

# 🎯 Current Analysis

현재 비교하고 싶은 곡만 관리한다.

예:

```text
Artists: 3 / 10
Tracks: 6 / 10

LISA — SaWaDiKa            [×]
BTS — SWIM                 [×]
ROSÉ, Bruno Mars — APT.   [×]
```

### 분석 제한

- Artist 최대 **10명**
- Track 최대 **10곡**

> Chart가 너무 복잡해지는 것을 방지하기 위한 UX 규칙

---

# ❌ Remove Track

각 Track 오른쪽의:

```text
[×]
```

버튼으로 해당 곡만 Current Analysis에서 제거할 수 있다.

> MySQL 데이터는 삭제하지 않는다.

---

# ♻️ RESET ANALYSIS

```text
[ RESET ANALYSIS ]
```

현재 분석 목록 전체를 초기화한다.

```text
Artists: 0 / 10
Tracks: 0 / 10
```

하지만 MySQL에 저장한 데이터는 그대로 유지한다.

---

# 🎵 Spotify Data

현재 Analysis에 포함된 곡의:

- Rank
- Artist
- Track
- Weekly Streams
- Chart Date

를 보여준다.

---

# ▶️ YouTube Data

현재 Analysis에 포함된 곡의:

- Views
- Likes
- Comments
- Channel

을 보여준다.

---

# 📊 Compare

Spotify와 YouTube 데이터를 같은 화면에서 비교한다.

## Difference

```text
YouTube Views - Spotify Streams
```

## Ratio

```text
YouTube Views ÷ Spotify Streams
```

## Larger

단순 숫자 기준 더 큰 값을 표시한다.

```text
Spotify
YouTube
Same
```

---

# ⚠️ Important Data Journalism Rule

이 프로젝트에서 **가장 중요한 부분**이다.

Spotify와 YouTube의 숫자는 같은 기준이 아니다.

### Spotify

```text
Weekly Streams
```

→ **한 주 동안의 스트리밍 수**

### YouTube

```text
Cumulative Views
```

→ **영상 공개 이후 누적 조회수**

따라서:

> ❌ YouTube가 Spotify보다 300배 더 인기 있다.

라고 말하면 안 된다.

정확한 표현:

> ✅ YouTube 누적 조회수가 해당 주 Spotify 스트리밍 수보다 약 300배 컸다.

---

# 📈 Accumulated Analysis

선택한 최대 10곡을 Chart로 비교한다.

```text
Spotify Weekly Streams
        VS
YouTube Cumulative Views
```

두 숫자의 크기 차이가 매우 크기 때문에:

```text
Logarithmic Scale
```

을 사용했다.

---

# 📊 Example Analysis

## Bruno Mars Search Example

| Track | Spotify Weekly Streams | YouTube Views | Ratio |
|---|---:|---:|---:|
| Die With A Smile | 17,899,819 | 1,871,728,441 | 104.57x |
| Locked out of Heaven | 13,020,548 | 1,306,676,128 | 100.35x |
| Risk It All | 12,909,649 | 161,865,782 | 12.54x |
| Just the Way You Are | 10,361,963 | 2,219,247,058 | 214.17x |
| That's What I Like | 9,114,614 | 2,559,734,441 | 280.84x |
| APT. | 8,675,626 | 2,704,373,001 | 311.72x |

---

# 📰 Fact Sheet Insight

숫자만 보면 YouTube 값이 훨씬 크다.

하지만 중요한 질문은:

> **“어느 숫자가 더 큰가?”**

가 아니라,

> **“이 숫자는 무엇을 측정한 것인가?”**

이다.

데이터를 해석할 때는 반드시:

- 측정 기간
- 데이터 출처
- 집계 방식
- 지표 정의

를 함께 확인해야 한다.

---

# 📰 Article Draft

## 같은 노래인데 숫자는 왜 이렇게 다를까?
### Spotify와 YouTube 데이터를 비교해봤다

음악의 인기를 보여주는 숫자는 플랫폼마다 다르다.

Spotify에서는 한 주 동안 몇 번 스트리밍됐는지를 볼 수 있고,
YouTube에서는 영상 공개 이후 누적된 조회수를 확인할 수 있다.

이번 실습에서는 Spotify Weekly Global Chart와
YouTube Data API를 연결해 같은 곡의 수치를 한 화면에서 비교하는
**K-POP DATA LAB**을 제작했다.

ROSÉ와 Bruno Mars의 `APT.`는
Spotify 주간 스트리밍 약 **868만 회**,
YouTube 누적 조회수 약 **27억 회**로 나타났다.

단순 숫자로 계산하면 YouTube 누적 조회수가
해당 주 Spotify 스트리밍 수보다 약 **311.7배** 컸다.

하지만 이를 두고 YouTube에서 311배 더 인기 있다고 말할 수는 없다.

Spotify는 한 주의 데이터를 측정하고,
YouTube는 영상 공개 이후의 누적 데이터를 보여주기 때문이다.

> **데이터 저널리즘에서 중요한 것은 숫자를 가져오는 것뿐 아니라  
> 그 숫자가 무엇을 의미하는지를 설명하는 것이다.**

---

# 🛠 Tech Stack

### Data
- Spotify Weekly Chart CSV
- YouTube Data API v3

### Backend
- Python
- FastAPI
- Pandas
- Requests

### Database
- MySQL
- MySQL Workbench

### Frontend
- HTML
- CSS
- Jinja2
- JavaScript
- Chart.js

### Development
- Visual Studio Code
- Git
- GitHub

---

# 📂 Project Structure

```text
mbc-kpop-data/
│
├── app.py
├── db_insert.py
├── db_test.py
├── compare_data.py
├── kpop_compare.py
├── youtube_test.py
│
├── mbc_kpop_data.sql
├── kpop_comparison.csv
├── regional-global-weekly-2026-10-01.csv
│
├── .env
├── .gitignore
│
├── templates/
│   ├── index.html
│   ├── spotify.html
│   ├── youtube.html
│   └── compare.html
│
└── static/
    └── style.css
```

---

# 🔐 Environment Variables

API Key와 Password는 코드 안에 직접 저장하지 않는다.

`.env`

```text
YOUTUBE_API_KEY=YOUR_KEY

MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=YOUR_PASSWORD
MYSQL_DATABASE=mbc_kpop_data
```

`.gitignore`

```text
.env
__pycache__/
```

---

# ▶️ Run Project

## Install

```bash
pip install pandas requests python-dotenv mysql-connector-python
pip install fastapi uvicorn jinja2 python-multipart
```

## Run

```bash
uvicorn app:app --reload
```

## Browser

```text
http://127.0.0.1:8000
```

---

# 🐛 Troubleshooting Knowledge Base

## `404 Not Found`

### 의미
FastAPI에 해당 Route가 없거나 저장되지 않은 코드가 실행 중일 수 있다.

---

## `500 Internal Server Error`

### 의미
Python / FastAPI 내부 오류.

### 확인
VS Code Terminal의 Traceback부터 본다.

---

## `return can be used only within a function`

### 원인
Python 들여쓰기 오류.

```python
def home():
    # return은 함수 안에 있어야 한다.
    return
```

---

## `Unexpected end of JSON input`

### 원인
Chart.js의 `JSON.parse()`가 비어 있거나 깨진 JSON을 읽은 경우.

이번 프로젝트에서는 Chart에 필요한 데이터만 별도로 전달하도록 수정했다.

---

## Python Format

Windows:

```text
Shift + Alt + F
```

Formatter:

```text
Black Formatter
```

> Black은 Python 코드는 정리하지만 문자열 안의 SQL까지 자동 정렬하지는 않는다.

---

# ✅ Project Status

- [x] Spotify CSV 확보
- [x] YouTube Data API 연결
- [x] Python API 호출
- [x] 데이터 결합
- [x] CSV 저장
- [x] ERD 설계
- [x] MySQL Schema
- [x] Foreign Key
- [x] Python → MySQL
- [x] Duplicate Protection
- [x] SQL JOIN
- [x] FastAPI
- [x] Artist Search
- [x] Track Selection
- [x] Current Analysis
- [x] Artist 10명 제한
- [x] Track 10곡 제한
- [x] 개별 Remove
- [x] RESET ANALYSIS
- [x] Single Dashboard
- [x] Spotify Data
- [x] YouTube Data
- [x] Compare
- [x] Difference
- [x] Ratio
- [x] Chart.js
- [x] Logarithmic Scale
- [x] Fact Sheet
- [x] 기사 초안
- [ ] Final Git Commit
- [ ] Final Git Push

---

# 🚀 Future Ideas

- Spotify 최신 Chart 자동 업데이트
- 날짜별 YouTube 조회수 저장
- 시간 변화 Line Chart
- 국가별 K-POP Chart 비교
- Artist별 분석
- Official Video 판별 강화
- Fact Sheet 자동 생성
- 기사 초안 자동 생성
- 모바일 Dashboard 개선
- Cloud 배포

---

# 🧩 One-Line Summary

> **K-POP DATA LAB은 Spotify와 YouTube 데이터를 수집·저장·비교·시각화하면서, 숫자의 크기보다 “그 숫자가 무엇을 의미하는가”를 이해하기 위해 만든 데이터 저널리즘 학습 프로젝트다.**

---

# ⚖️ License, Sources & Responsible AI Use
_2026-10-27 평가 과제: 저널리즘 윤리와 법적 책임_

## 1. 소프트웨어 이용 조건 (MIT License)

이 저장소에서 저작권자가 권리를 보유하고 MIT 라이선스로 제공할 수 있는 **자체 작성 소스 코드 및 관련 문서**는 [MIT License](./LICENSE)에 따라 이용할 수 있다.

- 저작권자: **Copyright (c) 2026 Kim Hyung Suk**
- 사용자는 해당 소프트웨어를 이용·복제·수정·배포·재라이선스·판매할 수 있다.
- 복제본 또는 소프트웨어의 상당 부분에는 **원 저작권 표시와 MIT 허가 고지**를 포함해야 한다.
- 소프트웨어는 보증 없이 제공된다.
- **외부 서비스 데이터, 음악·영상·이미지, 아티스트 이름·상표, 제3자 라이브러리 및 기타 타인 권리 자료는 MIT 허가 대상이 아니다.** 각 원 제공자의 약관·라이선스·권리를 별도로 확인해야 한다.

## 2. 데이터 및 도구 출처 · 사용 조건

| 구분 | 이 프로젝트에서의 역할 | 원 출처 및 확인할 조건 |
|---|---|---|
| Spotify Weekly Top Songs — Global | 주간 곡 순위·스트리밍 수 실습 자료 | [Spotify Charts](https://charts.spotify.com/) · [Spotify Developer Policy](https://developer.spotify.com/policy) · 데이터의 제공 범위·재배포 가능 여부 확인 |
| YouTube Data API v3 | 영상 ID·제목·채널·조회수·좋아요·댓글 | [YouTube Data API](https://developers.google.com/youtube/v3) · [YouTube API Services Terms](https://developers.google.com/youtube/terms/api-services-terms-of-service) · 표시·저장·갱신·이용 조건 확인 |
| Chart.js | 데이터 시각화 JavaScript 라이브러리 | [Chart.js](https://www.chartjs.org/) · 해당 배포 버전의 라이선스 준수 |
| FastAPI / pandas / Jinja2 등 | 웹 서버 및 데이터 처리 | 각 패키지 공식 문서와 실제 설치 버전의 개별 라이선스 준수 |

참고 실습 파일: `regional-global-weekly-2026-10-01.csv`. README에 기록된 집계 기간은 2026-09-25~2026-10-01이다. **파일이 저장소에 있다는 사실은 자유로운 재배포·상업적 이용 허가를 의미하지 않는다.** 데이터 재배포 권한은 별도 검토 대상이다.

## 3. AI 사용 기록 (도구 · 시점 · 역할)

**AI 활용 여부: 있음.** 아래 표는 프로젝트와 관련된 대화·작업 기록에서 확인 가능한 범위를 기준으로 적었다. 날짜는 해당 작업을 기록한 날이며, 모든 코드 줄의 생성 시각을 뜻하지 않는다.

| 도구 | 확인 가능한 사용 시점 | 활용 작업 | 한계 및 책임 |
|---|---|---|---|
| ChatGPT (OpenAI) | 2026-10-07 프로젝트 기록 작성 및 2026-10-20~27 프로젝트 작업·평가 정리 | 기획·구조 정리, 코드/오류 분석 보조, README 설명 및 기사 초안 검토, 라이선스·출처 고지 문서 보완 | AI 출력은 사람이 확인·수정해야 하며, AI 답변 자체는 데이터의 원출처가 아님 |
| GitHub 및 VS Code | 프로젝트 개발·관리 시 사용 | 버전 관리·코드 편집 도구이며 이 표에서 AI 생성 모델로 분류하지 않음 | 실제 수정 사항은 Git 커밋과 파일 내용으로 확인 |

**추가 도구 기록 원칙:** 다른 생성형 AI, 자동 코딩 도구 또는 API를 이 저장소 작업에 사용한 사실이 작업 로그로 확인되면 **정확한 제품명·날짜·기여 범위**를 이 표에 추가한다. 확인하지 못한 도구나 날짜를 추정해 쓰지 않는다.

- **인간의 역할:** 프로젝트 목표와 데이터 해석 기준을 정하고, AI 제안 코드·문장을 채택하거나 수정하며, 제출·공개 여부를 최종 결정한다.
- **검증 한계:** 이 기록은 전체 코드의 AI 생성 비율이나 모든 커밋의 도구별 출처를 정량적으로 입증하는 자료는 아니다.
- **저널리즘 원칙:** AI가 만든 코드·문장·설명은 자동으로 사실이나 법적으로 안전한 자료가 되지 않는다. README의 예시 수치·기사 초안은 작성 당시 학습 기록으로, 최신 관측값이나 독립 검증된 보도가 아니다.

## 4. 인용·출처 표기 및 문구 점검 기록

### 4-1. 실제 README 텍스트 점검 (2026-10-27)

| 점검 대상 | 문구 성격 | 처리 / 근거 |
|---|---|---|
| README의 'Article Draft' 예시 기사 | 이 실습에서 Spotify·YouTube 지표를 해석하기 위해 구성한 기사 초안 | **실습용 초안**으로 표시하고 데이터 원출처를 위 2절에 링크함. 타 기사에서 가져온 직접 인용이라고 확인되지 않음 |
| 'Spotify Weekly Top Songs — Global', 'YouTube Data API v3' 등 명칭 | 제공사 서비스·자료명 | 원 명칭을 유지하고 공식 출처·이용 조건 링크를 2절에 기록함 |
| 'YouTube가 Spotify보다 300배 더 인기 있다' 같은 비교 문장 | 잘못된 해석을 설명하기 위한 반례·교육용 예시 | 실제 검증된 보도 기사에서 따온 인용문으로 제시하지 않으며 오해 방지용 예시임을 명시함 |
| 수업 프로젝트의 자체 설명 및 One-Line Summary | 자체 프로젝트 소개 문구 | 외부 자료에서 복제된 인용으로 확인된 내용은 없음. 다만 이 점검만으로 모든 문장의 독창성을 증명하지는 못함 |

### 4-2. 동일 문장 검색 기록 (2026-10-27)

다음의 README 문구를 따옴표로 묶어 공개 웹 검색에서 **표본 점검**했다.

1. `"K-POP DATA LAB은 Spotify와 YouTube 데이터를 수집"`
2. `"데이터가 어디서 오고" "어떻게 기사로 연결되는지"`
3. `"YouTube 누적 조회수가 해당 주 Spotify 스트리밍 수보다"`

**결과:** 반환된 웹 검색 결과에서 위 세 문구와 **정확히 일치하는 외부 원문을 확인하지 못했다.** 검색 결과에는 요청과 직접 관련 없는 문서도 섞여 있었다. **이는 세 문구에 대한 제한적인 공개 웹 검색 결과일 뿐, 전체 저장소·인터넷·유료 자료의 중복 검사를 마친 것이 아니며 저작권 침해가 없음을 보증하지 않는다.**

### 4-3. 인용·출처 처리 원칙

- 타인의 기사를 **직접 인용**할 때는 인용부호 또는 블록 인용으로 구분하고 **저자·기사 제목·매체·발행일·원문 URL**을 적는다.
- **자료 수치 인용**에는 원 출처와 **대상·날짜·수집 시점·집계 기간·단위**를 함께 기록한다. 현재 README의 예시 통계는 수집 시점과 원자료를 추가 대조할 필요가 있으며, 최신 통계로 사용하지 않는다.
- 다른 사람의 문장을 요약·번역하더라도 출처를 남긴다. 출처 표시는 허락이 필요한 저작물의 **이용 허락 자체를 대체하지 않는다.**
- **추가 검토 필요:** 저장소 내 다른 파일과 화면 문구 전수 조사, 원본 기사·영상 대본 대조, 제3자 데이터·콘텐츠 재배포 권한 확인은 이 README 문구 표본 점검 범위 밖이다.

## 5. 데이터 저널리즘 해석 원칙

- Spotify의 **주간 스트리밍 수**와 YouTube의 **누적 조회수**는 측정 기간과 의미가 서로 다르다.
- 비율을 단순 계산할 수 있어도 '한 플랫폼이 몇 배 더 인기 있다'는 결론으로 바꾸지 않는다.
- 출처·시점·기간·단위·결측·제한을 Fact Sheet나 기사에 함께 남긴다.
- 사실 확인이 불충분한 주장은 확정적으로 보도하지 않고 보류하거나 한계를 명시한다.

## 6. 교육용 프로젝트 고지

이 저장소는 **MBC AI 데이터 저널리즘 교육 과정에서 제작한 실습 프로젝트**이며 MBC나 Spotify, YouTube의 공식 서비스 또는 승인을 받은 보도 상품을 뜻하지 않는다. 소프트웨어 라이선스와 제3자 콘텐츠·데이터의 이용 권한은 구분한다.
