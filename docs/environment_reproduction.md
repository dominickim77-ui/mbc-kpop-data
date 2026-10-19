# Windows 실행 환경 재현

검증 기준은 Windows 11 AMD64 / CPython **3.14.7**이다. 다른 Python/OS와 MariaDB의
호환성까지 검증한 것은 아니다. 기존 DB 스키마는 MySQL 8.0.34 기준이다.
`.python-version`은 기준 기록이며 Windows의 `py`가 이 파일을 자동 적용한다고 가정하지 않는다.

## 의존성 파일

- `requirements.txt`: 애플리케이션이 직접 사용하는 런타임 패키지의 고정 버전.
- `requirements-dev.txt`: 런타임과 현재 TestClient 구현의 `httpx2` 고정 버전.
- `constraints-win-py314.txt`: 격리 환경 A에 실제 설치된 필요한 34개 패키지의 전이 의존성 고정 목록.

전역 `pip freeze`를 저장한 파일이 아니다. 현재 OpenAI/Starlette는 `httpx2`를 사용하며,
누락된 `httpx`를 임의로 추가하거나 프레임워크를 업그레이드하지 않았다.
constraints는 버전 고정이며 아티팩트 해시를 강제하는 requirements 형식은 아니다.
패키지 변경은 별도 깨끗한 환경에서 설치·검증한 뒤 명세와 문서를 함께 갱신한다.

## 새 환경 생성과 설치

전역 Python과 기존 `.venv`를 덮어쓰지 않는다. 아래 경로가 이미 있으면 새 이름을 고른다.
먼저 `py -3.14 --version`이 기준 Python인지 확인한다. 패키지 설치에는 네트워크가 필요하다.

```powershell
py -3.14 --version
py -3.14 -m venv .venv-new
.\.venv-new\Scripts\python.exe -m pip --require-virtualenv install -r requirements-dev.txt -c constraints-win-py314.txt
.\.venv-new\Scripts\python.exe -m pip check
.\.venv-new\Scripts\python.exe -B scripts/run_checks.py
```

`--system-site-packages`, `--clear`, 전역 pip 설치/업데이트를 사용하지 않는다.
PowerShell 실행 정책을 변경하거나 환경을 활성화할 필요 없이 명시적 python.exe 경로로 실행한다.
한 환경이 통과한 뒤 같은 명세로 두 번째 새 환경을 만들고 동일하게 검증한다.

## 설정·서버 실행

오프라인 검증에 실제 API 키나 DB 비밀번호가 필요하지 않다. `.env`를 새 환경에 복사하지 않는다.
서버 실행이 필요할 때에만 `.env.example`의 변수 이름을 참고해 자기 로컬 `.env`를 준비한다.
실제 `.env`와 기존 값은 이 작업에서 수정하지 않았다.

```powershell
.\.venv-new\Scripts\python.exe scripts/run_local.py
```

이 명령을 명시적으로 실행할 때만 Uvicorn이 시작된다. 기본 주소는 기존 출처 보호와 같은
`http://127.0.0.1:8000`이다. 실행 도구는 현재 인터프리터와 프로젝트 루트를 사용한다.
기존 `python -m uvicorn app:app --reload`도 프로젝트 루트에서 사용할 수 있다.
static/templates와 `.env`는 app.py 위치를 기준으로 찾으며 환경변수 우선순위를 유지한다.

## 데이터는 스키마/환경과 구분

Python 환경 설치만으로 로컬 MySQL이나 승인 기록이 재현되는 것은 아니다.
기존 데이터 복원은 PK를 보존한 DB 백업과 facts/의 승인·정정 기록을 함께 대조해야 한다.
이 문서의 설치/오프라인 검증 명령은 운영 DB에 쓰거나 기존 CSV·기사·Fact Sheet를 재생성하지 않는다.

## 한계와 복구

새 환경의 패키지·코드 회귀 검증은 실제 유료 API 호출·브라우저 클릭 검증과 구분한다.
실행 중 서버/VS Code의 인터프리터를 자동으로 전환하지 않는다.
문제가 있으면 해당 코드·명세 변경만 복원하고 새 환경을 사용하지 않는다.
기존 전역 환경·데이터·승인·정정을 초기화하지 않는다.

참고: [Python venv](https://docs.python.org/3.14/library/venv.html),
[pip 재현 가능한 설치](https://pip.pypa.io/en/stable/topics/repeatable-installs/)
