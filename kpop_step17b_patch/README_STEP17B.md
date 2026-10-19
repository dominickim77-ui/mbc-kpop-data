# STEP 17B — YouTube 영상 매칭과 사람 검수

이 패치는 기존 K-POP DATA LAB의 검색 결과 첫 번째 영상을 자동 저장하는 위험한 동작을 중지합니다. 실제 Spotify·YouTube Global Weekly Top Songs CSV 분석은 그대로 유지합니다.

## 변경 사항

- `app.py`: 새 곡은 Spotify 정보를 저장하고 `Current Analysis`에 추가하지만, YouTube 영상은 **PENDING**으로 둡니다. 이전 MySQL `youtube_stats` 기록은 삭제하지 않습니다. 영상이 없는 곡도 화면에 표시되도록 `LEFT JOIN`을 사용합니다.
- `YouTube Data`: 기존 자동 연결 기록을 **미검수**로 명시합니다. 승인 기록이 없는 영상은 공식 MV라고 주장하지 않습니다.
- 새 `/api/youtube-video-review/candidates`: 선택된 곡의 YouTube API 후보 최대 5개 + 해당 주간 공식 차트 CSV 대표 영상(있을 경우)을 제공합니다. 단순 검색 결과나 공식 차트의 영상 URL도 **자동 승인하지 않습니다**.
- 승인 버튼: 사용자가 **공식 채널, 곡명·버전, 누적 조회수 구분**을 직접 확인한 뒤 승인합니다. 새 영상 스냅샷은 MySQL에 **추가**되며 기존 영상 기록은 삭제하지 않습니다. `facts/youtube_video_reviews/`에 검수 기록을 저장합니다.
- 새 영상 통계 `viewCount`는 그 영상 한 편의 **누적 조회수**이고 YouTube Global Weekly Top Songs `Views`는 곡 단위 **주간 조회수**입니다. 혼용하지 않습니다.
- 기존 기사 Fact Sheet 및 출고 승인 상태는 바꾸지 않습니다.

## 실행 순서 (Windows PowerShell, 프로젝트 루트)

1. FastAPI 서버 종료: `Ctrl+C`
2. ZIP 압축을 풀고 `kpop_step17b_patch` 폴더를 `C:\WORKSPACE\mbc-kpop-data\`에 넣습니다.
3. 먼저 `git status -sb`로 코드가 깨끗한지 확인합니다. 기존 GitHub 개발 브랜치의 STEP17A 코드와 다르면 패치가 안전하게 중단됩니다.
4. 다음 명령어 실행:

```powershell
python kpop_step17b_patch\install_step17b.py --dry-run
python kpop_step17b_patch\install_step17b.py
python kpop_step17b_patch\verify_step17b.py
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

5. 브라우저에서 `http://127.0.0.1:8000`에 접속하고 `Current Analysis`에 검수할 곡을 추가합니다.
6. `YouTube Data` 아래 **YouTube 영상 ID · 공식 채널 검수**에서 곡을 선택한 뒤 `영상 후보 확인`을 누릅니다. API 할당량이 사용될 수 있으므로 반복 조회를 피하세요. 같은 선택은 15분 동안 서버 메모리에서 재사용합니다.
7. 후보 링크를 직접 열어 검토하고, 세 가지 확인 항목에 체크한 뒤에만 `확인한 Video ID 승인·저장`을 누릅니다. 이 단계만 YouTube API + MySQL 읽기/쓰기를 수행합니다.
8. 승인 후 페이지를 새로고침하여 `YouTube Data`의 **확인한 영상** 표기를 확인합니다.

## 중요한 제한

- 채널명에 `VEVO`, `HYBE`, `Official` 등이 들어 있다고 공식 인증한 것으로 보지 않습니다.
- 이번 검수는 **영상 ID 매칭 승인**이지 음악 차트 검수나 기사의 최종 출고 승인이 아닙니다.
- 기존 `youtube_stats`에 저장된 다른 영상의 이력을 삭제하거나 정정하지 않습니다.
- 로컬 단일 사용자 수업용이며, 외부 공개 서버용 인증·승인 워크플로우가 아닙니다.
- 실 API 호출/Windows MySQL 테스트는 **사용자 PC에서 수행하기 전까지 미검증**입니다. 제공된 검증 스크립트는 요청과 DB를 모의 처리합니다.
- API 키는 `.env`에만 유지해야 하며, 캡처·GitHub에 올리지 마세요.

## GitHub 저장 전

수정·추가되는 코드: `app.py`, `templates/index.html`, `news/youtube_video_review_step17b.py`, `static/youtube_video_review_step17b.js`, `static/youtube_video_review_step17b.css`.

`kpop_step17b_patch/`, `.env`, `__pycache__/`, 생성된 API 기록 및 기사 검수 초안은 필요한 경우 별도로 보존하고, 코드와 혼동하여 무조건 `git add .` 하지 않습니다.
