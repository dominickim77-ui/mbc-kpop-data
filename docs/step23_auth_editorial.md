# STEP 23 — 회원가입·로그인 및 기사 검수 권한 관리

기준: `feature/kpop-news-analysis`, STEP 22 `86f4434a927acb2c98f1dfd40f3f849d144fd7eb`.

## 설치와 최초 관리자

운영 적용 전 변경 파일 목록과 이 문서를 확인한다. 기존 MySQL 스키마와 데이터는 변경하지 않는다.
별도 SQLite 파일에 인증·기사 데이터를 저장한다. SQL은 `db/migrations/002_editorial_sqlite.sql`이며
**SQLite 전용**이다. MySQL에서 실행하지 않는다. 새 파일만 생성하며 기존 파일이 있으면 초기화를 거부한다.

1. 승인된 코드 적용 후 프로젝트 루트에서 `python -B -m security.admin init`.
2. 기존 실행 방법으로 서버를 시작하고 `http://127.0.0.1:8000/account`에서 회원가입한다.
3. 로컬 운영 담당자가 `python -B -m security.admin bootstrap --username 등록아이디` 실행 후
   화면에 표시되지 않는 비밀번호 입력으로 해당 계정을 확인한다. 최초 관리자 한 명만 부여할 수 있다.
4. 다시 로그인하고 `/editorial`의 사용자 역할 관리에서 기자·편집자 역할을 부여한다.
   역할 변경은 기존 세션을 폐기하므로 대상 사용자는 다시 로그인해야 한다.
5. 기사 작성자와 최종 편집자를 다른 계정으로 운영한다. 자기 기사 승인은 차단된다.

자동 관리자·기본 비밀번호는 없다. 테스트 계정과 합성 기사는 운영 설치 대상이 아니다.
비밀번호 분실·이메일 인증·공개 서비스용 복구는 이번 최소 범위에 포함하지 않는다.

## 권한표

| 기능 | READER | JOURNALIST | EDITOR | ADMIN |
|---|---|---|---|---|
| Dashboard·데이터 조회·승인 기사 조회 | 가능 | 가능 | 가능 | 가능 |
| 자기 선택 초기화·제거 | 가능 | 가능 | 가능 | 가능 |
| 기존 Add to Analysis(MySQL 쓰기/YouTube 조회 포함) | 차단 | 가능 | 가능 | 가능 |
| 뉴스 근거·무료 초안·명시적 유료 생성 | 차단 | 가능 | 가능 | 가능 |
| 자기 기사 작성·수정·검수 요청 | 차단 | 가능 | 가능 | 가능 |
| 타인 미출고 기사 조회·검수·철회 | 차단 | 차단 | 가능 | 가능 |
| Fact Sheet 사람 검수 등록 | 차단 | 차단 | 가능 | 가능 |
| YouTube 영상 검수 | 차단 | 차단 | 가능 | 가능 |
| 사용자 역할 부여 | 차단 | 차단 | 차단 | 가능 |

CSV 등록은 기존 로컬 운영 CLI를 유지한다. 웹에 CSV 등록 API는 노출하지 않는다.
CSV 등록·기존 파일형 Fact Sheet 검수·정정 CLI는 파일 시스템에 접근하는 신뢰된 운영 담당자만 사용한다.
OS 계정·프로젝트 폴더 접근권한까지 웹 RBAC가 통제하는 것은 아니다.
로그인 기반 새 Fact Sheet 검수는 아래 API로 수행하며 기존 파일형 승인 이력과 분리한다.

## 기사 흐름

`DRAFT → PENDING_REVIEW → ON_HOLD → REVISED → PENDING_REVIEW → APPROVED`.

기자는 주차·제목·본문을 저장하거나 현재 선택곡 무료 초안을 가져온 뒤 저장한다.
Fact Sheet는 기존 STEP 22 검증기로 원본과 대조한 후 서버가 연결한다. 브라우저가 작성자·역할·승인 상태를 지정할 수 없다.
편집자는 본문과 근거 수치·기간·단위·지역·출처를 함께 읽고 네 체크리스트와 의견을 입력한다.
하나라도 실패하면 승인 요청도 `ON_HOLD`로 기록하며 `approval_blocked: true`를 반환한다.
본문 또는 근거를 바꾸면 새 버전이 생기며 다시 검수를 요청해야 한다.
승인·보류 시 최신 기사 버전과 근거 SHA-256을 다시 확인한다. 오래된 화면의 승인은 409로 차단한다.
출고 목록도 근거를 재검증하므로 승인 후 원본이 변하면 공개 목록에서 제외된다.
철회는 `WITHDRAWN` 상태로 남기며 삭제 API를 제공하지 않는다. 검수·수정·역할 변경 이력은 덮어쓰지 않는다.
유료 OpenAI 호출은 기존 명시적 확인 절차를 그대로 유지한다. 생성 결과는 출고 승인이 아니다.

## 저장 구조와 보안

`security/editorial_store.py`가 SQLite 연결과 트랜잭션을 담당한다.
기본 경로 `data/private/editorial.sqlite3`, 선택 환경변수 `KPOP_AUTH_DB`.
테이블: users, sessions, login_limits, articles, revisions, reviews, fact_reviews, audit.
검수·수정·감사·Fact Sheet 기록은 UPDATE/DELETE 방지 트리거로 보존한다.
기존 MySQL tracks/spotify_chart/youtube_stats 및 CSV·Manifest·기존 승인 JSON은 그대로 유지한다.
선택곡은 users.selection에 회원별로 저장한다. 요청별 ContextVar로 사용자를 바인딩하고 서버 측에서만 읽는다.
YouTube 검수 캐시도 계정 ID로 구분한다. 신규 영상 검수 기록에는 검수자 ID를 추가한다.

비밀번호는 랜덤 salt + scrypt(N=32768,r=8,p=3)로 해시한다. DB에는 `salt:hex`만 저장한다.
세션은 32바이트 난수, DB에는 토큰 SHA-256만 저장하며 8시간 후 만료된다.
로그아웃과 역할 변경 시 서버 세션을 폐기한다. 쿠키는 HttpOnly·SameSite=Strict이며 HTTPS에서 Secure를 사용한다.
로그인 실패는 계정별 15분에 10회로 제한한다. 공개 서비스의 IP별 제한은 STEP 24 배포 계층에서 추가 검토한다.
변경 요청에는 기존 고정 localhost/127.0.0.1:8000 Origin 정책을 적용한다.
DB·세션·.env는 Git 제외 대상이다. 소스 적용 후 DB 파일은 별도 보관·백업한다.

## Fact Sheet 검수 API

- `GET /api/editorial/fact-drafts/{week}`: EDITOR/ADMIN이 STEP 22 초안 확인.
- `POST /api/editorial/fact-drafts/{week}/review`: draft_sha256, period_review,
  period_evidence, tracks를 전달한다. tracks의 곡·버전·분류·근거 규칙은 STEP 22와 동일하다.
- reviewer ID와 시간은 서버가 기록한다. 10/08 기존 승인 재작성은 거부한다.
- 새 기록은 fact_reviews에 추가하며 기존 파일을 덮어쓰지 않는다. 원본 변경 시 재검증에서 차단된다.
- 이 데이터 검수만으로 기사가 발행되지 않는다. 기사 출고 체크리스트는 별도다.

## 검증 및 남은 항목

최종 오프라인 회귀: **140 PASS / 0 FAIL / 16 SKIP** (총 156개).
기존 124 PASS를 유지했고 신규 16개 인증·기사·데이터 검수 시험이 추가됐다.
실제 MySQL 시험 16개는 SKIP이며 통과로 계산하지 않는다.
구문 검사 및 기존 원본 4개 CSV 검사 PASS. 유료 API·운영 DB 접근 차단 상태에서 실행했다.
별도 SQLite 테스트 DB에는 실제 쓰기를 수행하고 독립 Python 프로세스로 기사·검수 영속성을 확인했다.
기존 HTTP 회귀는 명시적인 인증 편집자 fixture를 사용하며 실제 인증·권한 차단은 별도 HTTP 시험에서 검증한다.
브라우저 검증은 8023 격리 서버·시험 계정·합성 기사로 수행한다. 실제 사람의 운영 기사 승인을 대행하지 않는다.

실행: `python -X utf8 -B scripts/run_checks.py --report .reports/step23.json`.
기존 Windows 샌드박스 임시 폴더 권한과 출력 인코딩 문제는 시험 환경 오류였고,
허용된 격리 실행 및 UTF-8 출력으로 해결했다.

운영 적용·신규 저장소 초기화·실제 관리자 부여·Commit·Push는 별도 승인/담당자 설정 단계다.
실제 신규 공식 CSV 부족으로 신규 운영 주차 검증은 BLOCKED다.

## STEP 24 인계

MySQL은 유지되고 회원·기사는 별도 SQLite에 있다. PostgreSQL/Supabase 전환 시 테이블·불변 이력·선택곡·세션 정책을 함께 옮긴다.
SQL과 연결 모듈에 SQLite 방언이 있으므로 단순 연결 문자열 교체로 전환할 수 없다.
Vercel의 임시 파일 시스템에 SQLite 파일을 그대로 운영하지 않는다.
배포 환경의 HTTPS·명시적 Origin 허용목록·영속 DB·복수 서버 세션 및 기존 데이터 마이그레이션을 별도 환경에서 검증한다.
