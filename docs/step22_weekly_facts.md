# STEP 22 — Weekly Fact Sheet & AI News Integration

기준 커밋: `1e88cfeae6cd0759902511d72746a03f0e447e8e`, 브랜치 `feature/kpop-news-analysis`.

등록 Manifest → 원본 4개 재검증 → 주차별 DRAFT → 사람의 기간·곡·버전·편집 분류 검수 → 무료 Preview 또는 명시적 유료 AI 초안 → 별도 사람 출고 검수.

## 사용법

프로젝트 루트에서 `python -B -m news.weekly_facts --week-end YYYY-MM-DD`를 실행한다.
기본은 읽기 전용이며 Fact Sheet와 빈 review_template을 출력한다. `--apply`는
`facts/weekly/YYYY-MM-DD/draft.json`을 신규 저장하며 기존 파일을 덮어쓰지 않는다.
운영 데이터 생성은 담당자 승인 후 실행한다. 10/08 기존 Fact Sheet는 이 명령으로 저장할 수 없다.

출력의 `review_template`을 별도 JSON으로 저장하고 실제 사람이 검수한다.
`week_end`, `draft_sha256`은 해당 초안 값을 유지한다. `reviewer`, 시간대 포함 ISO `reviewed_at`,
`period_review: CONFIRMED_COMPARABLE_PERIODS`, `period_evidence`에 실제 집계 기간·시간대 확인 근거를 적는다.
`tracks`에는 확인을 완료한 후보만 다음 형태로 기록한다. 미검수 곡을 이 목록에 추가하지 않는다.

```json
{
  "candidate_id": "초안 candidates의 해당 식별자",
  "identity_review": "CONFIRMED_SAME_SONG",
  "version_review": "CONFIRMED_SAME_VERSION",
  "editorial_category": "KPOP_SOLO",
  "evidence": "실제 곡·녹음 버전·분류 확인 근거"
}
```

허용 편집 분류는 기존 정책과 같은 `KPOP_SOLO`, `KPOP_RELATED_GLOBAL`이다.
자동 이름 매칭은 후보일 뿐이다. source_rows에 각 플랫폼의 원래 표기를 함께 보존한다.
4개 원본 모두에서 유일하게 식별되고 증감률 계산이 가능한 곡만 이번 기사 경로에 사용한다.
미관측/중복/기준값 0인 후보는 null을 유지하고 기사 사용을 보류한다.

`python -B -m news.weekly_facts --week-end YYYY-MM-DD --review 사람검수.json`으로 검증한 뒤,
담당자 승인 후 `--apply`를 붙이면 별도 `reviewed.json`이 생성된다. DRAFT는 보존된다.
검수 JSON은 로컬 담당자의 확인 진술이며 로그인 기반 승인 서명은 아니다. 역할별 접근 제어는 STEP 23 범위다.
수정이나 철회 시 운영 파일을 임의 삭제·덮어쓰기하지 말고 담당자가 이력을 보존한 별도 절차로 처리한다.

## 웹사이트 및 기사

기존 Dashboard에서 주차를 선택하면 NEWS ANALYSIS가 해당 주차 상태와 선택곡의 승인/제외 사유를 표시한다.
검수 대기곡 근거 확인 버튼으로 기존 원본 비교표를 확인한다. 주차별 Fact Sheet 생성·사람 검수 등록은 위 CLI로 수행한다.
새 주차 검수가 없거나 원본/Manifest/계산/검수 지문이 달라지면 무료·유료 기사 생성을 차단한다.
승인된 일부 곡과 미검수곡을 함께 선택하면 승인된 곡만 기사 근거에 포함한다.
10/08 수정 기사 예시 버튼은 계속 10/08 전용 예시를 표시하며 현재 주차 기사로 표시하지 않는다.

CLI 기사 생성도 `python -B -m news.generation --week-end YYYY-MM-DD --mode template`으로 연결된다.
기존 `python news/generation.py` 호출도 유지한다. OpenAI 모드는 반드시 `--confirm-paid`가 필요하다.
웹의 유료 버튼도 기존 확인 절차를 유지한다. 개발·검증 과정에서는 실제 유료 API를 호출하지 않는다.
새 기사 파일명에는 근거 주차를 포함하며 초안·최종 출고 승인 상태를 분리한다. 자동 발행하지 않는다.

## 보존 및 검증

기존 CSV·Fact Sheet·기사·승인 JSON·.env·운영 DB는 수정하지 않는다.
새 런타임 Fact Sheet와 사람 검수 기록은 Git에서 제외되므로 별도 보관해야 한다.
출처 확인은 STEP 21 Manifest의 진술을 계승하며 새로운 외부 수집이나 이용 허가를 만들어내지 않는다.
실제 새 공식 주차 CSV가 없어 운영 신규 주차 검증은 BLOCKED다. 테스트는 격리 합성 데이터만 사용한다.

`python -B scripts/run_checks.py`는 기존 오프라인 실행기다. 실제 DB 시험은 SKIP이며 DB/API 호출을 차단한다.
`tests/test_weekly_facts.py`는 신규 초안·검수·원본 변경·주차 오염·미검수 제외·Preview·유료 모의 호출·덮어쓰기 차단을 검증한다.

다음 단계: STEP 23 — 회원가입·로그인 및 역할별 권한 관리. 데이터 등록, Fact Sheet 검수, 유료 생성, 최종 출고 권한을 분리한다.
