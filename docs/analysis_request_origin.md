# 분석 변경 요청의 출처 검증

`POST /add-analysis`, `POST /remove-analysis/{song_id}`, `POST /reset-analysis`는
`security.analysis_origin.require_local_analysis_origin` 의존성으로 보호한다.
검증 실패는 DB 접근·업무 함수 실행·분석 목록 변경 전에 403으로 종료한다.
프레임워크의 폼 구문 분석/입력 형식 오류는 별도로 400/422가 될 수 있다.

## 정상 사용

기존 HTML 폼을 그대로 제출한다. JavaScript fetch, 사용자 설정 헤더,
쿠키/세션/토큰 저장소를 추가하지 않는다. 정상 요청은 기존 303 이동과
검색어·주차 선택을 유지한다. P1의 commit 후 선택 반영과 요청 잠금도 유지한다.

기본 허용 주소는 문서화된 직접 접속 개발 서버의 두 출처다.

- `http://127.0.0.1:8000`
- `http://localhost:8000`

두 호스트는 서로 다른 출처다. 현재 페이지의 상대경로 폼은 같은 출처로 제출된다.
다른 포트·HTTPS·IPv6·프록시 배포를 자동 허용하지 않는다. 필요하면 서버 허용 목록과
관련 테스트를 명시적으로 검토한다. DB/API `.env` 설정은 이 검증에 맞추기 위해 변경하지 않는다.

## 검증 순서

1. 요청 대상 Host와 서버의 scheme을 파싱해 명시적 허용 목록과 대조한다.
2. 중복된 Host/Origin/Referer/Sec-Fetch-Site와 모호한 URL 형식을 거부한다.
3. Sec-Fetch-Site가 있으면 `same-origin`, `same-site`, `none`만 허용 후보로 둔다.
   `cross-site`는 거부한다. 이 헤더만으로 출처를 인정하지 않는다.
4. Origin이 있으면 scheme·호스트·유효 포트가 대상과 같아야 한다.
5. Origin이 아예 없을 때만 Referer URL의 출처를 대조한다.
6. 출처를 확인할 수 없거나 일치하지 않으면 403이다.

`Origin: null`, 빈 Origin, 잘못된 Origin이 있으면 좋은 Referer를 덧붙여도 통과하지 않는다.
둘 다 없는 요청도 거부한다. 커스텀 클라이언트는 이 정책을 충족해야 한다.
호스트 대소문자와 유효 포트는 정규화하며 부분 문자열 비교는 하지 않는다.
Origin의 path/query/fragment·사용자정보·잘못된 포트·제어문자 등은 거부한다.
Referer의 정상 경로/쿼리는 허용하되, 전체 URL을 오류 메시지에 반영하지 않는다.
전달된 X-Forwarded-Host/Proto로 허용 목록을 바꾸지 않는다.

## 영향 범위

검색·주차 선택·읽기 페이지에는 이 의존성을 연결하지 않는다.
기사 생성·YouTube 승인·정정 로직은 기존 정책을 유지한다.
직접 Python 함수를 호출하는 기존 P1 단위 테스트는 HTTP 의존성 검증을 실행하지 않으므로,
새 ASGI 테스트에서 실제 HTTP 라우트 보호를 별도로 검증한다.

이 보호는 브라우저의 외부 사이트 요청을 거부하기 위한 것이다. 사용자 인증 기능이 아니다.
로컬 프로그램은 헤더를 구성할 수 있으며, 인터넷 공개·다중 사용자·프록시 환경의
인증/권한 문제까지 해결한 것으로 취급하지 않는다. Origin과 Referer를 모두 제거하는
환경을 무조건 허용하는 예외는 두지 않는다.

## 검증 명령

프로젝트 루트에서 실행한다. 테스트는 실제 DB/API 호출을 차단하고 모의 DB만 사용한다.

```powershell
$env:PYTHONUTF8='1'
python -B -m unittest discover -s tests -p test_analysis_origin.py -v
python -B -m unittest discover -s tests -p test_step19_p1.py -v
python -B kpop_step17b_patch/verify_step17b.py
python -B -m kpop_step18_patch.verify_step18
python -B kpop_step18_correction_patch/verify_correction.py
```

일반 폼과 같은 URL 인코딩 본문을 사용한 ASGI 검증은 실제 브라우저 클릭 검증과 구분한다.
실행 중 서버 프로세스의 Current Analysis나 운영 DB에 시험 데이터를 저장하지 않는다.

문제가 있으면 해당 코드 변경만 되돌린다. 데이터·승인·정정·.env를 초기화하지 않는다.

설계 참고: [OWASP 출처 검증](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html#using-standard-headers-to-verify-origin)
