/* STEP17B · human-confirmed YouTube video IDs. No automatic approval. */
(() => {
  'use strict';
  const root = document.getElementById('youtube-review-step17b');
  if (!root) return;
  const select = document.getElementById('yt17-song');
  const search = document.getElementById('yt17-search');
  const box = document.getElementById('yt17-candidates');
  const status = document.getElementById('yt17-status');
  const weekEnd = root.dataset.weekEnd || '';
  let session = null;
  let busy = false;

  if (!['EDITOR', 'ADMIN'].includes(root.dataset.userRole)) {
    search.disabled = true;
    status.textContent = '영상 후보 검색과 검수는 EDITOR·ADMIN 권한이 필요합니다. 관리자에게 역할 부여를 요청해 주세요.';
    return;
  }

  async function json(url, options = {}) {
    const {headers: extraHeaders, ...rest} = options;
    const res = await fetch(url, {cache:'no-store', ...rest, headers:{'X-Requested-With':'KpopYouTubeReview', ...(extraHeaders || {})}});
    let body;
    try { body = await res.json(); } catch { throw new Error('서버 응답을 해석할 수 없습니다.'); }
    if (!res.ok) {
      const error = new Error(typeof body.detail === 'string' ? body.detail : '입력 내용을 확인해 주세요.');
      error.status = res.status;
      throw error;
    }
    return body;
  }
  function textElement(tag, content, className='') {
    const node = document.createElement(tag);
    node.textContent = content;
    if (className) node.className = className;
    return node;
  }
  function checkbox(id, msg) {
    const label = document.createElement('label'); label.className = 'yt17-check';
    const input = document.createElement('input'); input.type = 'checkbox'; input.id = id;
    label.append(input, document.createTextNode(msg));
    return label;
  }
  function show(data) {
    box.replaceChildren(); session = data;
    box.append(textElement('p', `${data.artist} — ${data.track} | 영상 후보 ${data.candidates.length}개 | 자동 승인 없음`));
    if (data.approval_locked) box.append(textElement('p', `🔒 이미 승인된 Video ID: ${data.approved_video_id}. 다른 영상을 승인하려면 정정 절차가 필요합니다.`, 'yt17-warning'));
    box.append(textElement('p', '아래의 누적 조회수는 개별 영상의 현재 누적 수치이며 YouTube 주간 곡 차트 조회수가 아닙니다.', 'yt17-warning'));
    const choices = document.createElement('div'); choices.className = 'yt17-choices';
    for (const [idx, entry] of data.candidates.entries()) {
      const label = document.createElement('label'); label.className = 'yt17-candidate';
      const input = document.createElement('input'); input.type = 'radio'; input.name = 'yt17-video'; input.value = entry.video_id;
      if (idx === 0) input.checked = true;
      const details = document.createElement('div');
      details.append(textElement('strong', `${entry.title} — ${entry.channel_title}`));
      details.append(textElement('small', `채널 ID: ${entry.channel_id} · 누적 조회수: ${Number(entry.cumulative_views).toLocaleString('ko-KR')} · ${entry.source === 'WEEKLY_CHART_REFERENCE' ? '주간 차트 참고 영상' : '검색 후보'}`));
      details.append(textElement('small', `검토 힌트: ${entry.review_hint} (공식 채널 자동 인증 아님)`));
      const a = document.createElement('a');
      a.href = `https://www.youtube.com/watch?v=${entry.video_id}`;
      a.target = '_blank'; a.rel = 'noopener noreferrer'; a.textContent = 'YouTube에서 직접 확인 ↗';
      details.append(a); label.append(input, details); choices.append(label);
    }
    box.append(choices);
    const checks = document.createElement('div'); checks.className = 'yt17-checks';
    checks.append(
      checkbox('yt17-channel-ok', '채널 페이지를 열어 공식 채널임을 직접 확인했습니다.'),
      checkbox('yt17-version-ok', '영상의 곡명·아티스트·원곡/리믹스 등 버전을 직접 확인했습니다.'),
      checkbox('yt17-metric-ok', '저장되는 조회수는 이 영상 하나의 누적 조회수임을 이해했습니다.')
    );
    box.append(checks);
    const approve = document.createElement('button'); approve.type = 'button'; approve.textContent = '✅ 확인한 Video ID 승인·저장';
    approve.className = 'yt17-approve';
    approve.disabled = Boolean(data.approval_locked);
    approve.addEventListener('click', async () => {
      if (busy) return;
      const checked = box.querySelector('input[name="yt17-video"]:checked');
      const channel = document.getElementById('yt17-channel-ok').checked;
      const version = document.getElementById('yt17-version-ok').checked;
      const metric = document.getElementById('yt17-metric-ok').checked;
      if (!checked || !channel || !version || !metric) {
        status.textContent = '먼저 영상을 열어 확인하고 세 항목에 체크해 주세요.'; return;
      }
      const video = data.candidates.find(x => x.video_id === checked.value);
      if (!video) return;
      if (!window.confirm(`직접 확인한 다음 영상을 ${data.artist} — ${data.track}에 연결할까요?\n\n${video.title}\n채널: ${video.channel_title}\nVideo ID: ${video.video_id}\n\n기존 이력은 삭제되지 않습니다.`)) return;
      busy = true; search.disabled = true; approve.disabled = true;
      status.textContent = '승인 영상의 최신 통계 확인 및 기록 중…';
      try {
        const result = await json('/api/youtube-video-review/approve', {
          method:'POST',
          headers:{'Content-Type':'application/json'},
          body:JSON.stringify({song_id:data.song_id,video_id:video.video_id,review_token:data.review_token,
            verified_channel:channel,verified_track_version:version,understood_lifetime_metric:metric})
        });
        status.textContent = `검수 기록 저장됨: ${result.video_id}. 새로고침 후 YouTube Data 확인해 주세요. 기사 출고는 별도 승인이 필요합니다.`;
        box.append(textElement('p', `검수 이력: ${result.source}`, 'yt17-success'));
        session = null;
      } catch (err) { status.textContent = `승인 실패: ${err.message}. API·DB 기록을 확인하기 전 다시 승인하지 마세요.`; }
      finally {busy=false; search.disabled=false; approve.disabled=false;}
    });
    box.append(approve); box.hidden = false;
  }
  search.addEventListener('click', async () => {
    if (busy || !select.value) return;
    busy = true; search.disabled = true;
    session = null; box.hidden = true; box.replaceChildren();
    status.textContent = 'YouTube 공식 영상 후보 검색 중 (API 할당량 사용)…';
    try {
      const url = `/api/youtube-video-review/candidates?song_id=${encodeURIComponent(select.value)}&week_end=${encodeURIComponent(weekEnd)}`;
      const data = await json(url);
      show(data);
      status.textContent = data.cached ? '10분 이내 검색 결과이며, 추가 API 사용은 없습니다.' : '후보를 불러왔습니다. 공식 채널과 곡 버전을 확인해 주세요.';
    } catch (err) {
      const labels = {401:'로그인 필요',403:'접근 권한 확인',404:'검색 결과 없음',429:'API 할당량 초과',502:'YouTube 연결·설정 오류',503:'YouTube 설정 필요'};
      status.textContent = `${labels[err.status] || '후보 조회 실패'}: ${err.message}`;
      if (err.status === 401 || err.status === 403) root.dataset.accessRevoked = 'true';
    }
    finally {busy=false; search.disabled=root.dataset.accessRevoked === 'true' || !select.value;}
  });
})();
