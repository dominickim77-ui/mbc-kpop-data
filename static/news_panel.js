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
  const contextEl = document.getElementById('news-result-context');
  function factLabel(value) {
    return ({
      TRACK_IDENTITY_AND_EDITORIAL_CATEGORY_APPROVED: '곡 정보와 분류 검증 완료',
      DRAFT: '검증이 필요합니다.',
      PENDING_HUMAN_REVIEW: '사람의 검수가 필요합니다.'
    })[value] || '검증 상태를 확인해 주세요.';
  }
  function beginResult(kind, historical = false) {
    output.hidden = true; output.replaceChildren();
    reviewBox.hidden = true; reviewBox.replaceChildren();
    sourceEl.textContent = '';
    const tracks = (selection?.selected_tracks || []).map(t => `${t.artist} — ${t.track}`).join(', ') || '선택한 곡 없음';
    contextEl.textContent = historical
      ? `${kind} · KATSEYE — Animal / LISA — SaWaDiKa · 기준 주: 2026-10-08 · 과거 검수용 사례 (현재 선택과 무관)`
      : `${kind} · 선택: ${tracks} · 기준 주: ${requestedWeekEnd} · Fact Sheet: ${factLabel(selection?.fact_status)} · 최종 승인 필요`;
    contextEl.hidden = false;
  }


  // Presentation gating avoids expected 403 traffic; API authorization remains authoritative.
  if (!['JOURNALIST', 'EDITOR', 'ADMIN'].includes(panel.dataset.userRole)) {
    [btnPreview, btnPaid, btnSaved, btnReview, btnSpotifyOnly].forEach(button => {
      if (button) button.disabled = true;
    });
    countEl.textContent = '개인 분석은 Dashboard에서 이용할 수 있습니다.';
    document.getElementById('news-fact-status').textContent = 'AI News 이용 권한이 필요합니다.';
    statusEl.textContent = 'AI News는 JOURNALIST·EDITOR·ADMIN 권한이 필요합니다. 관리자에게 역할 부여를 요청해 주세요.';
    return;
  }

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
    if (!approved) addLine(approvedList, '검수 완료된 곡이 없습니다. 곡·버전·분류 검수가 필요합니다.');
    const factStatus = document.getElementById('news-fact-status');
    if (factStatus) {
      factStatus.textContent = `Fact Sheet ${data.fact_week_end || requestedWeekEnd}: ${factLabel(data.fact_status)} · 최종 승인 필요` + (data.week_warning ? ` · ${data.week_warning}` : '');
      factStatus.title = data.fact_status || '';
    }
    for (const row of data.approved_tracks) addLine(approvedList, `${row.artist} — ${row.track}`);
    if (!data.excluded_tracks.length) addLine(excludedList, '없음');
    for (const row of data.excluded_tracks) addLine(excludedList, `${row.artist} — ${row.track}: ${row.reason}`);
    setBusy(busy);
  }
  async function requestJson(url, options) {
    const res = await fetch(url, {cache:'no-store', ...options});
    let data;
    try { data = await res.json(); } catch { throw new Error('서버 응답을 읽을 수 없습니다.'); }
    if (!res.ok) {
      const error = new Error(typeof data.detail === 'string' ? data.detail : '입력 내용을 확인해 주세요.');
      error.status = res.status;
      throw error;
    }
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
    if (data.mode !== 'saved_example') {
      const used = (data.selection?.approved_tracks || selection?.approved_tracks || []).map(t => `${t.artist} — ${t.track}`).join(', ');
      contextEl.textContent = `${data.ai_generated_now ? 'AI 기사 생성 (유료)' : '무료 기사 미리보기'} · 기사 대상: ${used || '응답의 기사 본문을 확인해 주세요.'} · 기준 주: ${requestedWeekEnd} · 검증된 Fact Sheet · 최종 승인 필요`;
    }
    sourceEl.textContent = `근거/저장 위치: ${data.source || '없음'} · 최종 검수 필요 · 출고 미승인`;
    if (data.mode === 'saved_example') {
      statusEl.textContent = '현재 선택과 별개인 과거 기사 예시이며, 추가 비용은 없습니다.';
      contextEl.textContent += ` · ${data.creation_date_label || '생성 시점'}: ${data.source_created_at_utc || '기존 기록에 없음'} · 출처: ${data.source}`;
    } else if (data.ai_generated_now) {
      statusEl.textContent = '검수된 곡으로 AI 초안을 생성했습니다. 수치와 출처를 확인해 주세요.';
      if (data.generation_id) sourceEl.textContent += ` · 기사 저장 시 사용할 생성 기록 ID: ${data.generation_id}`;
    } else {
      statusEl.textContent = '선택한 곡의 무료 초안이며, 유료 AI는 사용하지 않았습니다.';
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
    beginResult(kind === 'preview' ? '선택한 곡의 기사 · 무료 미리보기' : '과거 기사 예시', kind !== 'preview');
    statusEl.textContent = kind === 'preview' ? '선택한 곡을 검증하고 있습니다.' : '기사 예시를 불러오고 있습니다.';
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
      empty.textContent = '분석할 곡을 선택하시면 검증 자료를 확인할 수 있습니다.';
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
          'DUAL_CHART_REVIEWED':'기사 분석에 사용할 수 있습니다.',
          'DUAL_CHART_REVIEW_PENDING':'두 플랫폼 곡 식별 검수 대기',
          'SPOTIFY_ONLY_REVIEW_PENDING':'YouTube 주간 차트에서 확인되지 않았습니다.',
          'YOUTUBE_ONLY_REVIEW_PENDING':'Spotify 주간 차트에서 확인되지 않았습니다.',
          'HOLD_VERSION':'버전 차이 · 보류',
          'HOLD_FACT_MISMATCH':'원본 수치 불일치 · 중단',
          'HOLD_AMBIGUOUS':'중복 기록 · 식별 필요',
          'INSUFFICIENT_OBSERVATIONS':'연속 주차 근거 부족',
        };
        label.textContent = koreanStatus[row.review_status] || '검수 필요';
        if (row.review_status === 'SPOTIFY_ONLY_REVIEW_PENDING' &&
            (row.youtube.previous_week_views != null || row.youtube.current_week_views != null)) {
          label.textContent = 'YouTube의 연속 2주 자료를 확인할 수 없습니다.';
        }
        if (row.review_status === 'YOUTUBE_ONLY_REVIEW_PENDING' &&
            (row.spotify.previous_week_streams != null || row.spotify.current_week_streams != null)) {
          label.textContent = 'Spotify의 연속 2주 자료를 확인할 수 없습니다.';
        }
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
    caution.textContent = 'Top 200/100에서 미확인 = 조회수 0이 아님. 곡 버전·K-POP 분류는 사람이 검수해야 하고, 기존 승인은 새 주차에 자동 적용되지 않습니다.';
    reviewBox.appendChild(caution);
    reviewBox.hidden = false;
    reviewBox.scrollIntoView({behavior:'smooth', block:'nearest'});
  }
  if (btnReview && reviewBox) btnReview.addEventListener('click', async () => {
    if (busy) return;
    setBusy(true); beginResult('데이터 근거 확인'); statusEl.textContent = '현재 선택곡의 차트 근거를 확인하는 중…';
    try {
      const report = await requestJson('/api/news/review-candidates' + weekQuery);
      showReviewQueue(report);
      statusEl.textContent = '검수 후보를 표시했습니다. 기사 이용 전 승인이 필요합니다.';
    } catch (e) { statusEl.textContent = `검수 후보 확인 실패: ${e.message}`; }
    finally { setBusy(false); }
  });
  // STEP17A: Spotify-only editorial candidate preview. No AI, no approval.
  if (btnSpotifyOnly) btnSpotifyOnly.addEventListener('click', async () => {
    if (busy) return;
    setBusy(true);
    beginResult('Spotify 단독 초안 · 무료 검수용');
    statusEl.textContent = 'Spotify 단독 검수 후보의 2주간 수치를 확인하는 중…';
    try {
      const result = await requestJson('/api/news/spotify-only-preview' + weekQuery);
      renderArticle(result.article);
      sourceEl.textContent = `검수 대기 Fact Sheet: ${result.source} · 유료 AI 미호출 · 최종 출고 미승인`;
      statusEl.textContent = `Spotify 단독 검수 후보 ${result.candidate_count}곡의 무료 초안을 표시했습니다. 곡·버전·K-POP 분류 확인 전에는 기사 출고 또는 유료 AI 생성 불가.`;
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
      if (!fresh.can_generate) throw new Error('검수 완료된 곡이 없어 기사를 생성할 수 없습니다.');
      const names = fresh.approved_tracks.map(t => `${t.artist} — ${t.track}`).join(', ');
      const excluded = fresh.excluded_tracks.length;
      const msg = `현재 검수된 ${fresh.approved_tracks.length}곡(${names})으로 유료 AI 초안을 생성하시겠습니까? (OpenAI 1회 호출)` +
        (excluded ? `\n검수 대기 ${excluded}곡은 제외됩니다.` : '') + '\n기사는 사람의 승인 후 게시할 수 있습니다.';
      if (!window.confirm(msg)) { statusEl.textContent = '유료 생성을 취소했습니다.'; return; }
      beginResult('선택한 곡의 기사 · 유료 AI 생성');
      statusEl.textContent = '유료 AI 초안을 생성하고 있습니다.';
      const data = await requestJson('/api/news/generate', {
        method:'POST',
        headers:{'Content-Type':'application/json','X-Requested-With':'KpopNewsPanel'},
        body:JSON.stringify({confirm_paid:true, week_end: requestedWeekEnd})
      });
      displayArticle(data);
    } catch (e) { statusEl.textContent = `오류: ${e.message} · 유료 요청이 처리되었을 수 있습니다. 재시도 전 사용량을 확인해 주세요.`; }
    finally { setBusy(false); }
  });
  refreshSelection().then(() => {
    if (!selection.can_generate) statusEl.textContent = selection.week_warning || '선택한 기간의 곡 검수가 필요합니다. 검증 자료를 확인해 주세요.';
  }).catch(e => {
    countEl.textContent = '선택한 곡을 불러올 수 없습니다.';
    if (e.status === 403) {
      countEl.textContent = 'AI News 이용 권한이 필요합니다.';
      [btnPreview, btnPaid, btnSaved, btnReview, btnSpotifyOnly].forEach(button => {
        if (button) button.disabled = true;
      });
      document.getElementById('news-fact-status').textContent = '권한이 없어 데이터 검증 상태를 확인할 수 없습니다.';
    }
    statusEl.textContent = `오류: ${e.message}`;
  });
})();
