"""Opaque, revocable sessions and server-side access control for the existing app."""
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
from collections.abc import MutableSequence
from contextvars import ContextVar

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field
from security.analysis_origin import require_local_analysis_origin
from security.editorial_store import connect, audit

COOKIE = 'kpop_session'
current_user = ContextVar('kpop_user', default=None)
ROLES = {'READER', 'JOURNALIST', 'EDITOR', 'ADMIN'}
STAFF = {'JOURNALIST', 'EDITOR', 'ADMIN'}
router = APIRouter(prefix='/api/auth')


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    value = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=32768, r=8, p=3,
                           maxmem=64*1024*1024).hex()
    return salt + ':' + value


def verify_password(password, stored):
    return hmac.compare_digest(password_hash(password, stored.split(':')[0]), stored)


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def require_role(*roles):
    user = current_user.get()
    if not user:
        raise HTTPException(401, '로그인이 필요합니다.')
    if roles and user['role'] not in roles:
        raise HTTPException(403, '이 기능을 사용할 권한이 없습니다.')
    return user


def session_user(token):
    if not token or len(token) > 128:
        return None
    with connect() as db:
        row = db.execute('SELECT u.id,u.username,u.role FROM users u JOIN sessions s ON u.id=s.user_id '
                         'WHERE s.token_hash=? AND s.expires_at>?', (token_hash(token), int(time.time()))).fetchone()
    return dict(row) if row else None


class Credentials(BaseModel):
    model_config = ConfigDict(extra='forbid')
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=12, max_length=128)


@router.post('/signup', status_code=201)
def signup(body: Credentials):
    name = body.username.strip().casefold()
    if not re.fullmatch(r'[a-z0-9_.@+-]{3,80}', name):
        raise HTTPException(422, '아이디는 영문·숫자 및 _.@+-만 사용할 수 있습니다.')
    hashed = password_hash(body.password)
    try:
        with connect(True) as db:
            uid = db.execute('INSERT INTO users(username,password_hash) VALUES(?,?)', (name, hashed)).lastrowid
            audit(db, uid, 'SIGNUP', uid, {'role': 'READER'})
    except sqlite3.IntegrityError:
        raise HTTPException(409, '이미 등록된 아이디입니다.') from None
    return {'id': uid, 'username': name, 'role': 'READER'}


@router.post('/login')
def login(body: Credentials, request: Request, response: Response):
    name, now = body.username.strip().casefold(), int(time.time())
    # Persist per-account throttling, including nonexistent accounts; proxy headers are not trusted.
    key = token_hash(name)
    with connect(True) as db:
        limit = db.execute('SELECT * FROM login_limits WHERE key=?', (key,)).fetchone()
        if limit and now-limit['window_start'] < 900 and limit['attempts'] >= 10:
            raise HTTPException(429, '로그인 시도가 많습니다. 15분 후 다시 시도하세요.')
        if not limit or now-limit['window_start'] >= 900:
            db.execute('INSERT OR REPLACE INTO login_limits VALUES(?,?,?)', (key, 1, now))
        else:
            db.execute('UPDATE login_limits SET attempts=attempts+1 WHERE key=?', (key,))
        row = db.execute('SELECT * FROM users WHERE username=?', (name,)).fetchone()
    stored = row['password_hash'] if row else password_hash('dummy-unusable-password', '00'*16)
    valid = verify_password(body.password, stored)
    if not row or not valid:
        raise HTTPException(401, '아이디 또는 비밀번호가 올바르지 않습니다.')
    token = secrets.token_urlsafe(32)
    with connect(True) as db:
        db.execute('DELETE FROM login_limits WHERE key=?', (key,))
        db.execute('DELETE FROM sessions WHERE expires_at<=? OR token_hash=?',
                   (now, token_hash(request.cookies.get(COOKIE, ''))))
        db.execute('INSERT INTO sessions VALUES(?,?,?)', (token_hash(token), row['id'], now+28800))
    response.set_cookie(COOKIE, token, httponly=True, samesite='strict', max_age=28800,
                        secure=request.url.scheme == 'https', path='/')
    return {k: row[k] for k in ('id', 'username', 'role')}


@router.post('/logout')
def logout(request: Request, response: Response):
    with connect(True) as db:
        db.execute('DELETE FROM sessions WHERE token_hash=?', (token_hash(request.cookies.get(COOKIE, '')),))
    response.delete_cookie(COOKIE, path='/')
    return {'logged_out': True}


@router.get('/me')
def me():
    return require_role()


class RoleUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: str


@router.get('/users')
def users():
    require_role('ADMIN')
    with connect() as db:
        return [dict(r) for r in db.execute('SELECT id,username,role FROM users ORDER BY id')]


@router.put('/users/{uid}/role')
def set_role(uid: int, body: RoleUpdate):
    actor = require_role('ADMIN')
    if body.role not in ROLES:
        raise HTTPException(422, '알 수 없는 역할입니다.')
    with connect(True) as db:
        row = db.execute('SELECT role FROM users WHERE id=?', (uid,)).fetchone()
        if not row:
            raise HTTPException(404, '계정이 없습니다.')
        if row['role'] == 'ADMIN' and body.role != 'ADMIN':
            if db.execute("SELECT COUNT(*) FROM users WHERE role='ADMIN'").fetchone()[0] <= 1:
                raise HTTPException(409, '마지막 관리자는 해제할 수 없습니다.')
        db.execute('UPDATE users SET role=? WHERE id=?', (body.role, uid))
        db.execute('DELETE FROM sessions WHERE user_id=?', (uid,))
        audit(db, actor['id'], 'ROLE_CHANGED', uid, {'before': row['role'], 'after': body.role})
    return {'id': uid, 'role': body.role, 'login_required': True}


class UserSelection(MutableSequence):
    """Compatibility facade; every operation reads/writes the authenticated user's row."""
    def _read(self):
        uid = require_role()['id']
        with connect() as db:
            return json.loads(db.execute('SELECT selection FROM users WHERE id=?', (uid,)).fetchone()[0])

    def _change(self, operation):
        uid = require_role()['id']
        with connect(True) as db:
            value = json.loads(db.execute('SELECT selection FROM users WHERE id=?', (uid,)).fetchone()[0])
            operation(value)
            db.execute('UPDATE users SET selection=? WHERE id=?', (json.dumps(value), uid))

    def __len__(self): return len(self._read())
    def __getitem__(self, key): return self._read()[key]
    def __setitem__(self, key, value): self._change(lambda v: v.__setitem__(key, value))
    def __delitem__(self, key): self._change(lambda v: v.__delitem__(key))
    def insert(self, index, value): self._change(lambda v: v.insert(index, value))
    def extend(self, values): self._change(lambda v: v.extend(values))
    def clear(self): self._change(lambda v: v.clear())
    def remove(self, value): self._change(lambda v: v.remove(value))
    def __iter__(self): return iter(self._read())
    def __eq__(self, other): return self._read() == other


class AuthMiddleware:
    def __init__(self, app): self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        request = Request(scope)
        path, method = request.url.path, request.method
        public = path.startswith('/static/') or path == '/account' or path in {'/api/auth/signup', '/api/auth/login'}
        token = None
        try:
            if not public:
                user = session_user(request.cookies.get(COOKIE))
                if not user:
                    if method == 'GET' and path in {'/', '/spotify', '/youtube', '/compare', '/editorial'}:
                        return await RedirectResponse('/account', status_code=303)(scope, receive, send)
                    raise HTTPException(401, '로그인이 필요합니다.')
                token = current_user.set(user)
                scope.setdefault('state', {})['user'] = user
                if path.startswith('/api/news/'):
                    if user['role'] not in STAFF:
                        raise HTTPException(403, 'AI News는 JOURNALIST, EDITOR, ADMIN 계정으로 이용할 수 있습니다.')
                if path.startswith('/api/youtube-video-review/'):
                    require_role('EDITOR', 'ADMIN')
                if path == '/add-analysis':
                    require_role(*STAFF)  # Existing endpoint writes MySQL and may query YouTube.
            if method not in {'GET', 'HEAD', 'OPTIONS'}:
                require_local_analysis_origin(request)
            await self.app(scope, receive, send)
        except HTTPException as exc:
            if method == 'POST' and path.startswith(('/select-analysis', '/add-analysis', '/remove-analysis/', '/reset-analysis')) and 'text/html' in request.headers.get('accept', ''):
                from urllib.parse import quote_plus
                target = '/account' if exc.status_code == 401 else '/?message=' + quote_plus(str(exc.detail))
                return await RedirectResponse(target, status_code=303)(scope, receive, send)
            await JSONResponse({'detail': exc.detail}, status_code=exc.status_code)(scope, receive, send)
        except RuntimeError:
            await JSONResponse({'detail': '인증 저장소 초기화가 필요합니다.'}, status_code=503)(scope, receive, send)
        finally:
            if token is not None:
                current_user.reset(token)
