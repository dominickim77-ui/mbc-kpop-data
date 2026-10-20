'use strict';
const authForm = document.querySelector('#auth');
const authSubmit = document.querySelector('#auth-submit');
const authSwitch = document.querySelector('#signup');
let authMode = 'login';
let authPending = false;
function setAuthMode(mode) {
  authMode = mode;
  const signingUp = mode === 'signup';
  document.querySelector('#auth-heading').textContent = signingUp ? 'Create an Account' : 'Welcome Back';
  document.querySelector('#auth-description').textContent = signingUp
    ? '새 계정으로 K-POP 데이터 분석을 시작하세요.'
    : '로그인하고 K-POP 데이터의 이야기를 이어가세요.';
  authSubmit.textContent = signingUp ? 'Create Account' : 'Sign In';
  authSwitch.textContent = signingUp ? 'Back to Sign In' : 'Create an Account';
  document.querySelector('#auth-switch-hint').textContent = signingUp ? '이미 계정이 있으신가요?' : '처음 방문하셨나요?';
  document.querySelector('#password').autocomplete = signingUp ? 'new-password' : 'current-password';
  authForm.dataset.mode = mode;
  document.querySelector('#message').textContent = '';
}
async function authenticate(action) {
  if (authPending || !authForm.reportValidity()) return;
  const msg = document.querySelector('#message');
  authPending = true;
  authSubmit.disabled = authSwitch.disabled = true;
  authForm.setAttribute('aria-busy', 'true');
  authSubmit.textContent = action === 'login' ? 'Signing In…' : 'Creating Account…';
  msg.textContent = '요청을 처리하고 있습니다.';
  msg.dataset.kind = 'pending';
  try {
    const r = await fetch('/api/auth/' + action, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({username:document.querySelector('#username').value,password:document.querySelector('#password').value})});
    const data = await r.json();
    if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '입력값을 확인하세요.');
    if (action === 'login') {
      msg.textContent = '로그인되었습니다. 작업 공간으로 이동합니다.';
      location.href = '/editorial';
    } else {
      setAuthMode('login');
      document.querySelector('#password').value = '';
      msg.dataset.kind = 'success';
      msg.textContent = '회원가입 완료. 일반 회원(READER)으로 가입되었습니다. 로그인해 주세요.';
      document.querySelector('#password').focus();
    }
  } catch(e) {
    msg.dataset.kind = 'error';
    msg.textContent = e.message;
    msg.focus();
  } finally {
    authPending = false;
    authSubmit.disabled = authSwitch.disabled = false;
    authForm.setAttribute('aria-busy', 'false');
    authSubmit.textContent = authMode === 'login' ? 'Sign In' : 'Create Account';
  }
}
authForm.addEventListener('submit', e => {e.preventDefault(); authenticate(authMode);});
authSwitch.addEventListener('click', () => {
  if (authPending) return;
  setAuthMode(authMode === 'login' ? 'signup' : 'login');
  document.querySelector('#username').focus();
});
