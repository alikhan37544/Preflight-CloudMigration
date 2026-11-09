"""Local-product security: host/origin checks, CSRF, CSP, cookies.

No authentication: the product binds to loopback and is single-user. The CSRF
token is a synchronizer token bound to a signed, HttpOnly, SameSite=Strict
session cookie. Mutations are POST-only.
"""

from __future__ import annotations

import hmac
import secrets
from hashlib import sha256
from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; "
    "frame-ancestors 'none'"
)

SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Cache-Control": "no-store",
}

SESSION_COOKIE = "pf_session"


def csrf_for(session: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), session.encode("utf-8"), sha256).hexdigest()


def _sign_session(session: str, secret: str) -> str:
    return hmac.new(
        secret.encode("utf-8"), b"session:" + session.encode("utf-8"), sha256
    ).hexdigest()


def _session_from_cookie(value: str | None, secret: str) -> str | None:
    if not value or "." not in value:
        return None
    session, signature = value.rsplit(".", 1)
    if not session or not signature:
        return None
    expected = _sign_session(session, secret)
    if not hmac.compare_digest(signature, expected):
        return None
    return session


def _hostname(value: str | None) -> str:
    if not value:
        return ""
    try:
        parsed = urlsplit(value if "://" in value else f"//{value}")
    except ValueError:
        return ""
    return (parsed.hostname or "").strip().lower()


def _origin_key(value: str) -> tuple[str, str, int] | None:
    """Normalise an Origin to (scheme, host, port); None means malformed."""
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not parsed.hostname:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    if port is None:
        port = 443 if scheme == "https" else 80
    return scheme, parsed.hostname.strip().lower(), port


class SecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, secret_key: str, allowed_hosts: tuple[str, ...],
                 allowed_origins: tuple[str, ...] | None = None) -> None:
        super().__init__(app)
        self.secret_key = secret_key
        self.allowed_hosts = {host.strip().lower() for host in allowed_hosts if host}
        self.allowed_origins = tuple(allowed_origins) if allowed_origins is not None else None

    def _allowed_origin_keys(self, request: Request) -> set[tuple[str, str, int]]:
        origins = self.allowed_origins
        if origins is None:
            settings = getattr(request.app.state, "settings", None)
            origins = getattr(settings, "allowed_origins", None)
        if not origins:
            origins = tuple(
                origin
                for host in sorted(self.allowed_hosts)
                for origin in (f"http://{host}", f"http://{host}:8000")
            ) + ("http://testserver",)
        return {
            key for key in (_origin_key(origin) for origin in origins) if key is not None
        }

    def _same_origin_key(self, request: Request, host_header: str) -> tuple[str, str, int] | None:
        # The configured port may not be known to the settings object (for
        # example when uvicorn is started on an alternate local port). An
        # Origin that exactly matches the already-validated Host is same-origin
        # and therefore safe.
        return _origin_key(f"{request.url.scheme}://{host_header}")

    async def dispatch(self, request: Request, call_next):
        host_header = request.headers.get("host")
        host = _hostname(host_header)
        if not host or host not in self.allowed_hosts:
            return PlainTextResponse("Host not allowed", status_code=400)

        origin = request.headers.get("origin")
        if origin:
            origin_key = _origin_key(origin)
            if (
                origin_key is None
                or (
                    origin_key not in self._allowed_origin_keys(request)
                    and origin_key != self._same_origin_key(request, host_header or "")
                )
            ):
                return PlainTextResponse("Origin not allowed", status_code=400)

        session = _session_from_cookie(
            request.cookies.get(SESSION_COOKIE), self.secret_key
        )
        new_session = False
        if not session:
            session = secrets.token_urlsafe(24)
            new_session = True
        request.state.session_token = session
        request.state.csrf_token = csrf_for(session, self.secret_key)

        response = await call_next(request)
        if new_session:
            response.set_cookie(
                SESSION_COOKIE,
                f"{session}.{_sign_session(session, self.secret_key)}",
                httponly=True, samesite="strict",
                secure=False, path="/", max_age=60 * 60 * 12,
            )
        for key, value in SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        return response


async def require_csrf(request: Request) -> None:
    session = getattr(request.state, "session_token", None) or request.cookies.get(SESSION_COOKIE)
    expected = csrf_for(session or "", request.app.state.settings.secret_key)
    supplied = request.headers.get("x-csrf-token")
    if not supplied:
        content_type = (
            request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        )
        if content_type in {"application/x-www-form-urlencoded", "multipart/form-data"}:
            form = await request.form()
            value = form.get("csrf_token")
            if isinstance(value, str):
                supplied = value
    # Deliberately do not accept a token from the query string: URLs leak into
    # logs, referrers, and browser history.
    if not supplied or not hmac.compare_digest(str(supplied), expected):
        raise HTTPException(status_code=403, detail="CSRF token missing or invalid")
