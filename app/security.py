"""Local-product security: host/origin checks, CSRF, CSP, cookies.

No authentication: the product binds to loopback and is single-user. The CSRF
token is a synchronizer token bound to an HttpOnly, SameSite=Strict session
cookie. Mutations are POST-only.
"""

from __future__ import annotations

import hmac
import secrets
from hashlib import sha256
from urllib.parse import urlparse

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


def csrf_for(session: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), session.encode("utf-8"), sha256).hexdigest()


def _hostname(value: str | None) -> str:
    if not value:
        return ""
    if "://" in value:
        return urlparse(value).hostname or ""
    return value.split(":", 1)[0]


class SecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, secret_key: str, allowed_hosts: tuple[str, ...]) -> None:
        super().__init__(app)
        self.secret_key = secret_key
        self.allowed_hosts = set(allowed_hosts)

    async def dispatch(self, request: Request, call_next):
        host = _hostname(request.headers.get("host"))
        if host and host not in self.allowed_hosts:
            return PlainTextResponse("Host not allowed", status_code=400)

        origin = request.headers.get("origin")
        if origin and _hostname(origin) not in self.allowed_hosts:
            return PlainTextResponse("Origin not allowed", status_code=400)

        session = request.cookies.get("pf_session")
        new_session = False
        if not session:
            session = secrets.token_urlsafe(24)
            new_session = True
        request.state.session_token = session
        request.state.csrf_token = csrf_for(session, self.secret_key)

        response = await call_next(request)
        if new_session:
            response.set_cookie(
                "pf_session", session, httponly=True, samesite="strict",
                secure=False, path="/", max_age=60 * 60 * 12,
            )
        for key, value in SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        return response


def require_csrf(request: Request) -> None:
    session = getattr(request.state, "session_token", None) or request.cookies.get("pf_session")
    expected = csrf_for(session or "", request.app.state.settings.secret_key)
    supplied = request.headers.get("x-csrf-token") or request.query_params.get("csrf_token")
    if not supplied or not hmac.compare_digest(str(supplied), expected):
        raise HTTPException(status_code=403, detail="CSRF token missing or invalid")
