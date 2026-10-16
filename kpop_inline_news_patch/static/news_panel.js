/* K-POP DATA LAB: 메인 화면 인라인 기사 생성. 사용자가 클릭할 때만 유료 API 호출. */
(() => {
  'use strict';
  const root = document.getElementById('news-inline-panel');
  if (!root) return;
  const generateButton = document.getElementById('news-generate-btn');
  const savedButton = document.getElementById('news-saved-btn');
  const status = document.getElementById('news-status');
  const output = document.getElementById('news-article-output');
  const source = document.getElementById('news-result-source');
  let busy = false;

  function render(article) {
    output.replaceChildren();
    const blocks = String(article || '').trim().split(/\n\s*\n/);
    blocks.forEach((block, i) => {
      const line = block.trim();
      if (!line) return;
      const el = document.createElement(i === 0 ? 'h3' : 'p');
      // HTML을 삽입하지 않고 글자로만 렌더링: 모델 출력의 XSS 방지
      el.textContent = line.replace(/^#{1,6}\s+/, '').replace(/\*\*/g, '');
      output.appendChild(el);
    });
    output.hidden = false;
    output.classList.add('visible');
  }

  function setBusy(value) {
    busy = value;
    generateButton.disabled = value;
    savedButton.disabled = value;
  }

  async function showResponse(response) {
    let data;
    try { data = await response.json(); } catch { throw new Error('서버 응답을 읽지 못했습니다.'); }
    if (!response.ok) {
      const detail = typeof data.detail === 'string' ? data.detail : '요청을 처리할 수 없습니다.';
      throw new Error(detail);
    }
    render(data.article);
    source.textContent = `저장 위치: ${data.source || '정보 없음'} · 검수 전 초안 · 출고 미승인`;
    status.textContent = data.ai_generated_now
      ? 'AI가 새 기사 초안을 생성했어. Fact Sheet와 대조해 최종 검수해 줘.'
      : '저장된 기사 수정본을 불러왔어. 새 API 요금은 발생하지 않았어.';
    output.scrollIntoView({behavior: 'smooth', block: 'nearest'});
  }

  savedButton.addEventListener('click', async () => {
    if (busy) return;
    setBusy(true);
    status.textContent = '저장된 기사 읽는 중…';
    try {
      const resp = await fetch('/api/news/article?variant=edited', {cache:'no-store'});
      await showResponse(resp);
    } catch (error) { status.textContent = `오류: ${error.message}`; }
    finally { setBusy(false); }
  });

  generateButton.addEventListener('click', async () => {
    if (busy) return;
    if (!window.confirm('OpenAI API를 1회 호출해 새 기사 초안을 생성할까요? 사용료가 발생할 수 있어.')) return;
    setBusy(true);
    status.textContent = 'OpenAI에서 기사를 생성 중이야. 버튼을 다시 누르지 말고 잠시 기다려 줘…';
    try {
      const resp = await fetch('/api/news/generate', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-Requested-With':'KpopNewsPanel'},
        body: JSON.stringify({confirm_paid:true})
      });
      await showResponse(resp);
    } catch (error) {
      status.textContent = `오류: ${error.message} 중복 과금을 피하려면 재시도 전 사용 내역을 확인해 줘.`;
    } finally { setBusy(false); }
  });
})();
