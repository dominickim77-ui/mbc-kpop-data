# 📰 STEP16 — K-POP 뉴스 곡별 Fact Sheet 검수 후보 확장

## 목표
- 사용자가 Current Analysis에서 선택한 **모든 곡**을 대상으로, Spotify·YouTube 동일 기간 주간 CSV의 존재 여부와 추이를 확인한다.
- **BTS SWIM, NORMAL / ROSÉ APT.**처럼 Spotify에만 완전한 2주 수치가 있으면 이를 명확하게 표시한다. YouTube Top 100에 없다고 조회수가 0인 것은 아니다.
- 기존 **LISA SaWaDiKa / KATSEYE Animal**의 사람 검수 기록은 유지한다. **Hootie Frutti**는 리믹스 버전 차이로 보류한다.
- 이 단계는 **검수 후보표(Review Queue) 생성**이며, 미검수 곡의 AI 기사 승인·자동 게시·새로운 K-POP 분류 자동 승인은 하지 않는다.

## 안전한 설치
Windows 11 / VS Code / 프로젝트 루트 `C:\WORKSPACE\mbc-kpop-data`에서 실행:

1. 서버가 실행 중이면 Ctrl+C로 종료.
2. ZIP의 `kpop_step16_patch` 폴더를 `mbc-kpop-data` 안으로 복사.
3. 기존 Git 브랜치가 `feature/kpop-news-analysis`이고 `git status --short`가 비어 있는지 확인.
4. 다음 명령을 **한 줄씩** 실행.

```powershell
python kpop_step16_patch\install_step16.py --dry-run
python kpop_step16_patch\install_step16.py
python kpop_step16_patch\verify_step16.py
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

- 설치 스크립트는 기존 **STEP15 버전 파일을 SHA로 검사**하고, 예상과 달라지면 덮어쓰지 않는다.
- 원래 코드는 **프로젝트 폴더 옆**의 `mbc-kpop-data_step16_backup_YYYYMMDD...`로 백업한다.
- 바뀌는 파일: `news/news_routes.py`, `static/news_panel.js`, `static/style.css`, `templates/index.html`
- 추가하는 파일: `news/review_candidates_step16.py`
- **변경 금지:** `.env`, CSV, MySQL, 기존 Fact Sheet, articles, 기존 검수 기록, Git 브랜치.

## 브라우저 실습
메인 페이지 → Current Analysis에 BTS, ROSÉ, LISA 등을 선택 → 아래 `NEWS ANALYSIS`에서 **📋 검수 대기곡 근거 확인 (무료)** 클릭.

- 선택된 곡의 Spotify 두 주 순위·스트리밍과 YouTube 두 주 순위·주간 조회수, 미확인 상태 표시
- Spotify 음원 링크와 YouTube **대표 영상** 참조 URL을 구분
- 검수 완료 이전에는 `SPOTIFY_ONLY_REVIEW_PENDING`, `DUAL_CHART_REVIEW_PENDING`, `HOLD_VERSION` 등으로 표시
- 새 주차는 기존 Fact Sheet 검수 기록을 자동으로 승계하지 않음
- 이 버튼은 GET 요청만 보내고 OpenAI 요금을 사용하지 않음

## 별도 Python 실행 — MySQL 없이도 무료

```powershell
python -m news.review_candidates_step16
```
기본 데모 4곡(BTS SWIM, NORMAL, ROSÉ APT., LISA SaWaDiKa)을 대상으로 실제 CSV 검수 후보 상태를 표시한다. **현재 선택곡**을 MySQL에서 조회하려면:

```powershell
python -m news.review_candidates_step16 --from-current-analysis
```

인위적으로 선택하려면:

```powershell
python -m news.review_candidates_step16 --selected "BTS|SWIM" --selected "ROSÉ, Bruno Mars|APT."
```

검수 후보 JSON을 `facts/`에 보존하려면 위 명령 뒤에 `--export`를 붙인다. 기존 파일은 덮어쓰지 않는다.

## 검수 기준

| 상태 | 의미 | 기사 사용 |
|---|---|---|
| `DUAL_CHART_REVIEWED` | 기존 승인 Fact Sheet와 원본 주간 수치 일치 | 교차 차트 기사 **초안** 가능(출고 승인은 별도) |
| `DUAL_CHART_REVIEW_PENDING` | 두 플랫폼의 전주·금주 후보 수치 있음 | 버전·아티스트·분류 사람 검수 필요 |
| `SPOTIFY_ONLY_REVIEW_PENDING` | Spotify는 전주·금주 모두 확인, YouTube 자료는 불완전 | Spotify **단독 기사**는 후속 검증 프로세스 설계 필요; 교차 기사는 불가 |
| `YOUTUBE_ONLY_REVIEW_PENDING` | YouTube만 전주·금주 모두 확인 | 검수 필요 |
| `HOLD_VERSION` | 동일 곡의 버전 매칭 불분명 | 제외 |
| `HOLD_FACT_MISMATCH`, `HOLD_AMBIGUOUS` | 근거 수치 불일치·매칭 중복 | 중단 |
| `INSUFFICIENT_OBSERVATIONS` | 연속 2주 자료 부족 | 증감률 계산 불가 |

**주의:** Spotify는 Top 200, YouTube는 Top 100 곡 차트이고 지표 정의가 다르므로 플랫폼 간 수치 비율은 계산하지 않는다. 'YouTube 차트 미진입'은 영상 조회수가 0이라는 뜻이 아니다.

## 향후 단계
사람이 원자료와 음원 버전·편집 분류를 확인한 후, 검수 승인 및 Spotify 단독 근거 기사 옵션을 별도로 설계할 수 있다. **이번 단계에서는 새 곡을 자동 승인하지 않는다.**
