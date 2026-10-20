# STEP 25 평가 항목 대조표

2026-10-20 사용자 제공 상세 평가 기준. CONFIRMED COMPLETE는 아래 명시한 범위의 구현·시험·산출물을 확인했다는 의미이며 전체 과제 제출 완료를 뜻하지 않는다.

| 평가 항목 | 기존 구현 | 부족한 부분 | 필요한 작업 | 증거 위치 | 우선순위 |
|---|---|---|---|---|---|
| 01 도메인 기획 — CONFIRMED COMPLETE | K-POP 차트 비교와 사람 검수 | 주요 독자·검토 계획 통합 문서 보완 완료 | 제출 답안 참조 | docs/step25_submission.md §1 | 완료 |
| 02 기능·화면·DB 설계 — CONFIRMED COMPLETE | FastAPI·MySQL·SQLite | 통합 기능정의·화면구성·11테이블 ERD 보완 완료 | 코드·설계 연결 유지 | docs/step25_submission.md §2–3, db/migrations/002_editorial_sqlite.sql | 완료 |
| 03 수집·MySQL 저장 — CONFIRMED COMPLETE | Spotify·YouTube 수집·저장 | 실제 저장·스키마 증거 확보 완료 | 기존 수집 재실행 불필요 | .reports/mysql-readonly.json, db_insert.py, news/chart_import.py | 완료 |
| 04 CRUD·오류·영속성 — CONFIRMED COMPLETE | 기사 생성·조회·수정·철회, 검증 오류 | 격리 SQLite·MySQL 증거 확보 완료 | 삭제 대신 이력 보존 철회임을 설명 | tests/test_editorial_auth.py, .reports/step25-targeted-initial.log, .reports/step25-mysql-isolated.json | 완료 |
| 05 Fact Sheet·AI 기사·Git 3회 — CONFIRMED COMPLETE | 실제 기존 AI 기사·Fact Sheet·커밋 4개 확인 | 새 생성의 프롬프트·입력 지문 저장 추가 완료 | STEP 25 조건부 승인 확보, 원격 결과 Notion 참조 | news/provenance.py, articles/draft_openai_20261008.json, docs/step25_submission.md §5·8 | 완료 |
| 06 공통 오류 초안 검수 — BLOCKED | 기존 자체 기사 편집 비교는 존재 | 선생님 지정 원자료·오류 초안 미확보 | 사용자 자료 수령 후 대조·수정 | articles/editorial_review_20261008.md는 대체 증거가 아님 | P0 |
| 07 근거 대조·승인 차단 — CONFIRMED COMPLETE | 4항목 검수, ON_HOLD→REVISED→APPROVED, 자기 승인 차단 | 격리 실행 증거 확보 완료 | 실제 직원 브라우저 전체 흐름은 STEP 26 | news/editorial.py, tests/test_editorial_auth.py | 완료 |
| 08 지침 v1·원본 3건 — PARTIAL | 기존 학습 노트 유지 | 원본 DB·3건·지침은 있으나 최근 3일 조건 미충족 | 최근 기사 확보 후 연결 초안 보완 | docs/step25_news_evidence.json, Notion 원본 DB | P0 |
| 09 생성·등록·v1/v2 비교 — CONFIRMED COMPLETE | 기존 앱 기사 저장 재사용 | Notion에 동일 원본으로 초안 2건·비교표 등록 완료 | 사람 출고 승인 전 검토 대기 유지 | Notion 생성 DB·지침 비교표, docs/step25_news_evidence.json | 완료 |
| 10 정기 자동화 — PARTIAL | 예약 k-pop ACTIVE | 예약 시각 실제 실행 증거 없음 | 다음 09:00 실행 후 결과·등록 링크 확인 | 앱 자동화 k-pop, Notion STEP 25 수동 실행 기록 | P0 |

## 추가 제출 항목

- README·SQL·테스트 결과: 연결 완료.
- 비밀키: 현재 `.env`·운영 SQLite Git 제외 확인. 과거 전체 이력 무노출 보증 아님.
- 실제 화면: `.reports/step25-login.png`. 전체 차트·직원 검수 화면은 STEP 26.
- GitHub: https://github.com/dominickim77-ui/mbc-kpop-data/tree/feature/kpop-news-analysis
- Notion: https://app.notion.com/p/3ff16efa972b819eaef9edbab9935ee9
- 작업 대화 공유: https://chatgpt.com/s/cx_6ad6df665a6c819199d8c8d948b35df8
- DOCX: 제출 답안지 작성 후 별도 전달. Windows 번들에 LibreOffice가 없어 DOCX 페이지 렌더 검증은 미완료.
- Commit·Push: 사용자 조건부 승인 확보. 실제 반영 결과는 Notion 종료 기록 참조. 운영 데이터 변경과 STEP 25 배포는 하지 않는다.

## 종료 시 추가 확인한 제출 조건

사용자가 2026-10-20 승인한 12개 파일의 Commit·Push 범위로 종료한다. 실제 커밋·원격 SHA 확인 결과는 Notion STEP 25 종료 기록을 참조한다.
원본 기사 발행일은 2026-01-16, 2025-08-05, 2026-10-16이다. 2026-10-20 제출 기준 선생님 예시의 최근 3일 조건을 충족하지 않는다. 기존 3건은 지침 비교 자료로 보존하고, 최근 3일 조건에 맞는 원본 확보 및 연결 초안 보완을 STEP 26 잔여로 인계한다.
따라서 항목 08은 PARTIAL로 정정한다. 최종 분류는 확인 완료 7개, PARTIAL 2개(08·10), BLOCKED 1개(06)다.
기존 DOCX·ZIP은 승인 전 산출물로, Word 화면 검증과 항목 08·종료 상태의 갱신이 필요하다. 이번 단계 종료는 전체 과제 완료나 배포 완료를 뜻하지 않는다.
