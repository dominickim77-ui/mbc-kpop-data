# STEP 27A — PostgreSQL 런타임 전환

2026-10-20. 대상: `dominickim77-ui/mbc-kpop-data`,
`feature/kpop-news-analysis`, 시작 HEAD `4b2cf09`.
시작 시 Git 작업 트리는 깨끗했다. 기존 프로젝트에서만 수정했다.

## 구현

- `KPOP_DB_BACKEND=legacy`가 기본값이며 기존 MySQL·SQLite 경로를 유지한다.
  `postgresql`을 명시하면 차트·인증·개인 선택·기사·검수 저장소가 모두
  `KPOP_POSTGRES_DSN`의 PostgreSQL을 사용한다. 연결 실패 시 legacy fallback은 없다.
- STEP 24 스키마/변환 계획/격리 로더를 재사용한다. 실행 중 자동 생성·이전은 없다.
  PostgreSQL에서 `security.admin init`은 거부한다.
- 현재 앱 SQL에 한정한 호환 계층: 바인딩 매개변수, RETURNING ID,
  login_limits/차트 ON CONFLICT, 이름·위치 기반 행 조회, UTC 문자열 시각.
  JSON TEXT와 해시 계산, 비밀번호·세션 형식은 유지한다.
- PostgreSQL 편집 저장소 쓰기는 READ COMMITTED 트랜잭션과 공통
  `pg_advisory_xact_lock(27001)`을 사용한다. 개인 선택, 로그인 제한,
  마지막 관리자, 기사 버전·승인을 읽고 바꾸는 동안 앱 쓰기를 직렬화한다.
  다른 SQL 도구가 이 잠금을 따르지 않는 직접 쓰기는 보호 범위 밖이다.
  이 보수적인 전체 쓰기 잠금은 규모 확장 전 성능 측정이 필요하다.
- 새 주차 Fact Sheet 조회가 SQLite 파일 존재 여부에 묶이지 않도록 변경했다.
  AI 기사 기능은 같은 PostgreSQL 개인 선택·차트·검수 자료를 읽는다.
  기존 파일 기반 원자료·영상 승인·기사 초안 저장 방식은 유지한다.
- UI/템플릿은 변경하지 않았다. 승인된 기사 수정 시 기존 정책대로 REVISED로
  전환하여 공개 목록에서 제외하고 재검수를 요구한다.

## 검증과 한계

최종 오프라인 결과: `.reports/step27a_offline.json` 참조.
오프라인 시험은 임시 SQLite/합성 파일/가짜 DB 및 AI 응답으로 진행한다.
MySQL·PostgreSQL 실제 연결과 외부 API는 실행기가 차단한다.
따라서 오프라인 PASS를 PostgreSQL 실제 동작 PASS로 해석하면 안 된다.

신규 단위 시험은 backend 분기, fallback 차단, SQL/ID/행 호환,
잠금·commit·rollback·close 및 오류 전달을 확인한다.
기존 회귀는 인증/권한/개인 선택/비교/AI 요청 근거/기사 승인·이력 등을 확인한다.
최초 실행의 신규 시험 1건은 오프라인 차단 장치가 설정 검증까지 막아서 실패했다.
물리 접속 경계만 차단하도록 수정했으며 최종 결과를 기준으로 판단한다.

**실제 PostgreSQL 연결·DDL·CRUD·영속성·동시성·트리거: BLOCKED.**
psycopg 미설치. psql/postgres/docker 명령, 기본 설치 경로,
Windows PostgreSQL 서비스 및 제공된 PostgreSQL 환경 변수는 발견되지 않았다.
PostgreSQL 서버 설치, 클라우드 연결, 운영 데이터 이전은 수행하지 않았다.

실제 엔진용 `tests/test_postgres_integration.py`를 추가했다. 기본 실행은 SKIP.
새 빈 로컬 테스트 DB에서 STEP 24 로더로 스키마를 만들고 합성 데이터만 넣는다.
로그인/중복 회원/권한/마지막 관리자/횟수 제한, 차트 upsert·조회, 개인 선택
동시 수정·격리, 새 주차 검수 Fact Sheet/무료 기사 미리보기, 기사 버전·동시 승인,
rollback·재접속·이력 삭제/TRUNCATE 거부를 확인하도록 준비했다.
이 시나리오 자체는 아직 실제 서버에서 실행·검증하지 못했다.
유료 AI API·브라우저 전체 흐름·DB 서버 재시작 후 보존은 별도 미실시다.

## 실제 시험에 필요한 환경

1. 로컬 PostgreSQL 서버와 새 **빈** DB `kpop_step24_test_<고유이름>`.
   운영 DB를 사용하거나 기존 DB를 지우지 않는다. 재시험도 새 빈 DB를 준비한다.
2. 기존 프로젝트 안의 격리 Python 환경에 `requirements-postgres.txt` 설치.
   현재 전역 패키지는 변경하지 않았다. 선택적 psycopg 의존성의 정확한 버전은
   설치 및 실제 시험 시 기록·고정해야 한다.
3. 세션에 `PYTHON_DOTENV_DISABLED=1`, `STEP27_RUN_POSTGRES_TESTS=1`,
   `KPOP_POSTGRES_TEST_DSN` 설정. DSN에는 localhost 호스트와 전용 DB 이름을
   명시한다. 비밀번호/DSN을 보고서·Git·명령 출력에 남기지 않는다.
4. `python -B -m unittest tests.test_postgres_integration -v` 실행.
   로더는 기존 테이블이 있으면 거부하고, 테스트는 DB를 삭제하지 않는다.
   합성 검수 이력은 DB에 남으므로 다음 실행은 새 빈 DB를 사용한다.
5. 추가로 비소유자 앱 계정의 최소 권한, 역할 변경 경쟁, 로그인 경쟁,
   DB 서버 재시작 후 보존 및 실제 AI·브라우저 흐름을 검증한다.

## 남은 문제와 STEP 27B

- STEP 24에서 남긴 MySQL/PostgreSQL 문자열 비교·대소문자·악센트
  UNIQUE 차이는 해소되지 않았다. 실제 이전 전 충돌·collation 검증이 필요하다.
- 기본 앱 쓰기 잠금의 실제 엔진 동작 및 서비스 규모에서의 대기 시간을
  검증해야 한다. DB 소유자는 이력 트리거를 제거할 수 있으므로 운영 권한 검증도 필요하다.
- 원자료 CSV, 영상 검수, 기사 초안은 여전히 파일 저장소를 사용한다.
  Vercel의 파일 영속성과 배포 구성은 이번 범위 밖이며 STEP 27B에서 별도 설계해야 한다.
- `db_insert.py` 등 과거 MySQL 전용 수집 스크립트는 그대로 보존했다.
  PostgreSQL 모드로 전환하는 대상은 웹 앱 런타임이며 이 스크립트로 이전하지 않는다.
- **STEP 27B 배포 진행은 보류**: 실제 PostgreSQL 시험 및 위 호환성 확인 전
  배포 준비 완료로 판단하지 않는다.

운영 MySQL·SQLite 및 기존 검수 기록에 대한 쓰기·마이그레이션은 수행하지 않았다.
Commit/Push, Supabase 연결, Vercel 배포도 수행하지 않았다.

## 변경 파일

- `.env.example`
- `app.py`
- `db/postgres_runtime.py` (신규)
- `news/editorial.py`
- `news/weekly_facts.py`
- `security/editorial_store.py`
- `security/admin.py`
- `scripts/offline_worker.py`
- `requirements-postgres.txt` (신규)
- `tests/test_postgres_runtime.py` (신규)
- `tests/test_postgres_integration.py` (신규)
- `docs/step27a_postgresql.md` (이 보고서)

Git 제외 산출물: `.reports/step27a_offline.json`.
