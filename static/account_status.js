'use strict';
(async () => {
  const r = await fetch('/api/auth/me');
  if (!r.ok) {
    if (r.status === 401) {
      const link = document.querySelector('#lab-account > a');
      if (link) link.textContent = '로그인이 필요합니다';
      document.querySelectorAll('[data-nav]:not([data-nav="user"])').forEach(a => {
        a.title = '로그인 후 이용할 수 있습니다';
      });
    }
    return;
  }
  const user = await r.json();
  const bar = document.createElement('nav');
  bar.className = 'account-identity';
  const label = document.createElement('span'); label.textContent = user.username + ' · ' + user.role;
  const link = document.createElement('a'); link.href='/editorial'; link.textContent='기사 · 검수 관리'; link.style.color='#95dfff';
  const dashboard = document.createElement('a'); dashboard.href='/'; dashboard.textContent='Dashboard'; dashboard.style.color='#95dfff';
  const logout = document.createElement('button'); logout.textContent='로그아웃';
  logout.onclick = async () => {const out = await fetch('/api/auth/logout',{method:'POST'}); if(out.ok) location.href='/account';};
  bar.append(label, logout); (document.getElementById('lab-account') || document.body).append(bar);
  const placeholder = document.querySelector('#lab-account > a'); if (placeholder) placeholder.remove();
  if(user.role==='READER') {
    document.querySelectorAll('button[onclick*="News"],button[onclick*="news"]').forEach(el=>el.hidden=true);
  }
})();
