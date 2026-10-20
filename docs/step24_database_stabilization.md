# STEP 24 — 데이터베이스 통합 준비 및 안정화

기준일: 2026-10-20. 기준 브랜치 `feature/kpop-news-analysis`,
커밋 `fa01d88211ea9af372ff72825256ba3f50d84b80`.
로컬 HEAD와 원격 브랜치의 일치를 확인했다. 클라우드 배포 단계가 아니다.

## 범위와 실제 상태

기존 앱은 계속 MySQL + SQLite를 사용한다. 연결 문자열만 PostgreSQL로 바꾸면
동작하지 않는다. 이번 변경은 별도 PostgreSQL 스키마, 변환 계획 생성기,
격리 DB 로더, 오프라인 시험과 이전 절차다. PostgreSQL에서 FastAPI 전체가
동작하는 런타임 어댑터를 완성했다는 뜻이 아니다.

`psql`, `postgres`, `docker` 명령과 기본 PostgreSQL 설치 폴더를 발견하지 못했다.
실제 PostgreSQL 스키마 생성·CRUD·트리거·롤백·재접속 영속성은 BLOCKED다.
설치나 클라우드 DB 생성으로 작업 범위를 확대하지 않았다.

## 저장 구조

| 저장소 | 내용 | 연결·보호 |
|---|---|---|
| MySQL | tracks, spotify_chart, youtube_stats | song_id PK/FK, RESTRICT, Spotify 곡/주차 및 YouTube 영상/수집시각 UNIQUE |
| SQLite | users, sessions, login_limits | username UNIQUE, 역할 CHECK, 사용자 FK, scrypt 해시, 토큰 SHA-256, Unix 초 |
| SQLite | articles, revisions, reviews, fact_reviews, audit | 작성자·검수자 FK, 기사/버전 UNIQUE, 상태/결정 CHECK, 이력 UPDATE/DELETE 금지 |
| 파일 | CSV, Manifest, Fact Sheet, 영상 승인·정정, 기사 원본 | 상대 경로와 SHA-256이 근거. DB 통합만으로 대체하지 않음 |

회원 selection은 song_id의 JSON 배열이며 기존 DB에서 FK가 아니다.
변환 계획은 없는 song_id를 거부한다. fact_ref와 JSON 내부의 파일 참조 역시
SQL FK가 아니므로 파일 존재·해시·내용 검증을 별도로 수행해야 한다.
MySQL 구조 분석은 저장소 schema_manifest.json 기준이며 운영 DB를 조회하지 않았다.

## PostgreSQL 설계

- `003_postgresql_prepare.sql`: 11개 테이블. identity로 ID 자동 발급,
  원래 ID의 명시적 INSERT 허용. 기존 FK/UNIQUE/CHECK를 유지한다.
- `004_postgresql_sequences.sql`: 데이터 삽입 후 sequence를 MAX(id)에 맞춘다.
  빈 테이블은 첫 ID 1. 운영 테이블에 직접 실행하지 않는다.
- history 4개 테이블은 UPDATE/DELETE뿐 아니라 TRUNCATE도 트리거로 거부한다.
  DB 소유자는 트리거를 제거할 수 있으므로 향후 앱 계정에 소유자/DDL 권한을 주지 않는다.
- JSON은 이번 준비 단계에서 TEXT + JSON 파싱 CHECK를 선택했다. JSONB로
  재직렬화하면 공백·키 순서가 달라질 수 있다. 기존 evidence_hash와
  news.editorial.digest 규칙, 원본 JSON 문자열을 유지한다.
- SQLite UTC 시각은 기존 문자열 형식을 유지한다. Unix 초는 BIGINT다.
  MySQL DATETIME은 TIMESTAMP WITHOUT TIME ZONE으로 옮기고 시간대를 추정하지 않는다.
- 비밀번호 salt:hex와 scrypt 매개변수는 변경하지 않는다. 세션 해시도
  계획 생성 시 그대로 보존한다. 실제 전환 때 기존 세션 폐기·재로그인은
  별도 승인된 정책으로 적용하고 감사 기록을 남긴다.

**남은 호환성 조건:** MySQL utf8mb4_0900_ai_ci와 PostgreSQL 기본 문자열
비교는 동일하지 않다. 특히 youtube_video_id의 UNIQUE는 MySQL에서
대소문자·악센트 비구분이다. 현 SQL의 PostgreSQL UNIQUE는 이를 완전히
재현하지 않으므로 실제 전환 전 ICU collation 후보와 운영 자료의 충돌을
격리 DB에서 비교해야 한다. 이 의미 차이는 BLOCKED이며 운영 적용 금지 조건이다.
날짜·정수 범위·문자열 길이도 실제 PostgreSQL 입력 검증이 최종 기준이다.

## 코드 사용과 한계

`db.postgres_prepare.plan(snapshot)`은 11개 테이블을 모두 포함한 사전형
스냅샷을 받는다. 테이블별 값은 전체 컬럼을 가진 행 사전 목록이다.
원본에 접속하거나 파일을 덮어쓰지 않는다. SQLite 관계/역할/상태 제약,
JSON, 곡 참조, 차트 중복을 검사한 뒤 `%s` 매개변수 INSERT 계획을 반환한다.
반환값에는 비밀번호 해시 등이 있으므로 출력·Git 저장하지 않는다.

`db.postgres_test_loader.load(connection, snapshot, allow_test_database=True)`는
psycopg 3 연결을 받는 선택적 시험용 진입점이다. localhost,
`kpop_step24_test_...` 이름, 시작 전 유휴 트랜잭션, 빈 DB를 요구한다.
하나의 트랜잭션에서 스키마·INSERT·sequence·행 수를 처리한다.
실패 시 트랜잭션 롤백하며 기존 DB 삭제/복구 기능은 없다.
현재 테스트는 거부 가드만 실행했으며 성공 경로는 PostgreSQL 부재로 BLOCKED.
psycopg는 전역 설치하지 않았고 기존 requirements를 변경하지 않았다.

향후 앱 어댑터에서 해결할 항목:
`?`→`%s`, `lastrowid`→`RETURNING`, `INSERT OR REPLACE`→명시적
`ON CONFLICT DO UPDATE`, sqlite3.Row/IntegrityError 변환, PRAGMA 제거,
`BEGIN IMMEDIATE` 대신 행 잠금과 동시 수정 제어.
특히 기사 승인·역할 변경·마지막 관리자 보호·로그인 횟수 변경의 경쟁 상태를
실제 PostgreSQL에서 검증해야 한다. SQLite 전용 코드를 그대로 재사용하지 않는다.

## 승인 후 이전·복구 절차

1. 쓰기를 멈출 시간과 대상 DB·파일 목록을 승인받는다. MySQL 일관된 읽기
   스냅샷, SQLite backup API를 이용한 일관된 사본, 파일의 상대 경로/바이트/
   SHA-256 목록을 각각 보관한다. 실행 중 SQLite 파일만 단순 복사하지 않는다.
2. 비밀키와 해시를 로그에 출력하지 않고 기존 DB의 행 수·PK·FK·NULL·중복,
   원본 파일의 경로/해시를 기록한다. ID를 재번호 매기지 않는다.
3. 별도의 새 PostgreSQL 테스트 DB에서만 스키마와 스냅샷을 로드한다.
   운영 대상은 로더가 거부한다. collation과 타입 차이가 있으면 중단한다.
4. 테이블별 행 수뿐 아니라 PK별 모든 값, JSON 원문, 해시, 원본 근거 파일,
   비밀번호 검증, 세션 정책을 비교한다. 합성 데이터로 UNIQUE/FK/CHECK/
   이력 변경 거부·실패 롤백·재접속·sequence 후속 INSERT를 시험한다.
5. 실제 앱 어댑터를 별도로 완성한 뒤 회원 격리, 권한, 자기 승인 금지,
   최신 기사 버전/근거 해시 대조, 승인 후 수정 차단을 회귀 시험한다.
6. 최종 배포는 STEP 27에서 별도 승인한다. 실패하면 전환을 중단하고
   원본 저장소를 유지한다. 새 DB나 원본을 자동 삭제하지 않는다.
   운영 복구가 필요하면 마지막 일관된 백업과 쓰기 발생분을 먼저 비교하고
   복구 대상을 다시 승인받는다.

## 로컬 실행

확인한 Python은 3.14.7이며 FastAPI/uvicorn/pandas import 성공.
기존 전역 패키지는 변경하지 않았다.

```powershell
cd C:\WORKSPACE\mbc-kpop-data
python -B scripts/run_local.py
```

기존 실행기는 127.0.0.1:8000을 사용한다. 먼저 포트 점유를 확인하고,
사용 중이면 기존 서버를 종료하지 말고 해당 서버의 소유·환경을 확인한다.
임의로 다른 포트로 옮기면 Origin 검증이 거부하므로 보안 허용목록을 임의 확대하지 않는다.
정상 운영 화면은 기존 MySQL 설정과 초기화된 SQLite가 필요하다.
이미 있는 SQLite에 init을 다시 실행하지 않는다.
패키지가 없으면 독립 `.venv`를 만들고 해당 Python으로 requirements-dev.txt를 설치한다.

브라우저 시험 중 접속 대상 확인 오류가 있었다. 격리 서버를 실행하려 했지만
그 프로세스는 준비를 마치지 못했다. 샌드박스의 포트 조회에서 기존 프로세스가
보이지 않아 빈 포트로 잘못 판단했고, 브라우저는 기존 C:/WORKSPACE 서버에
접속했다. 권한을 확장한 읽기 전용 포트 조회에서 기존 서버임을 확인했다.
기존 서버에서 `step24_browser` 계정이 생성됐고 로그인·로그아웃했다.
이를 격리 DB 시험으로 분류하지 않는다. 테스트 계정과 SIGNUP 감사 기록은
임의 삭제하지 않는다. 기존 서버도 종료하지 않았다.
회원가입·로그인·READER 화면·로그아웃과 Dashboard/Spotify/YouTube/Compare/
NEWS ANALYSIS 영역 표시는 실제 브라우저에서 확인했다. 실제 차트 값,
직원별 기사 작성/검수 브라우저 흐름, 유료 AI 호출은 확인하지 않았다.
READER의 NEWS ANALYSIS 접근은 권한 거부가 표시되며 이를 기사 생성 PASS로
계산하지 않는다. 전체 업무 흐름의 확인은 별도 자동 회귀 시험 결과와 구분한다.

재발 방지: Windows 샌드박스의 빈 프로세스/포트 조회를 포트 미사용의 증거로
삼지 않는다. 실행 완료 로그, 포트 소유 PID, 해당 PID의 프로젝트 경로와
테스트 DB 경로를 모두 확인한 후에만 브라우저 쓰기 시험을 시작한다.

Windows 안정화 수정: `scripts/run_checks.py`의 부모 출력도 UTF-8로 고정했다.
기존 코드에서는 작업자가 UTF-8로 보내는 한글/이모지를 cp949 파이프로
출력하다 UnicodeEncodeError가 발생해 최종 보고서가 저장되지 않았다.
cp949 출력 환경을 재현한 별도 회귀 시험을 추가했다.
