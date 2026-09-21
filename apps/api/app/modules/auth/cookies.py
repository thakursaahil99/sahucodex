"""Cookie handling for the refresh token.

Two cookies are set:
  * `sahucodex_refresh` — the opaque refresh token. httpOnly (invisible to JavaScript, so XSS
    cannot steal it) and scoped to /api/auth so it is only ever sent to the auth endpoints.
  * `sahucodex_session` — a non-secret "you appear to be signed in" flag so the Next.js edge can
    redirect without a round trip. It is a UX hint only; the API never trusts it.
"""

from __future__ import annotations

from fastapi import Response

from app.core.config import Settings

REFRESH_COOKIE = "sahucodex_refresh"
SESSION_HINT_COOKIE = "sahucodex_session"
REFRESH_COOKIE_PATH = "/api/auth"


def set_session_cookies(response: Response, settings: Settings, refresh_token: str, max_age: int) -> None:
    secure = settings.use_secure_cookies
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=max_age,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=secure,
        samesite=settings.cookie_samesite,
    )
    response.set_cookie(
        SESSION_HINT_COOKIE,
        "1",
        max_age=max_age,
        path="/",
        httponly=False,
        secure=secure,
        samesite=settings.cookie_samesite,
    )


def clear_session_cookies(response: Response, settings: Settings) -> None:
    secure = settings.use_secure_cookies
    response.delete_cookie(
        REFRESH_COOKIE, path=REFRESH_COOKIE_PATH, httponly=True, secure=secure, samesite=settings.cookie_samesite
    )
    response.delete_cookie(SESSION_HINT_COOKIE, path="/", secure=secure, samesite=settings.cookie_samesite)
