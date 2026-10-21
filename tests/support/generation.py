"""Authenticated generation fixture; temporary SQLite only, no production records."""
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from starlette.requests import Request
from starlette.responses import Response
from security import auth, editorial_store as store


@contextmanager
def generation_session():
    with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
        'KPOP_AUTH_DB': str(Path(directory) / 'generation.sqlite3'),
        'KPOP_DB_BACKEND': 'legacy', 'PYTHON_DOTENV_DISABLED': '1',
    }):
        store.initialize()
        credentials = auth.Credentials(username='generation_fixture', password='Synthetic-generation-test-only')
        account = auth.signup(credentials)
        with store.connect(True) as db:
            db.execute("UPDATE users SET role='EDITOR' WHERE id=?", (account['id'],))
        response = Response()
        auth.login(credentials, Request({'type':'http', 'headers':[], 'scheme':'http', 'path':'/'}), response)
        cookie = response.headers['set-cookie'].split(';')[0]
        user = auth.session_user(cookie.split('=',1)[1])
        assert user and user['role'] == 'EDITOR'
        token = auth.current_user.set(user)
        try:
            yield user, cookie
        finally:
            auth.current_user.reset(token)
