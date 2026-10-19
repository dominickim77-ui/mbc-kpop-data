# STEP20 인수인계

인수인계 기준: 2026-10-19, `feature/kpop-news-analysis`의
`6a423d219b7d1a69407f69170765eef18d14a85b` 실행 결과.
[STEP19 최종 보고서](step19_final_audit.md)의 P1·P2 합의 범위는 해결됐다.
STEP20의 새 기능 범위는 아직 확정하지 않았으며 아래 항목은 후속 제안(PROPOSAL)이다.

## 현재 구조와 데이터 흐름

단일 FastAPI 앱 `app.py`가 Jinja2 templates와 static JS/CSS를 제공한다.
CSV는 주간 차트 근거, MySQL은 곡·Spotify 주차·영상 누적 스냅샷,
JSON은 Fact Sheet와 사람 승인·정정 근거다.

```text
Artist Search / 주차 선택 → Current Analysis
  → Spotify / YouTube 화면 → Compare / Accumulated Analysis
  → CSV·Fact Sheet 재대조 → 무료 preview / 명시적 유료 기사 초안
  → 사람 검수 (자동 출고 승인 없음)

YouTube 후보 → 사람 확인 → 승인 JSON + DB 스냅샷
  → 승인 잠금 → append-only 정정 → ACTIVE 해석 → 화면 표시
```

승인 JSON과 MySQL은 단일 트랜잭션이 아니고 선택 상태·검수 토큰은 프로세스 메모리다.
운영 코드는 `app.py`, `news/`, `security/`에 있으며 과거 패치 payload를 실행 기준으로 삼지 않는다.
`kpop_step18_correction_patch/correct_active.py`는 수동 정정 도구이므로 패치 폴더 전체를 삭제하면 안 된다.

## 첫 작업과 완료 기준

| 순서 | 제안 작업 | 완료 기준 |
| --- | --- | --- |
| 1 | 분리 환경에서 브라우저 전체 흐름 확인 | 검색→선택→플랫폼 화면→주간 비교/그래프→근거→무료 미리보기 확인. 실제 브라우저 정상/거부 폼 요청과 미검수곡 제외 확인 |
| 2 | 승인 경쟁·DB/JSON 중간 실패 시험 | 서로 다른 토큰의 최초 승인 경쟁, DB 실패, commit 후 파일 실패를 임시 기록·모의 API·분리 DB로 재현. 기존 이력을 삭제하지 않는 대조/복구 절차 문서화 |
| 3 | 사용 범위에 따른 상태·식별 정책 확정 | 다중 사용자/다중 worker가 필요할 때 선택 영속화·세션·인증·곡 식별/고유키·새 DB ID 연결 정책 결정 |
| 4 | 작은 유지보수 변경 검토 | Chart.js 버전 고정, 구형 도구 timeout, 역사 패치/백업 역할 구분. 변경별 회귀 확인 |

실제 YouTube 호출·승인 저장·유료 OpenAI 시험은 별도로 범위·할당량·비용과 기록 보존 방법을 정한다.
새 기능이나 배포를 이 인수인계만으로 자동 승인한 것으로 해석하지 않는다.

## 검증 시작 방법

먼저 브랜치·원격 최신 상태와 작업 폴더를 확인하고
[환경 재현 문서](environment_reproduction.md)에 따라 전역 환경과 분리된 인터프리터를 선택한다.
프로젝트 루트에서 해당 가상환경의 Python으로 실행한다.

```powershell
python -B -m pip check
python -B scripts/run_checks.py
```

기본 offline은 운영 DB/API 진입점을 차단한다. 기준 결과는 92건 중 76건 통과·DB 16건 건너뜀이다.
건너뜀을 DB 검증 통과로 보고하지 않는다. 별도의 MySQL 테스트 DB 생성/쓰기/정리가 가능한
시험 환경을 마련한 경우에만 이중 opt-in을 사용한다.

```powershell
python -B scripts/run_checks.py --mode test-db --allow-test-db
```

기준 결과는 스키마 정책 6건과 실제 DB 16건을 합한 22건 통과다.
운영 DB의 스키마·무결성 조회는 쓰기 모드와 구분한다.

```powershell
python -B scripts/run_checks.py --mode db-readonly --database mbc_kpop_data
```

자격 설정은 로컬 .env로 별도 준비한다. 실제 값은 문서·로그·Git에 넣지 않는다.
기본 서버는 직접 연결한 `http://127.0.0.1:8000` 또는 `http://localhost:8000`이며,
다른 host/port·프록시·HTTPS는 출처 보호에 대한 별도 검토와 테스트가 필요하다.
서버 실행은 현재 인터프리터의 `python -B scripts/run_local.py`로 명시적으로 수행한다.

## 보존 및 장애 대응 원칙

- 원본 CSV·Fact Sheet·기사·검수·승인·append-only 정정·실제 .env·운영 DB를
  시험 fixture로 덮어쓰거나 자동 정리하지 않는다. 운영 DB DDL/복구는 별도 계획과 승인 대상이다.
- Animal ACTIVE `m7k9UMcHbr0`와 과거 잘못된 영상 이력을 함께 보존한다.
  과거 기록을 지워 정정 상태를 맞추지 않는다.
- 주간 Spotify 스트리밍, 주간 YouTube 곡 조회수, 영상 누적 조회수를 구분한다.
  미관측을 0으로 만들지 않으며 미검수 곡을 기사에 자동 포함하지 않는다.
- DB/JSON 중간 실패가 의심되면 재승인·재수집을 자동 반복하지 않는다.
  관련 기록과 오류를 보존하고 DB 저장 여부·원본 승인·정정 체인을 읽기 전용으로 대조한 뒤
  복구안을 작성한다. 이는 상세 장애 복구 검증이 완료됐다는 의미가 아니다.
- `db_insert.py`, `youtube_test.py`, `compare_data.py`, `kpop_compare.py`, 패치 설치기는
  쓰기/외부 호출 가능성이 있으므로 일괄 import나 무차별 테스트 수집 대상에 넣지 않는다.
- 코드 복구는 검토한 변경 단위로 수행한다. 운영 데이터·이력의 자동 롤백,
  위험한 reset·force push·main 변경은 하지 않는다.

## 관련 문서

- [STEP19 최종 통합 점검](step19_final_audit.md)
- [환경 재현](environment_reproduction.md)
- [현행 회귀 테스트와 역사 검증의 구분](testing.md)
- [DB 스키마 재현 및 구형 DB 보완](database_reproduction.md)
- [분석 요청 출처 보호](analysis_request_origin.md)
