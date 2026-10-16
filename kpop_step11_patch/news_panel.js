/* STEP11: only server-approved CURRENT selection is used for new paid news. */
(() => {
  'use strict';
  const panel = document.getElementById('news-inline-panel');
  if (!panel) return;
  const btnPreview = document.getElementById('news-preview-btn');
  const btnPaid = document.getElementById('news-generate-btn');
  const btnSaved = document.getElementById('news-saved-btn');
  const countEl = document.getElementById('news-selected-count');
  const approvedList = document.getElementById('news-approved-list');
  const excludedList = document.getElementById('news-excluded-list');
  const statusEl = document.getElementById('news-status');
  const output = document.getElementById('news-article-output');
  const sourceEl = document.getElementById('news-result-source');
  let busy = false;
  let selection = null;

  function setBusy(flag) {
    busy = flag;
    btnPreview.disabled = flag || !selection || !selection.can_generate;
    btnPaid.disabled = flag || !selection || !selection.can_generate;
    btnSaved.disabled = flag;
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
    const data = await requestJson('/api/news/selection');
    showSelection(data);
    return data;
  }
  async function runFree(kind) {
    if (busy) return;
    setBusy(true);
    statusEl.textContent = kind === 'preview' ? '현재 선택 곡을 검증하는 중…' : '기존 예시를 읽는 중…';
    try {
      if (kind === 'preview') await refreshSelection();
      const data = await requestJson(kind === 'preview' ? '/api/news/preview' : '/api/news/article?variant=edited');
      displayArticle(data);
    } catch (e) { statusEl.textContent = `오류: ${e.message}`; }
    finally { setBusy(false); }
  }
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
        body:JSON.stringify({confirm_paid:true})
      });
      displayArticle(data);
    } catch (e) { statusEl.textContent = `오류: ${e.message} · 유료 요청이 있었을 수 있으니 재시도 전 사용량을 확인해 줘.`; }
    finally { setBusy(false); }
  });
  refreshSelection().catch(e => {
    countEl.textContent = '선택 목록을 불러오지 못했어.';
    statusEl.textContent = `오류: ${e.message}`;
  });
})();
