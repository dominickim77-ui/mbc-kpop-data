'use strict';
(() => {
  document.querySelector('.top-account')?.setAttribute('aria-label', '계정 / Account');
  const menu = document.querySelector('.menu-toggle');
  const sidebar = document.querySelector('.lab-sidebar');
  function closeMenu() {
    document.body.classList.remove('menu-open');
    menu?.setAttribute('aria-expanded', 'false');
    menu?.setAttribute('aria-label', '메뉴 열기');
  }
  menu?.addEventListener('click', () => {
    const open = document.body.classList.toggle('menu-open');
    menu.setAttribute('aria-expanded', String(open));
    menu.setAttribute('aria-label', open ? '메뉴 닫기' : '메뉴 열기');
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && document.body.classList.contains('menu-open')) {
      closeMenu(); menu.focus();
    }
  });
  document.addEventListener('click', event => {
    if (!sidebar?.contains(event.target) && !menu?.contains(event.target)) closeMenu();
  });
  function activeLink() {
    const target = location.pathname + (location.hash === '#discover' || location.hash === '#news-inline-panel' ? location.hash : '');
    document.querySelectorAll('[data-nav]').forEach(a => {
      if (a.getAttribute('href') === target) a.setAttribute('aria-current', 'page');
      else a.removeAttribute('aria-current');
    });
  }
  sidebar?.querySelectorAll('a').forEach(a => a.addEventListener('click', closeMenu));
  // Keep form errors inside the Dashboard, including expired sessions and bad input.
  document.querySelectorAll('form[action="/select-analysis"],form[action="/reset-analysis"],form[action^="/remove-analysis/"]').forEach(form => {
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (form.dataset.pending) return;
      const button = event.submitter;
      if (button?.hasAttribute('data-collect-confirm') &&
          !confirm('선택한 곡의 원본 데이터를 저장하시겠습니까? 개인 분석 선택만 하시려면 취소해 주세요.')) return;
      let status = document.querySelector('#analysis-form-status');
      if (!status) {
        status = document.createElement('p');
        status.id = 'analysis-form-status';
        status.className = 'search-message';
        status.setAttribute('role', 'alert');
        status.tabIndex = -1;
      }
      form.append(status);
      status.textContent = '선택 목록을 처리하고 있습니다.';
      form.dataset.pending = 'true';
      if (button) button.disabled = true;
      try {
        const response = await fetch(button?.getAttribute('formaction') || form.action, {
          method: 'POST', body: new FormData(form), headers: {'Accept': 'application/json'}
        });
        if (!response.ok) {
          const data = await response.json();
          throw new Error(typeof data.detail === 'string' ? data.detail : '입력 내용을 확인해 주세요.');
        }
        if (response.redirected) location.assign(response.url);
        else location.reload();
      } catch (error) {
        status.textContent = error instanceof TypeError ? '서버에 연결할 수 없습니다. 연결 상태를 확인해 주세요.' : error.message;
        status.focus();
      } finally {
        delete form.dataset.pending;
        if (button) button.disabled = false;
      }
    });
  });
  addEventListener('hashchange', activeLink); activeLink();
  // Tables retain their existing form controls and become keyboard-scrollable.
  document.querySelectorAll('.dashboard-table-scroll,.weekly-table-scroll').forEach(el => {
    el.tabIndex = 0; el.setAttribute('role', 'region');
    el.setAttribute('aria-label', '데이터 표 · 좌우 스크롤');
  });
})();
