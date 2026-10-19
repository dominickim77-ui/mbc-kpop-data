/* KPOP_WEEKLY_MANAGER_STEP13 */
/* STEP11: only server-approved CURRENT selection is used for new paid news. */
(() => {
  'use strict';
  const panel = document.getElementById('news-inline-panel');
  if (!panel) return;
  const btnPreview = document.getElementById('news-preview-btn');
  const btnPaid = document.getElementById('news-generate-btn');
  const btnSaved = document.getElementById('news-saved-btn');
  const btnReview = document.getElementById('news-review-queue-btn');
  const btnSpotifyOnly = document.getElementById('news-spotify-only-preview-btn');
  const reviewBox = document.getElementById('news-review-queue');
  const countEl = document.getElementById('news-selected-count');
  const approvedList = document.getElementById('news-approved-list');
  const excludedList = document.getElementById('news-excluded-list');
  const statusEl = document.getElementById('news-status');
  const output = document.getElementById('news-article-output');
  const sourceEl = document.getElementById('news-result-source');
  const requestedWeekEnd = panel.dataset.chartWeekEnd || '';
  const newsWeekCompatible = panel.dataset.newsWeekCompatible === 'true';
  const weekQuery = '?week_end=' + encodeURIComponent(requestedWeekEnd);
  let busy = false;
  let selection = null;

  function setBusy(flag) {
    busy = flag;
    btnPreview.disabled = flag || !newsWeekCompatible || !selection || !selection.can_generate;
    btnPaid.disabled = flag || !newsWeekCompatible || !selection || !selection.can_generate;
    btnSaved.disabled = flag;
    if (btnReview) btnReview.disabled = flag;
    if (btnSpotifyOnly) btnSpotifyOnly.disabled = flag;
  }
  function addLine(list, text) {
    const li = document.createElement('li');
    li.textContent = text;
    list.appendChild(li);
  }
  function showSelection(data) {
    selection = data;
    approvedList.replaceChildren();
    excludedList.replaceChildren();
    const all = data.selected_tracks.length;
    const approved = data.approved_tracks.length;
    countEl.textContent = `현재 선택 ${all}곡 · 교차 검수 완료 ${approved}곡 · 검수 대기 ${data.excluded_tracks.length}곡`;
    if (!approved) addLine(approvedList, '없음 — 검수된 Animal 또는 SaWaDiKa를 Current Analysis에 추가해 줘.');
    for (const row of data.approved_tracks) addLine(approvedList, `${row.artist} — ${row.track} (${row.editorial_category})`);
    if (!data.excluded_tracks.length) addLine(excludedList, '없음');
    for (const row of data.excluded_tracks) addLine(excludedList, `${row.artist} — ${row.track}: ${row.reason}`);
    setBusy(busy);
  }
  async function requestJson(url, options) {
    const res = await fetch(url, {cache:'no-store', ...options});
    let data;
    try { data = await res.json(); } catch { throw new Error('서버 응답을 읽을 수 없습니다.'); }
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    return data;
  }
  function renderArticle(text) {
    output.replaceChildren();
    for (const [idx, chunk] of String(text).trim().split(/\n\s*\n/).entries()) {
      if (!chunk.trim()) continue;
      const el = document.createElement(idx === 0 ? 'h3' : 'p');
      // Escaped by textContent: model output is NEVER treated as HTML.
      el.textContent = chunk.trim().replace(/^#{1,6}\s+/, '').replace(/\*\*/g, '');
      output.appendChild(el);
    }
    output.hidden = false;
    output.scrollIntoView({behavior:'smooth', block:'nearest'});
  }
  function displayArticle(data) {
    renderArticle(data.article);
    sourceEl.textContent = `근거/저장 위치: ${data.source || '없음'} · 최종 검수 필요 · 출고 미승인`;
    if (data.mode === 'saved_example') {
      statusEl.textContent = '기존 2곡 예시야. 현재 선택과는 관계없으며 추가 API 비용은 없어.';
    } else if (data.ai_generated_now) {
      statusEl.textContent = '현재 선택에서 검수된 곡만으로 AI 초안을 생성했어. 숫자와 출처를 직접 검수해 줘.';
    } else {
      statusEl.textContent = '현재 선택의 무료 Template이야. OpenAI를 호출하지 않았어.';
    }
  }
  async function refreshSelection() {
    const data = await requestJson('/api/news/selection' + weekQuery);
    showSelection(data);
    return data;
  }
  async function runFree(kind) {
    if (busy) return;
    setBusy(true);
    statusEl.textContent = kind === 'preview' ? '현재 선택 곡을 검증하는 중…' : '기존 예시를 읽는 중…';
    try {
      if (kind === 'preview') await refreshSelection();
      const data = await requestJson(kind === 'preview' ? '/api/news/preview' + weekQuery : '/api/news/article?variant=edited');
      displayArticle(data);
    } catch (e) { statusEl.textContent = `오류: ${e.message}`; }
    finally { setBusy(false); }
  }
  // STEP16: visually inspect a candidate Fact Sheet; NEVER approve automatically.
  function showReviewQueue(report) {
    reviewBox.replaceChildren();
    const heading = document.createElement('h3');
    heading.textContent = `검수 후보표 · ${report.comparison_period.current_end} 종료 주`;
    reviewBox.appendChild(heading);
    const note = document.createElement('p');
    note.textContent = `현재 선택 ${report.selected_count}곡 · 원본 CSV 근거 · 자동 승인/유료 호출 없음`;
    reviewBox.appendChild(note);
    if (!report.candidates.length) {
      const empty = document.createElement('p');
      empty.textContent = 'Current Analysis에 곡을 추가하면 근거를 확인할 수 있어.';
      reviewBox.appendChild(empty);
    } else {
      const wrap = document.createElement('div');
      wrap.className = 'news-review-table-scroll';
      const table = document.createElement('table');
      table.className = 'news-review-table';
      const head = document.createElement('thead');
      const trHead = document.createElement('tr');
      for (const name of ['아티스트 · 곡', 'Spotify 순위 · 주간 스트리밍 (전→금)', 'YouTube 순위 · 주간 조회수 (전→금)', '검수 상태 및 다음 단계']) {
        const th = document.createElement('th'); th.scope = 'col'; th.textContent = name;
        trHead.appendChild(th);
      }
      head.appendChild(trHead); table.appendChild(head);
      const tbody = document.createElement('tbody');
      function fmtCount(value) { return value == null ? '—' : Number(value).toLocaleString('ko-KR'); }
      function fmtRank(value) { return value == null ? '—' : `${value}위`; }
      for (const row of report.candidates) {
        const tr = document.createElement('tr');
        const title = document.createElement('td');
        const strong = document.createElement('strong');
        strong.textContent = `${row.artist} — ${row.track}`; title.appendChild(strong);
        const spotify = document.createElement('td');
        spotify.textContent = `${fmtRank(row.spotify.previous_rank)} → ${fmtRank(row.spotify.current_rank)} · ${fmtCount(row.spotify.previous_week_streams)} → ${fmtCount(row.spotify.current_week_streams)}`;
        const youtube = document.createElement('td');
        youtube.textContent = `${fmtRank(row.youtube.previous_rank)} → ${fmtRank(row.youtube.current_rank)} · ${fmtCount(row.youtube.previous_week_views)} → ${fmtCount(row.youtube.current_week_views)}`;
        const status = document.createElement('td');
        const label = document.createElement('strong');
        const koreanStatus = {
          'DUAL_CHART_REVIEWED':'교차 차트 검수 완료',
          'DUAL_CHART_REVIEW_PENDING':'두 플랫폼 곡 식별 검수 대기',
          'SPOTIFY_ONLY_REVIEW_PENDING':'Spotify 단독 근거 · 검수 대기',
          'YOUTUBE_ONLY_REVIEW_PENDING':'YouTube 단독 근거 · 검수 대기',
          'HOLD_VERSION':'버전 차이 · 보류',
          'HOLD_FACT_MISMATCH':'원본 수치 불일치 · 중단',
          'HOLD_AMBIGUOUS':'중복 기록 · 식별 필요',
          'INSUFFICIENT_OBSERVATIONS':'연속 주차 근거 부족',
        };
        label.textContent = koreanStatus[row.review_status] || '검수 필요';
        label.title = row.review_status;
        label.className = row.eligible_for_current_dual_chart_article ? 'review-queue-ok' : 'review-queue-hold';
        const guidance = document.createElement('p'); guidance.textContent = row.review_note;
        status.append(label, guidance);
        function safeLink(url, expectedHost, caption) {
          try {
            const u = new URL(url);
            if (u.protocol !== 'https:' || u.hostname !== expectedHost) return;
            const a = document.createElement('a'); a.href = u.href;
            a.target = '_blank'; a.rel = 'noopener noreferrer'; a.textContent = caption;
            const span = document.createElement('span'); span.className = 'review-queue-link'; span.appendChild(a);
            status.appendChild(span);
          } catch { /* Missing/untrusted URLs are omitted. */ }
        }
        safeLink(row.spotify.chart_track_link, 'open.spotify.com', 'Spotify 음원 ↗');
        safeLink(row.youtube.representative_video_link_only, 'www.youtube.com', 'YouTube 참고영상 ↗');
        tr.append(title, spotify, youtube, status);
        tbody.appendChild(tr);
      }
      table.appendChild(tbody); wrap.appendChild(table); reviewBox.appendChild(wrap);
    }
    const caution = document.createElement('p'); caution.className = 'news-review-caution';
    caution.textContent = 'Top 200/100에서 미확인 = 조회수 0이 아님. 곡 버전·K-POP 분류는 사람이 검수해야 하고, 기존 승인도 새 주차로 자동 이전되지 않아.';
    reviewBox.appendChild(caution);
    reviewBox.hidden = false;
    reviewBox.scrollIntoView({behavior:'smooth', block:'nearest'});
  }
  if (btnReview && reviewBox) btnReview.addEventListener('click', async () => {
    if (busy) return;
    setBusy(true); statusEl.textContent = '현재 선택곡의 차트 근거를 확인하는 중…';
    try {
      const report = await requestJson('/api/news/review-candidates' + weekQuery);
      showReviewQueue(report);
      statusEl.textContent = '검수 후보표를 표시했어. 아직 새 곡을 승인하거나 기사에 추가하지 않았어.';
    } catch (e) { statusEl.textContent = `검수 후보 확인 실패: ${e.message}`; }
    finally { setBusy(false); }
  });
  // STEP17A: Spotify-only editorial candidate preview. No AI, no approval.
  if (btnSpotifyOnly) btnSpotifyOnly.addEventListener('click', async () => {
    if (busy) return;
    setBusy(true);
    statusEl.textContent = 'Spotify 단독 검수 후보의 2주간 수치를 확인하는 중…';
    try {
      const result = await requestJson('/api/news/spotify-only-preview' + weekQuery);
      renderArticle(result.article);
      sourceEl.textContent = `검수 대기 Fact Sheet: ${result.source} · 유료 AI 미호출 · 최종 출고 미승인`;
      statusEl.textContent = `Spotify 단독 검수 후보 ${result.candidate_count}곡의 무료 초안을 표시했어. 곡·버전·K-POP 분류 확인 전에는 기사 출고 또는 유료 AI 생성 불가.`;
    } catch (e) { statusEl.textContent = `Spotify 단독 검수 초안: ${e.message}`; }
    finally { setBusy(false); }
  });
  btnPreview.addEventListener('click', () => runFree('preview'));
  btnSaved.addEventListener('click', () => runFree('saved'));
  btnPaid.addEventListener('click', async () => {
    if (busy) return;
    setBusy(true);
    try {
      // Refresh on click: no stale client selection sent in request body.
      const fresh = await refreshSelection();
      if (!fresh.can_generate) throw new Error('선택된 곡 중 검수 완료된 곡이 없어 기사 생성을 중단했어.');
      const names = fresh.approved_tracks.map(t => `${t.artist} — ${t.track}`).join(', ');
      const excluded = fresh.excluded_tracks.length;
      const msg = `현재 검수된 ${fresh.approved_tracks.length}곡(${names})만으로 OpenAI 유료 호출 1회를 할까?` +
        (excluded ? `\n검수 대기 ${excluded}곡은 제외돼.` : '') + '\n승인되지 않은 기사가 자동 게시되지는 않아.';
      if (!window.confirm(msg)) { statusEl.textContent = '유료 생성이 취소됐어.'; return; }
      statusEl.textContent = 'OpenAI 1회 호출 중… 완료될 때까지 다시 누르지 마.';
      const data = await requestJson('/api/news/generate', {
        method:'POST',
        headers:{'Content-Type':'application/json','X-Requested-With':'KpopNewsPanel'},
        body:JSON.stringify({confirm_paid:true, week_end: requestedWeekEnd})
      });
      displayArticle(data);
    } catch (e) { statusEl.textContent = `오류: ${e.message} · 유료 요청이 있었을 수 있으니 재시도 전 사용량을 확인해 줘.`; }
    finally { setBusy(false); }
  });
  refreshSelection().then(() => {
    if (!newsWeekCompatible) statusEl.textContent = '현재 선택 주차는 기존 검수 완료 Fact Sheet와 달라. 먼저 신규 주차 곡 검수를 진행해 줘.';
  }).catch(e => {
    countEl.textContent = '선택 목록을 불러오지 못했어.';
    statusEl.textContent = `오류: ${e.message}`;
  });
})();
