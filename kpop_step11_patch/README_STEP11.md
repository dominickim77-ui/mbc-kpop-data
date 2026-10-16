# K-POP DATA LAB — STEP 11 설치 안내

이 패치는 **현재 VS Code 프로젝트 `C:\WORKSPACE\mbc-kpop-data`** 위에 적용합니다. 새 프로젝트가 아닙니다.

## 적용 내용

- 뉴스 패널 위치는 `Accumulated Analysis` 아래 그대로 유지
- `Current Analysis`의 현재 선택곡을 서버에서 읽어서 기사 작성에 반영
- 사람 검수가 승인된 곡만 Fact Sheet에서 추출 (현 시점 **KATSEYE Animal**, **LISA SaWaDiKa**)
- 미검수 곡은 사유를 표시하고 기사 근거에서 제외; **Hootie Frutti**는 버전 문제로 제외
- 무료 사전 점검 버튼, 유료 AI 생성 버튼, 기존 저장 기사 예시 버튼 구분
- `Compare`의 의미 없는 숫자 차이·비율 표시 제거
- `Accumulated Analysis`는 서로 다른 단위의 데이터에 **각각 독립적인 그래프** 사용
- AI 초안은 저장만 하고 **게시하지 않음**

## 설치 방법 (Windows PowerShell)

1. 돌아가고 있는 `uvicorn` 터미널에서 `Ctrl + C`로 서버를 종료합니다.
2. ZIP 압축을 해제한 **`kpop_step11_patch` 폴더를 `mbc-kpop-data` 폴더 안에 복사**합니다.
3. VS Code 터미널의 현재 폴더가 `C:\WORKSPACE\mbc-kpop-data`인지 확인합니다.
4. 아래 한 줄을 실행합니다.

```powershell
python kpop_step11_patch\install_step11.py
```

설치기는 변경 전의 5개 파일을 `mbc-kpop-data_step11_backup_날짜_시간` 형식의 **프로젝트 외부 폴더**에 백업합니다. `app.py`, 원본 차트 CSV, 기존 기사, `.env`는 변경하지 않습니다. 예상과 다른 HTML 구조를 발견하면 안전하게 중단합니다.

## 무료 자체 점검

```powershell
python kpop_step11_patch\verify_step11.py
```

이 검사는 OpenAI/YouTube API 요청 및 MySQL 접속 없이 기본 소스/구조를 점검합니다.

## 서버 실행

```powershell
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

브라우저에서 `http://127.0.0.1:8000/`을 열고 `Ctrl+F5` 새로고침합니다. 페이지 아래 `NEWS ANALYSIS`에서 다음을 확인합니다.

- 선택된 곡 수 / 검수 완료 곡 / 보류 곡 목록
- **선택한 곡 기사 미리보기 (무료)**부터 실행
- 유료 생성은 필요한 경우에만 본인 확인 후 1회 실행
- **기존 2곡 수정 기사 예시**는 현재 선택과 무관하게 보여주는 옛 파일입니다.

## 범위 및 주의

현 버전은 처음 검수 완료한 두 곡에 대해 선택 연동을 구현합니다. 현재 선택에 다른 곡이 들어 있으면 자동 생성에 포함되지 않습니다. 다른 곡을 포함하려면 그 곡의 공식 같은 주차 차트 데이터와 곡 식별에 대한 인간 검수가 먼저 필요합니다.

기존 MySQL SQL에서 수행되는 과거 비율 계산 자체는 이번 패치로 삭제하지 않습니다. **메인·별도 Compare 화면에서 잘못된 차이·배율을 더 이상 표시하지 않도록 변경**했습니다. 추후 해당 SQL 계산을 제거하고 본 데이터 구조를 최신 주간 차트 기반으로 확장하는 것이 다음 과제입니다.

## 오류가 나면

유료 버튼을 반복하지 말고 VS Code 터미널에 표시된 오류만 공유합니다. `.env` 키나 비밀번호는 공유하지 않습니다.
