"""In-process HTTP requests; no sockets or running server."""
import json
from contextlib import nullcontext
from urllib.parse import urlencode
import app as site


async def asgi_request(path, method='GET', payload=None, *, cookie=None):
    events = []
    headers = {'host': '127.0.0.1:8000', 'origin': 'http://127.0.0.1:8000',
               'content-type': 'application/json', 'x-requested-with': 'KpopNewsPanel'}
    if cookie is not None:
        headers['cookie'] = cookie
    route, _, query = path.partition('?')
    scope = {'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
             'method': method, 'scheme': 'http', 'path': route, 'raw_path': route.encode(),
             'query_string': query.encode(), 'root_path': '',
             'headers': [(k.encode(), v.encode()) for k, v in headers.items()],
             'client': ('127.0.0.1', 1234), 'server': ('127.0.0.1', 8000)}
    delivered = False

    async def receive():
        nonlocal delivered
        if not delivered:
            delivered = True
            return {'type': 'http.request', 'body': json.dumps(payload).encode() if payload else b'',
                    'more_body': False}
        return {'type': 'http.disconnect'}

    async def send(event):
        events.append(event)

    # Existing route regressions supply a server-authenticated editor fixture.
    # STEP23 tests exercise real login, cookies, and RBAC separately.
    from unittest.mock import patch
    session = nullcontext() if cookie is not None else patch('security.auth.session_user', return_value={'id': 999, 'username': 'regression-editor', 'role': 'EDITOR'})
    with session:
        await site.app(scope, receive, send)
    status = next(e['status'] for e in events if e['type'] == 'http.response.start')
    body = b''.join(e.get('body', b'') for e in events if e['type'] == 'http.response.body')
    return status, json.loads(body)


async def form_request(path, headers=None, form=None, method='POST', scheme='http'):
    raw_headers = list(headers if headers is not None else [
        ('host', '127.0.0.1:8000'), ('origin', 'http://127.0.0.1:8000')])
    raw_headers.append(('content-type', 'application/x-www-form-urlencoded'))
    route, _, query = path.partition('?')
    scope = {'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
             'method': method, 'scheme': scheme, 'path': route, 'raw_path': route.encode(),
             'query_string': query.encode(), 'root_path': '',
             'headers': [(k.encode(), v.encode()) for k, v in raw_headers],
             'client': ('127.0.0.1', 1234), 'server': ('127.0.0.1', 8000)}
    data = form if form is not None else {'selected_ranks': [1], 'search_artist': 'KATSEYE',
                                         'week_end': '2026-10-08'}
    events, sent = [], False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {'type': 'http.request', 'body': urlencode(data, doseq=True).encode(), 'more_body': False}
        return {'type': 'http.disconnect'}

    async def send(event):
        events.append(event)

    # Existing route regressions supply a server-authenticated editor fixture.
    # STEP23 tests exercise real login, cookies, and RBAC separately.
    from unittest.mock import patch
    with patch('security.auth.session_user', return_value={'id': 999, 'username': 'regression-editor', 'role': 'EDITOR'}):
        await site.app(scope, receive, send)
    start = next(e for e in events if e['type'] == 'http.response.start')
    body = b''.join(e.get('body', b'') for e in events if e['type'] == 'http.response.body')
    return start['status'], dict((k.decode(), v.decode()) for k, v in start['headers']), body
