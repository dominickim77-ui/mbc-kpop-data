# 현행 회귀 검증

프로젝트 루트에서 아래 명령을 사용한다. 다른 디렉터리에서는 script의 절대 경로를 지정해도 된다.

```powershell
python -B scripts/run_checks.py
```

기본은 `offline`이다. 같은 인터프리터로 구문 검사, tests/ 현행 회귀, 주간 CSV 형식 검증을
명시적으로 실행한다. 작업 경로·UTF-8·pyc 비생성을 고정한다. 기본 모드는 상속된
`STEP19_RUN_DB_TESTS=1`을 0으로 바꿔 실제 DB 통합 테스트가 우연히 실행되지 않도록 한다.

작업자는 실제 `.env` 로딩과 DB 연결·프로젝트의 외부 API 진입점을 차단한다.
격리된 ASGI 요청·모의 DB·임시 승인/정정 기록만 사용한다. 이 진입점 차단은 OS 네트워크
샌드박스가 아니므로 임의의 새 수집 스크립트를 목록에 넣어서는 안 된다.
실행 과정의 성공·실패·건너뜀·예상 실패를 구분하고, 실패/시간 초과는 최종 비정상 종료로 전달한다.
테스트가 의도적으로 발생시키는 INSERT/commit 오류 메시지는 장애 주입이다.

JSON 보고서를 원하면 Git 제외 경로에 명시적으로 저장한다.

```powershell
python -B scripts/run_checks.py --report .reports/offline.json
```

현재 검증은 승인·정정 모듈의 운영 news/ 코드를 대상으로 한다. 테스트 지원 코드는
`tests/support/`에 있고 실제 facts/의 특정 song_id나 설치 패치 사본에 의존하지 않는다.
P1 저장 보호와 분석 요청 출처 검증도 같은 suite에 포함한다.

## 명시적 DB 모드

운영 DB를 조회할 필요가 있을 때에만 읽기 전용 검사를 선택한다.

```powershell
python -B scripts/run_checks.py --mode db-readonly --database mbc_kpop_data
```

별도 MySQL 테스트 DB 생성/쓰기/정리는 다음의 이중 opt-in이 필요하다.
기존 DB 가드는 유지되며 운영 DB 적용 기능이 아니다.

```powershell
python -B scripts/run_checks.py --mode test-db --allow-test-db
```

기본 오프라인 실행의 건너뜀을 DB 통합 테스트 통과로 보고하지 않는다.
모드별 접근·정리 정책은 [DB 문서](database_reproduction.md)를 참고한다.

## 과거 검증과 위험한 자동 수집의 구분

STEP11/16 verify는 과거 UI ID·payload 바이트 일치를 검사하는 설치 시점의 도구다.
현행 앱의 합격 기준이 아니며, 이들을 맞추기 위해 운영 UI를 과거로 되돌리지 않는다.
STEP17A/17B·STEP18의 현재 기능 단언은 tests/의 현행 테스트에 포함한다.
기존 STEP18 직접 verify 명령도 실행 경로를 보정했지만 기본 검증은 tests/를 사용한다.

`db_insert.py`, `youtube_test.py`, `compare_data.py`, `kpop_compare.py`나 패치 설치기는
DB·API·파일 작업을 할 수 있다. 저장소 전체를 무차별 import하거나 pytest로 수집하지 않는다.
새 테스트 프레임워크를 도입하지 않고 unittest를 유지한다.

## 안전한 CLI 경로 점검

```powershell
python news/weekly_changes.py --help
python -m news.weekly_changes --help
python news/review_tracks.py --help
python -m news.review_tracks --help
```

`--help`는 결과 파일을 생성하지 않는다. 실제 main 실행은 기존 CSV/검수 결과를 쓸 수 있으므로
실행 경로 점검을 이유로 운영 자료를 재생성하지 않는다.
