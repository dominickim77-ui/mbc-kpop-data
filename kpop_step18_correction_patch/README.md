# STEP 18 보완 — 승인 정정 이력 (ACTIVE / INVALIDATED)

- 기존 KATSEYE Animal 영상 승인 기록 3개와 MySQL 행은 **절대 삭제·수정하지 않는다**.
- 가장 최근 승인 기록을 무조건 선택하는 대신, append-only 정정 JSON을 우선한다.
- 승인 잠금, 화면 표시, 영상 검수 상태는 `latest_approved` 하나를 기준으로 판단한다.
- 정정 JSON은 수정하려는 과거 승인 파일의 SHA-256 해시를 포함한다. 이력이 바뀌거나 서로 충돌하면 오류로 중단한다.
- 정정 명령 실행은 명시적으로 `--confirm`을 붙일 때만 `facts/youtube_video_corrections` 아래에 새 JSON 파일 한 개를 만든다.
- 정정 명령은 **읽기 전용 MySQL 조회**로 기존 공식 영상 행의 Video ID와 채널을 검사한다. MySQL INSERT/UPDATE/DELETE 없음.
- YouTube 주간 차트의 조회수와 단일 MV의 누적 조회수는 분리한다.

프로젝트 루트에서 서버 종료 후:

```powershell
python kpop_step18_correction_patch\install_correction.py --dry-run
python kpop_step18_correction_patch\install_correction.py
python kpop_step18_correction_patch\verify_correction.py
```

사전 확인(쓰기 없음):

```powershell
python kpop_step18_correction_patch\correct_active.py --song-id 5 --video-id m7k9UMcHbr0 --expected-current SyLtYUk9Ogg --expected-channel "HYBE LABELS" --invalidate SyLtYUk9Ogg --invalidate j84h0XW8rMs --reason "비공식 가사 영상 두 건을 무효화하고 검수한 HYBE LABELS 공식 MV로 복원"
```

사전 확인 결과가 맞고 사람이 명시적으로 동의하면, 위 명령 **끝에** `--confirm` 추가. 정정이 생성되면 다시 실행하지 말 것.

검증:

```powershell
python -c "from app import get_dashboard_data; rows=[r for r in get_dashboard_data() if r['artist']=='KATSEYE' and r['track']=='Animal']; print([(r['youtube_video_id'],r['youtube_channel'],r.get('youtube_review_status')) for r in rows])"
```

기대값: `('m7k9UMcHbr0', 'HYBE LABELS', 'MANUALLY_APPROVED')`.

**주의:** 이 도구는 공식 채널 여부를 인터넷에서 자동 검증하지 않고, 사용자가 검수한 기존 승인·정정 사실을 관리하는 로컬 교육용 도구다. 오류 발생 시 강제로 `git reset`, JSON 삭제, 날짜 조작, 중복 승인을 하지 말 것.
