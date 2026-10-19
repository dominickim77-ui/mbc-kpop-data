# STEP 17A — Spotify 단독 검수 초안 (무료)

## 목적

BTS `SWIM`, `NORMAL`, ROSÉ·Bruno Mars `APT.`처럼 Spotify 두 주 기록은 있으나 공식 YouTube Top Songs 100위권에 일치 기록이 없는 곡을, **Spotify 단독 기사 후보**로 확인한다.

이 버전은 기사 출고 승인 기능이 아니다. YouTube 미진입을 조회수 0으로 처리하지 않는다. 곡명·아티스트·버전·분류는 별도 사람 검수 대상이다. **OpenAI API는 호출하지 않는다.**

## 설치

프로젝트 최상위 `mbc-kpop-data/`에 `kpop_step17_patch/`를 복사한다. FastAPI 서버를 먼저 종료한다.

```powershell
python kpop_step17_patch\install_step17.py --dry-run
python kpop_step17_patch\install_step17.py
python kpop_step17_patch\verify_step17.py
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

NEWS ANALYSIS에서 `🎵 Spotify 단독 검수 초안 (무료)` 버튼을 클릭한다. Spotify 두 주의 원본 CSV 수치만으로 작성된 검수용 글이 버튼 아래에 나타난다.

### 준비 조건

- 기존 `feature/kpop-news-analysis` 브랜치의 STEP16 코드 상태
- Spotify·YouTube 2026.09.25~10.01 / 10.02~10.08 원본 CSV 4개
- 브라우저 Current Analysis에 BTS·ROSÉ 등 선택곡

설치는 원래 코드 파일의 Git blob SHA가 확인된 상태에서만 가능하며, 원본 코드 3개 파일을 프로젝트 바깥에 자동 백업한다. `.env`, 원본 CSV, 기존 기사, 승인 기록은 수정하지 않는다. 새 검수 대상의 **유료 AI 생성은 사람 승인 기능을 추가할 다음 단계에서만 허용한다.**

### YouTube 영상 식별 문제

기존 `app.py`의 `search.list maxResults=1`은 잘못된 공식 영상이나 유사 영상을 선택할 수 있다. 이 패치는 **해당 YouTube DB 데이터를 기사 근거로 사용하지 않는다**. STEP17B에서 공식 채널·영상 ID 확인 및 재연결 절차를 개선한다.
