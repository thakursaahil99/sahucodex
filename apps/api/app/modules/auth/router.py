from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Request, Response, status
from fastapi.responses import JSONResponse

from app.core.deps import SettingsDep
from app.core.errors import AppError, error_body, unauthorized
from app.core.net import client_ip, user_agent
from app.core.rate_limit import RateLimiter, get_rate_limiter
from app.modules.auth.cookies import REFRESH_COOKIE, clear_session_cookies, set_session_cookies
from app.modules.auth.deps import AuthServiceDep, CurrentSessionId, CurrentUser, verify_origin
from app.modules.auth.schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    RegisterResponse,
    ResetPasswordRequest,
    SessionOut,
    TokenResponse,
    VerifyEmailRequest,
)
from app.modules.auth.service import IssuedSession
from app.modules.users.schemas import to_user_me

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_response(session: IssuedSession) -> TokenResponse:
    return TokenResponse(
        access_token=session.access_token, expires_in=session.expires_in, user=to_user_me(session.user)
    )


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    request: Request,
    settings: SettingsDep,
    service: AuthServiceDep,
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> RegisterResponse:
    ip = client_ip(request)
    await limiter.enforce("register:ip", ip, settings.rate_limit_register)
    user = await service.register(
        email=body.email, username=body.username, password=body.password, ip=ip, user_agent=user_agent(request)
    )
    return RegisterResponse(user=to_user_me(user))


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest, request: Request, response: Response, settings: SettingsDep, service: AuthServiceDep
):
    session = await service.login(
        identifier=body.identifier, password=body.password, ip=client_ip(request), user_agent=user_agent(request)
    )
    set_session_cookies(response, settings, session.refresh_token, session.refresh_max_age)
    return _token_response(session)


@router.post("/refresh", response_model=TokenResponse, dependencies=[Depends(verify_origin)])
async def refresh(
    request: Request,
    response: Response,
    settings: SettingsDep,
    service: AuthServiceDep,
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
):
    try:
        if not refresh_token:
            raise unauthorized("REFRESH_TOKEN_MISSING", "No active session")
        session = await service.refresh(refresh_token, ip=client_ip(request), user_agent=user_agent(request))
    except AppError as exc:
        if exc.status_code != 401 or exc.code == "REFRESH_TOKEN_RACE":
            raise  # a benign race must keep the cookie the other tab just received
        # The session is definitively dead: drop both cookies so the browser stops treating
        # the user as signed in (otherwise /login and /dashboard could redirect to each other).
        failure = JSONResponse(error_body(exc.code, exc.message), status_code=exc.status_code, headers=exc.headers)
        clear_session_cookies(failure, settings)
        return failure
    set_session_cookies(response, settings, session.refresh_token, session.refresh_max_age)
    return _token_response(session)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(verify_origin)])
async def logout(
    request: Request,
    settings: SettingsDep,
    service: AuthServiceDep,
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
) -> Response:
    await service.logout(refresh_token, ip=client_ip(request), user_agent=user_agent(request))
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookies(response, settings)
    return response


@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(user: CurrentUser, session_id: CurrentSessionId, service: AuthServiceDep) -> list[SessionOut]:
    rows = await service.list_sessions(user, session_id)
    return [
        SessionOut(
            id=token.family_id,
            ip_address=token.ip_address,
            user_agent=token.user_agent,
            last_active_at=token.created_at,
            current=current,
        )
        for token, current in rows
    ]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    session_id: uuid.UUID, request: Request, user: CurrentUser, service: AuthServiceDep
) -> Response:
    await service.revoke_session(user, session_id, ip=client_ip(request), user_agent=user_agent(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/verify-email/request", response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED)
async def request_email_verification(user: CurrentUser, service: AuthServiceDep) -> MessageResponse:
    await service.send_verification_email(user)
    return MessageResponse(message="If your email is not yet verified, a link is on its way.")


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(body: VerifyEmailRequest, service: AuthServiceDep) -> MessageResponse:
    await service.verify_email(body.token)
    return MessageResponse(message="Email verified.")


@router.post("/password/forgot", response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(body: ForgotPasswordRequest, request: Request, service: AuthServiceDep) -> MessageResponse:
    await service.forgot_password(body.email, ip=client_ip(request))
    return MessageResponse(message="If that email is registered, a reset link is on its way.")


@router.post("/password/reset", response_model=MessageResponse)
async def reset_password(body: ResetPasswordRequest, request: Request, service: AuthServiceDep) -> MessageResponse:
    await service.reset_password(body.token, body.new_password, ip=client_ip(request), user_agent=user_agent(request))
    return MessageResponse(message="Password updated. Please sign in with your new password.")
