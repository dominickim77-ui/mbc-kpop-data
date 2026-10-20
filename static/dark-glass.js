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
  addEventListener('hashchange', activeLink); activeLink();
  // Tables retain their existing form controls and become keyboard-scrollable.
  document.querySelectorAll('.dashboard-table-scroll,.weekly-table-scroll').forEach(el => {
    el.tabIndex = 0; el.setAttribute('role', 'region');
    el.setAttribute('aria-label', '데이터 표 · 좌우 스크롤');
  });
})();
