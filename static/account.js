'use strict';
async function authenticate(action) {
  const msg = document.querySelector('#message');
  try {
    const r = await fetch('/api/auth/' + action, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({username:document.querySelector('#username').value,password:document.querySelector('#password').value})});
    const data = await r.json();
    if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '입력값을 확인하세요.');
    if (action === 'login') location.href = '/editorial';
    else msg.textContent = '회원가입 완료. 로그인해 주세요.';
  } catch(e) {msg.textContent = e.message;}
}
document.querySelector('#auth').addEventListener('submit', e => {e.preventDefault(); authenticate('login');});
document.querySelector('#signup').addEventListener('click', () => authenticate('signup'));
