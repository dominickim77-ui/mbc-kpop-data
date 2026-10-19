# DB 스키마 재현 및 안전한 보완

실측 기준은 MySQL 8.0.34, InnoDB, `utf8mb4` / `utf8mb4_0900_ai_ci`이다.
`db/schema_manifest.json`은 구조 비교 기준이며 데이터·비밀값을 포함하지 않는다.
MariaDB 및 다른 MySQL 버전에서의 호환성을 검증했다고 가정하지 않는다.

## 실행 환경

프로젝트 루트에서 기존 Python 환경의 `mysql-connector-python`, `python-dotenv`를 사용한다.
접속 정보는 기존 `.env`에서 읽으며 값을 출력하지 않는다. 다른 설정 파일은
`--env-file`로 지정한다. 운영 `.env`의 `MYSQL_DATABASE`를 테스트 DB 이름으로 바꾸지 않는다.
명령에는 대상 DB를 반드시 명시한다. 명시한 DB가 자동 생성되는 도구는 아니다.

```powershell
$env:PYTHONUTF8 = '1'
python -B scripts/check_db_schema.py --database mbc_kpop_data
python -B scripts/migrate_db_schema.py --database mbc_kpop_data
```

두 명령은 읽기 전용이다. 첫 명령은 차이를 보고하며, 둘째는 보완 계획만 출력한다.
현재 운영 DB의 기대 결과는 `compatible: true`, `statements: []`이다.
비교 도구의 종료 코드는 정상 0, 구조·데이터 불일치 1, 접속·조회 오류 2다.
보완 도구는 안전하게 계획 가능한 누락을 출력한 경우에도 0을 반환하고,
자동 처리할 수 없는 차이는 1, 접속·실행 오류는 2를 반환한다.
접속 계정이 구조를 조회할 권한이 있어야 하며, 제한된 권한 때문에 보이지 않는
객체가 있다는 사실까지 도구가 보증하지는 않는다.

## 신규 빈 DB 구축

`mbc_kpop_data.sql`에는 3개 `CREATE TABLE`만 있다. `USE`, DB 생성, 데이터 삽입,
테이블 삭제, `IF NOT EXISTS`는 넣지 않았다. 선택한 빈 DB에만 실행한다.
기존 테이블이 있으면 중단해야 하며 클라이언트의 오류 무시 옵션을 사용하지 않는다.
MySQL 클라이언트가 설치된 환경의 예시는 다음과 같다.

```text
mysql --database=명시적으로_만든_빈_테스트_DB < mbc_kpop_data.sql
```

이번 자동 검증은 MySQL CLI 대신 Python connector를 사용했다. 테스트는
`mbc_kpop_step19_test_`로 시작하는 무작위 새 DB를 만들며, 기존 DB는 재사용하지 않는다.

스키마만 구축하면 기존 데이터와 승인 JSON의 관계까지 복구되는 것은 아니다.
실제 데이터 복원이 필요하면 PK 값을 보존하는 DB 백업과 `facts/`의 승인·정정 이력을
함께 복원·대조해야 한다. CSV 재적재로 `song_id`를 새로 부여하면 안 된다.
기존 AUTO_INCREMENT 카운터와 시간값을 리셋·재해석하지 않는다.

## 구형 스키마 보완

`db/migrations/001_weekly_unique_indexes.sql`은 가드가 있는 도구가 사용하는 두 DDL의 원문이다.
직접 source하지 않는다. 도구는 아래 조건을 먼저 확인한 뒤 필요한 문장만 실행한다.

- 컬럼·엔진·문자셋·정렬 규칙·FK 관계가 기준과 맞아야 한다.
- 중복 그룹과 고아 행이 없어야 한다. 삭제·병합으로 해결하지 않는다.
- 같은 의미의 UNIQUE가 이미 있으면 이름이 달라도 추가하지 않는다.
- 같은 이름이 다른 정의로 존재하거나 접두사 인덱스이면 중단한다.
- Spotify에 남은 일반 `song_id` FK 지원 인덱스는 보존하고 경고만 표시한다.
- 두 인덱스 전체 계획을 사전 검증한다. 일부만 보완된 DB에서는 남은 인덱스만 추가한다.

적용 모드는 이 작업에서 허가된 별도 테스트 DB로만 제한된다.

```powershell
python -B scripts/migrate_db_schema.py --database mbc_kpop_step19_test_example
python -B scripts/migrate_db_schema.py --database mbc_kpop_step19_test_example --apply
```

첫 명령은 읽기 전용 계획이다. 실제 대상에는 소문자 영문·숫자·밑줄만 사용한다.
`--apply`는 `mbc_kpop_step19_test_*` 이름만 허용하고, `.env`의 운영 DB와 같으면
접속 전에 거부한다. 연결 후 선택된 DB도 다시 대조한다. 운영 DB에 적용하는 경로는 없다.
격리된 테스트 DB에는 다른 작성자가 접속하지 않아야 한다. 이 도구는 동시 작성 중인
DB의 메타데이터·데이터 변경을 잠가 주는 온라인 migration 도구가 아니다.

MySQL DDL은 암묵적 커밋을 수반한다. 한 ALTER가 성공한 뒤 다음 ALTER가 실패하면
앞의 변경이 남을 수 있다. 일반 ROLLBACK으로 DDL 전체를 되돌릴 수 있다고 생각하면 안 된다.
그 경우 구조를 다시 읽고 남은 계획을 확인한다. 데이터 삭제나 인덱스 자동 제거는 하지 않는다.
운영 DDL이 향후 필요해지면 별도의 승인·백업·복원 시험·잠금 영향 검토가 필요하다.
[MySQL 8.0 DDL 커밋 문서](https://dev.mysql.com/doc/refman/8.0/en/implicit-commit.html)

## 비교 기준

컬럼의 순서·타입·부호·길이·NULL·기본값·자동증가·생성식을 비교한다.
인덱스는 컬럼 순서·UNIQUE 여부·접두사 길이·방향·가시성·식을 비교한다.
FK는 참조 테이블·컬럼과 UPDATE/DELETE 정책을 비교한다. 다른 DB로의 FK는 거부한다.
새로운 트리거·루틴·지원하지 않는 제약도 자동 보완 대상이 아니다.
현재 행 수와 AUTO_INCREMENT 진행값, 동등한 인덱스·FK의 이름 차이는
구조 불일치와 구분한다. `tracks(artist, track)` UNIQUE는 추가하지 않는다.

## 테스트

기본 실행은 순수 정책 검사만 실행하고 실제 DB 통합 검증은 건너뛴다.

```powershell
python -B -m unittest discover -s tests -p test_db_schema_reproduction.py -v
```

실제 DB 통합 검증은 명시적으로 켠다. DB 생성·삭제 권한이 있는 테스트용 계정이 필요하다.
새 DB 이름은 테스트마다 생성하며 테스트가 만든 정확한 DB만 정리한다.
운영 데이터는 fixture로 복사하지 않는다.

```powershell
$env:STEP19_RUN_DB_TESTS = '1'
python -B -m unittest discover -s tests -p test_db_schema_reproduction.py -v
Remove-Item Env:STEP19_RUN_DB_TESTS
```

다른 자격 파일은 `STEP19_DB_ENV_FILE`에 경로를 지정한다.
테스트는 신규 구축, 반복 구축 거부, 구형 DB 보완·재실행, ID·행 보존,
중복·고아 행·컬럼 차이·잘못된 인덱스 정의 차단을 검사한다.
시간값이나 실제 승인·정정 파일은 변경하지 않는다.

기존 회귀 검증:

```powershell
python -B -m unittest discover -s tests -p test_step19_p1.py -v
python -B kpop_step17b_patch/verify_step17b.py
python -B -m kpop_step18_patch.verify_step18
python -B kpop_step18_correction_patch/verify_correction.py
```

## 복구

이번 변경은 저장소의 구조 명세·도구·테스트·문서이며 운영 DB에는 적용하지 않는다.
코드·SQL의 복구는 해당 파일 백업 또는 commit 단위로 한다. 운영 데이터를 초기화하지 않는다.
테스트용 신규 DB는 테스트가 생성한 이름을 확인한 뒤 정리한다. 운영 DB 이름을
계산된 삭제 명령에 전달하지 않는다.
