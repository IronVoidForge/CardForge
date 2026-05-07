from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote
from urllib.parse import urlencode

from fastapi import Request
from fastapi.responses import RedirectResponse, Response

from cardforge.config import AppSettings

SESSION_COOKIE = "cardforge_session"
CSRF_COOKIE = "cardforge_csrf"
SESSION_TTL_SECONDS = 60 * 60 * 24 * 14
PUBLIC_PATH_PREFIXES = ("/static/", "/manifest.webmanifest", "/service-worker.js", "/offline", "/healthz")
PUBLIC_EXACT_PATHS = {"/login", "/logout"}


@dataclass(frozen=True)
class LoginResult:
    ok: bool
    error: str = ""


class UIAuth:
    """Small signed-cookie auth layer for LAN/mobile operator use.

    CardForge is still intended to run behind a trusted local network/VPN, but
    mobile operation makes accidental LAN exposure more likely.  This class keeps
    the UI dependency-free while providing password login, signed sessions, and
    CSRF tokens for mutating form posts.
    """

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    @property
    def required(self) -> bool:
        return bool(self.settings.ui_require_auth)

    @property
    def password_configured(self) -> bool:
        return bool(self.settings.ui_password)

    def public_path(self, path: str) -> bool:
        if path in PUBLIC_EXACT_PATHS:
            return True
        return path.startswith(PUBLIC_PATH_PREFIXES)

    def authenticate(self, password: str) -> LoginResult:
        expected = self.settings.ui_password
        if not self.required:
            return LoginResult(ok=True)
        if not expected:
            return LoginResult(ok=False, error="UI auth is required but CARDFORGE_UI_PASSWORD is not set.")
        if not hmac.compare_digest(password, expected):
            return LoginResult(ok=False, error="Incorrect password.")
        return LoginResult(ok=True)

    def session_cookie(self) -> str:
        expires = int(time.time()) + SESSION_TTL_SECONDS
        nonce = secrets.token_urlsafe(16)
        payload = f"{expires}.{nonce}"
        return f"{payload}.{self._sign(payload)}"

    def verify_session(self, token: str | None) -> bool:
        if not self.required:
            return True
        if not token:
            return False
        parts = str(token).split(".")
        if len(parts) != 3:
            return False
        payload = ".".join(parts[:2])
        signature = parts[2]
        if not hmac.compare_digest(signature, self._sign(payload)):
            return False
        try:
            expires = int(parts[0])
        except ValueError:
            return False
        return expires >= int(time.time())

    def csrf_token(self) -> str:
        nonce = secrets.token_urlsafe(24)
        return f"{nonce}.{self._sign(nonce)}"

    def verify_csrf(self, token: str | None) -> bool:
        if not self.required:
            return True
        if not token:
            return False
        parts = str(token).split(".")
        if len(parts) != 2:
            return False
        nonce, signature = parts
        return hmac.compare_digest(signature, self._sign(nonce))

    def login_response(self, target: str = "/") -> RedirectResponse:
        response = RedirectResponse(safe_redirect_target(target), status_code=303)
        self.set_auth_cookies(response)
        return response

    def logout_response(self) -> RedirectResponse:
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie(SESSION_COOKIE)
        response.delete_cookie(CSRF_COOKIE)
        return response

    def set_auth_cookies(self, response: Response) -> None:
        session = self.session_cookie()
        csrf = self.csrf_token()
        response.set_cookie(SESSION_COOKIE, session, httponly=True, samesite="lax", max_age=SESSION_TTL_SECONDS)
        response.set_cookie(CSRF_COOKIE, csrf, httponly=False, samesite="lax", max_age=SESSION_TTL_SECONDS)

    def ensure_csrf_cookie(self, request: Request, response: Response) -> None:
        if not self.required:
            return
        current = request.cookies.get(CSRF_COOKIE)
        if current and self.verify_csrf(current):
            return
        response.set_cookie(CSRF_COOKIE, self.csrf_token(), httponly=False, samesite="lax", max_age=SESSION_TTL_SECONDS)

    def _sign(self, payload: str) -> str:
        digest = hmac.new(
            self.settings.ui_session_secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def safe_redirect_target(target: str | None) -> str:
    value = str(target or "/").strip() or "/"
    if not value.startswith("/") or value.startswith("//"):
        return "/"
    return value


def login_url_for(request: Request) -> str:
    path = request.url.path
    if request.url.query:
        path += f"?{request.url.query}"
    return "/login?" + urlencode({"next": path})


async def read_csrf_token(request: Request) -> str:
    header = request.headers.get("x-cardforge-csrf", "").strip()
    if header:
        return header
    content_type = request.headers.get("content-type", "")
    if "application/x-www-form-urlencoded" not in content_type and "multipart/form-data" not in content_type:
        return ""
    body = await request.body()
    await _restore_request_body(request, body)
    if not body:
        return ""
    # Keep parsing dependency-free.  Hidden CSRF tokens are small ASCII values.
    if b"csrf_token=" not in body:
        return ""
    from urllib.parse import parse_qs

    parsed = parse_qs(body.decode("utf-8", errors="ignore"), keep_blank_values=True)
    return str((parsed.get("csrf_token") or [""])[0]).strip()


async def _restore_request_body(request: Request, body: bytes) -> None:
    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": body, "more_body": False}

    request._receive = receive  # type: ignore[attr-defined]


def wants_html(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    return "text/html" in accept or "*/*" in accept


def login_redirect(request: Request) -> RedirectResponse:
    return RedirectResponse(login_url_for(request), status_code=303)


def quoted_url(url: str) -> str:
    return quote(url, safe=":/?#[]@!$&'()*+,;=%")
