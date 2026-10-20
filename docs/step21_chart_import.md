# STEP 21 1차 — 주간 CSV 가져오기

기준: `916233682e9de0432b96413b030f568935102111`.
현재 구현은 격리 사본에서 검증하며 운영 설치·Commit·Push는 별도 승인 대상이다.
공식 다운로드 가능 여부와 실제 새 주차 파일의 이용 권한은 미확인이다.
샘플 JSON의 확인 상태를 실제 근거 없이 true로 바꾸지 않는다.

## 목표와 경계

사용자가 제공한 공식 출처 확인 CSV 2개를 원본 그대로 보관하고, 검증 완료 주차만
기존 FastAPI Dashboard의 주차 목록에 등록한다. 웹 업로드·네트워크 다운로드·스케줄러·
DB 쓰기·유료 API·새 Fact Sheet·기사 생성은 추가하지 않는다.
새 주차의 곡을 선택하는 기존 `/add-analysis`는 여전히 DB 쓰기 기능이다.
CSV 등록 명령은 이 경로를 호출하지 않는다. 운영 화면에서 해당 버튼을 시험하지 않는다.

## 왜 등록 목록인가?

파일명만 바꿔 폴더에 넣으면 주차가 노출되던 방식 대신 등록 기록(Manifest)을 읽는다.
기존 10/01·10/08 원본은 `data/chart_registry/baseline.json`에 기준 커밋의 SHA-256으로 고정했다.
이는 기존 승인 범위를 보존하는 호환 목록이며 현재 다운로드 권한을 새로 인증한 기록이 아니다.
기존 파일 지문이 다르면 해당 주차를 제외한다. 기준 목록이 없으면 임의 폴더 탐색으로 우회하지 않는다.
Windows 작업 폴더와 Git 원본의 줄바꿈(CRLF/LF)이 다른 기존 YouTube CSV는 내용이 같은지
읽기 전용으로 대조한 뒤 두 개의 정확한 지문을 기록했다. 원본을 정규화해서 덮어쓰지 않는다.

새 주차는 `data/chart_registry/weeks/YYYY-MM-DD.json` 하나로 두 플랫폼을 함께 공개한다.
정상 파일을 준비하고 마지막에 같은 파일시스템에서 원자적으로 이름을 바꾼다(Atomic rename).
이전에 등록된 주차 기록은 덮어쓰지 않는다. 등록 전 실패하면 기존 정상 목록은 유지된다.
파일시스템 전체 장애·전원 손실의 내구성까지 보장하는 분산 트랜잭션은 아니다.

## 출처 기록 준비

`docs/step21_provenance.example.json`을 별도 입력 폴더에 복사하고 실제 확인 내용을 채운다.
원본 CSV의 행·열·인코딩·파일명을 고칠 필요는 없다. 파일명 대신 확인한 메타데이터로 기간을 지정한다.

- `source_url`: 실제 해당 주차 공식 차트 HTTPS 주소. 쿼리·인증 토큰·쿠키를 넣지 않는다.
- `sha256`: 해당 파일의 SHA-256. 이것은 파일의 동일성을 확인하며 공식 출처 자체를 증명하지 않는다.
- `week_start`, `week_end`, `timezone`, `period_basis`: 공식 화면/내보내기 자료의 집계 기간과 근거.
- `source_evidence`, `reviewer`, `source_confirmed`, `period_confirmed`: 누가 무엇을 확인했는지 기록.
- `downloaded_at`: 주차 종료 후 실제 다운로드 시각과 시간대.
- `usage_status`: 로컬 분석 이용 근거를 확인했을 때만 `confirmed_local_analysis`.
- `usage_evidence`: 그 판단의 근거. 미확인은 `unknown`으로 두고 등록을 보류한다.

Spotify는 UTC를 확인한다. YouTube 시간대는 공식 근거대로 기록하며 자동 추정하지 않는다.
JSON은 사람의 확인 진술이다. 프로그램이 외부 사이트나 이용 권한을 독립적으로 인증하지 않는다.
원본 재배포·외부 AI 입력·기사 공개 권한은 이 확인 범위에 포함하지 않는다.

PowerShell에서 지문을 읽는 예:

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath 'C:\input\spotify.csv'
Get-FileHash -Algorithm SHA256 -LiteralPath 'C:\input\youtube.csv'
```

지문은 소문자 64자리로 기록한다.

## 실행

검토한 격리 프로젝트 루트에서 해당 가상환경의 Python을 사용한다.

```powershell
python -B -m news.chart_import --spotify C:\input\spotify.csv --youtube C:\input\youtube.csv --provenance C:\input\source.json --week-end 2026-10-15
```

기본은 미리 점검(Dry Run)이며 파일을 전혀 쓰지 않는다. 출력의 `PASS`, `comparable`,
`planned_files`, 경고를 검토한다. 확인한 로컬 프로젝트에 등록할 때만 같은 명령에 `--apply`를 붙인다.
이 명령은 운영 DB 쓰기를 승인하거나 실행하는 명령이 아니다.

`--apply`는 읽어들인 두 파일과 출처 기록을 실행별 Staging에 보존한다. 내용 검증에 실패해도
보관된 Staging과 failure.json을 유지한다. 파일 자체를 읽지 못하거나 출처 JSON을 해석하지 못하면
출력에 오류를 반환하며 Staging이 생성되지 않을 수 있다. 필요하면 출력을 별도 로그로 저장한다.

## 검사와 상태

필수/중복 헤더, 행의 열 개수, UTF-8, Top 200/100 전체 순위, 중복 순위, 빈 곡명·아티스트,
정수·음수, 동일 곡명/아티스트 행, 존재하는 곡 식별자 중복을 검사한다.
정규화 후 모호한 곡은 경고하고 기존 화면의 후보·보류 처리를 유지한다. 수치 내림차순 이상은 보류한다.
기간·Global·weekly_top_songs·지표·출처 확인·지문·이용 근거도 검사한다.
다른 등록 주차와 동일한 원본 재사용은 기간 오표기 가능성이 있어 보류한다.

| 상태 | 의미 |
| --- | --- |
| PASS / dry_run | 검사 통과, 등록하지 않음 |
| PASS / registered | 마지막 주차 manifest 공개 완료 |
| SKIP / duplicate | 같은 주차·같은 원본. 기존 기록 유지 |
| BLOCKED | 출처/이용 근거 미확인, 주차 충돌, 잠금 등 해결 필요 |
| FAIL | CSV 형식, 파일 손상, 읽기·쓰기 실패 |

검증된 단일 주차는 등록 가능하다. Dashboard의 **비교 목록**에는 양 플랫폼이 갖춰진
연속 2주만 나온다. 이전 주가 없으면 `comparable: false`이고 0으로 채우지 않는다.
직접 data/charts에 넣은 미등록 새 파일은 목록에 나타나지 않는다.

## 보관·중단·재실행

- `data/chart_imports/staging/<실행ID>/`: 입력 사본·출처·검사/실패 기록.
- `data/chart_imports/objects/<SHA-256>.csv`: 검증한 원본 바이트. 같은 지문은 재사용하며 덮어쓰지 않는다.
- `data/chart_registry/weeks/<종료일>.json`: **등록 완료의 최종 기준**. `READY_TO_COMMIT`만으로 성공을 판단하지 않는다.
- `data/chart_registry/import.lock`: 동시 쓰기 방지. 중단된 잠금은 자동 해제하지 않는다.
- `*.pending`: 아직 공개되지 않은 기록. Dashboard는 읽지 않는다.

중단 시 오류·Staging·pending을 먼저 보존하고 마지막 manifest 존재와 원본 지문을 대조한다.
manifest가 없으면 등록되지 않은 상태이며 원인을 해결한 뒤 재실행할 수 있다.
manifest가 있고 지문이 같으면 재실행은 SKIP이다. 지문 충돌·기존 object 손상은 자동 복구하지 않는다.
잠금이 남았다면 기록된 프로세스가 종료됐는지 확인하고 해당 잠금만 검토 후 해제한다.
기존 CSV·Fact Sheet·기사·승인/정정 기록을 복구 목적으로 삭제하거나 덮어쓰지 않는다.

## 2차 연결 검토 — 미구현

등록된 주차의 파일 경로·SHA-256·출처 기록을 Fact Sheet의 입력 근거로 사용할 수 있다.
후속 단계에서는 generation.py의 고정 날짜/곡 수/곡 이름, FACT_PATH, app.py의
news_week_compatible 및 서버 뉴스 경로의 주차 검증을 함께 검토해야 한다.
원본 검증과 사람의 곡 식별·편집 승인 상태를 분리하고, 원본 지문이 바뀌면 검수를 재요구한다.
이번 구현은 이 파일들을 수정하지 않는다. 10/15 합성 주차가 Dashboard에 나와도
기존 검수 뉴스 경로는 409로 차단되며 10/08 승인이 이월되지 않는다.

## 검증

```powershell
python -B scripts/run_checks.py --report report.json
```

기본 오프라인 실행기는 실제 DB/API 진입점을 차단한다. 새 시험은 테스트 임시 폴더만 변경한다.
공식 CSV 신규 다운로드/실제 이용 권한/운영 반영은 검증했다고 주장하지 않는다.
테스트 DB 16개 SKIP을 PASS로 보고하지 않는다.
