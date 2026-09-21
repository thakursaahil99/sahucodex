"""SahuJudge API: submit, run, history, and the real-time event socket."""

from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, WebSocket, WebSocketDisconnect, status
from redis.exceptions import RedisError

from app.core.deps import DbSession, RedisDep, SettingsDep
from app.core.pagination import Page, PageParamsDep
from app.core.queue import JobQueue
from app.core.rate_limit import get_rate_limiter
from app.modules.auth.deps import CurrentUser
from app.modules.submissions import events, service
from app.modules.submissions.models import SubmissionStatus, Verdict
from app.modules.submissions.schemas import (
    LANGUAGE_PATTERN,
    SLUG_PATTERN,
    RunCreate,
    RunOut,
    RunQueued,
    SubmissionCreate,
    SubmissionDetail,
    SubmissionQueued,
    SubmissionSummary,
    WsTicket,
)

router = APIRouter(tags=["submissions"])
ws_router = APIRouter()  # mounted at the app root: `general_rate_limit` needs an HTTP Request, a WebSocket has none


def _queue(request: Request) -> JobQueue:
    return request.app.state.queue


QueueDep = Annotated[JobQueue, Depends(_queue)]


@router.post("/submissions", response_model=SubmissionQueued, status_code=status.HTTP_202_ACCEPTED)
async def submit(
    data: SubmissionCreate,
    request: Request,
    user: CurrentUser,
    db: DbSession,
    redis: RedisDep,
    queue: QueueDep,
    settings: SettingsDep,
) -> SubmissionQueued:
    """Records the submission and returns its id immediately; the judge worker does the work."""
    await get_rate_limiter(request).enforce("submit", str(user.id), settings.rate_limit_submit)
    submission = await service.create_submission(db, redis, queue, settings, user, data)
    return SubmissionQueued(id=submission.id, status=SubmissionStatus(submission.status))


@router.get("/submissions/{submission_id}", response_model=SubmissionDetail)
async def get_submission(submission_id: uuid.UUID, user: CurrentUser, db: DbSession) -> SubmissionDetail:
    return await service.get_submission_detail(db, user, submission_id)


@router.get("/users/me/submissions", response_model=Page[SubmissionSummary])
async def my_submissions(
    user: CurrentUser,
    db: DbSession,
    params: PageParamsDep,
    problem: Annotated[str | None, Query(max_length=80, pattern=SLUG_PATTERN, description="Problem slug")] = None,
    verdict: Verdict | None = None,
    language: Annotated[str | None, Query(pattern=LANGUAGE_PATTERN)] = None,
    status: SubmissionStatus | None = None,
) -> Page[SubmissionSummary]:
    items, total = await service.list_submissions(
        db, user, params, problem_slug=problem, verdict=verdict, language=language, status=status
    )
    return Page.build(items, total, params)


@router.post("/run", response_model=RunQueued, status_code=status.HTTP_202_ACCEPTED)
async def run_code(
    data: RunCreate,
    request: Request,
    user: CurrentUser,
    db: DbSession,
    redis: RedisDep,
    queue: QueueDep,
    settings: SettingsDep,
) -> RunQueued:
    """Runs the code against the problem's PUBLIC examples, or against custom input. Never touches hidden tests."""
    await get_rate_limiter(request).enforce("run", str(user.id), settings.rate_limit_run)
    run_id = await service.create_run(db, redis, queue, settings, user, data)
    return RunQueued(id=run_id)


@router.get("/run/{run_id}", response_model=RunOut)
async def get_run(run_id: str, user: CurrentUser, redis: RedisDep) -> RunOut:
    return await service.get_run(redis, user, run_id)


@router.post("/ws/ticket", response_model=WsTicket)
async def ws_ticket(user: CurrentUser, redis: RedisDep, settings: SettingsDep) -> WsTicket:
    """A single-use, short-lived ticket for `/api/ws?ticket=...` (browsers cannot send an Authorization header)."""
    ticket = await events.issue_ticket(redis, user.id, settings.ws_ticket_ttl)
    return WsTicket(ticket=ticket, expires_in=settings.ws_ticket_ttl)


# --- WebSocket ---------------------------------------------------------------------------------------------------

WS_POLICY_VIOLATION = 1008


async def _forward_events(websocket: WebSocket, pubsub, deadline: float) -> None:
    while time.monotonic() < deadline:
        message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
        if message is not None and message.get("type") == "message":
            data = message["data"]
            await websocket.send_text(data.decode() if isinstance(data, bytes) else data)


async def _wait_for_disconnect(websocket: WebSocket) -> None:
    """Clients send nothing we care about; reading is how a closed connection is noticed."""
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            return


@ws_router.websocket("/api/ws")
async def event_socket(websocket: WebSocket, ticket: Annotated[str, Query(max_length=100)] = "") -> None:
    app = websocket.app
    settings = app.state.settings
    origin = websocket.headers.get("origin")
    if origin is not None and origin.rstrip("/") not in settings.allowed_origins:
        await websocket.close(code=WS_POLICY_VIOLATION)
        return
    user_id = await events.redeem_ticket(app.state.redis, ticket)
    if user_id is None:
        await websocket.close(code=WS_POLICY_VIOLATION)
        return

    await websocket.accept()
    pubsub = app.state.redis.pubsub()
    try:
        await pubsub.subscribe(events.user_channel(user_id))
        # A socket lives no longer than an access token: the client then needs a fresh ticket, which needs a valid
        # session, so a revoked session cannot keep receiving events indefinitely.
        deadline = time.monotonic() + settings.jwt_access_expire
        tasks = {
            asyncio.ensure_future(_forward_events(websocket, pubsub, deadline)),
            asyncio.ensure_future(_wait_for_disconnect(websocket)),
        }
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            task.result()  # surfaces a real error; a clean disconnect returns None
    except (WebSocketDisconnect, RedisError, RuntimeError):
        pass  # the peer went away, or Redis did: the client reconnects and polls in the meantime
    finally:
        with contextlib.suppress(Exception):
            await pubsub.unsubscribe()
            await pubsub.aclose()
        with contextlib.suppress(RuntimeError):
            await websocket.close()
