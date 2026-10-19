"""Validate browser source origin before analysis mutations; no DB or session state."""
from urllib.parse import urlsplit

from fastapi import HTTPException, Request

# Server-side allowlist for the documented direct local development server.
# Different schemes/ports/hosts require explicit configuration review and tests.
ALLOWED_ANALYSIS_ORIGINS = frozenset({('http', '127.0.0.1', 8000), ('http', 'localhost', 8000)})
_FETCH_SITES = frozenset({'same-origin', 'same-site', 'none'})
_DENIED = '현재 로컬 페이지에서 보낸 분석 요청인지 확인할 수 없습니다. 페이지 주소를 확인한 뒤 다시 시도해 주세요.'


def _origin(value: str, *, referer: bool = False) -> tuple[str, str, int]:
    """Parse a single authority, rejecting inputs browsers do not send as origins."""
    if (not value or any(ord(c) <= 32 or ord(c) == 127 for c in value)
            or '\\' in value):
        raise ValueError('Invalid origin text')
    parsed = urlsplit(value)
    if (parsed.scheme not in {'http', 'https'} or not parsed.netloc or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or not parsed.netloc.isascii() or '%' in parsed.netloc or ',' in parsed.netloc
            or parsed.fragment or '#' in value):
        raise ValueError('Invalid origin authority')
    if not referer and (parsed.path or parsed.query or '?' in value):
        raise ValueError('Origin must not have a path or query')
    # Reject empty port syntax; urlsplit otherwise accepts host: as no port.
    if parsed.netloc.endswith(':'):
        raise ValueError('Empty port')
    port = parsed.port if parsed.port is not None else (80 if parsed.scheme == 'http' else 443)
    if not 1 <= port <= 65535:
        raise ValueError('Invalid port')
    return parsed.scheme, parsed.hostname, port


def _single_header(request: Request, name: str) -> str | None:
    values = request.headers.getlist(name)
    if len(values) > 1:
        raise ValueError('Duplicate security header')
    return values[0] if values else None


def require_local_analysis_origin(request: Request) -> None:
    """FastAPI dependency for the three native HTML analysis POST forms only."""
    try:
        host = _single_header(request, 'host')
        origin = _single_header(request, 'origin')
        referer = _single_header(request, 'referer')
        fetch_site = _single_header(request, 'sec-fetch-site')
        if not host or request.scope.get('scheme') not in {'http', 'https'}:
            raise ValueError('No trusted target')
        # Do not derive the allowlist from Host or client-supplied forwarded headers.
        target = _origin(request.scope['scheme'] + '://' + host)
        if target not in ALLOWED_ANALYSIS_ORIGINS:
            raise ValueError('Target not allowlisted')
        if fetch_site is not None and fetch_site not in _FETCH_SITES:
            raise ValueError('Cross-site or invalid Fetch Metadata')
        if origin is not None:
            source = _origin(origin)
        elif referer is not None:
            source = _origin(referer, referer=True)
        else:
            raise ValueError('Missing source')
        if source != target:
            raise ValueError('Source differs from target')
    except (ValueError, TypeError):
        # Do not reflect Origin/Referer, which can contain sensitive query data.
        raise HTTPException(status_code=403, detail=_DENIED) from None
