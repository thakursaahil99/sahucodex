"""The authenticated event socket. Sync tests: Starlette's TestClient owns the event loop and every Redis call is made
on it (via `portal.call`), so nothing crosses loops."""

from __future__ import annotations

import json
import time
import uuid

import fakeredis
import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import create_app
from app.modules.submissions import events
from tests.conftest import RecordingQueue, make_settings


@pytest.fixture
def stack():
    redis = fakeredis.FakeAsyncRedis(server=fakeredis.FakeServer(), decode_responses=True)
    app = create_app(make_settings(), redis_client=redis, job_queue=RecordingQueue())  # type: ignore[arg-type]
    with TestClient(app) as client:
        yield client, redis


def ticket_for(client: TestClient, redis, user_id: uuid.UUID) -> str:
    return client.portal.call(events.issue_ticket, redis, user_id, 30)  # type: ignore[union-attr]


def publish(client: TestClient, redis, user_id: uuid.UUID, kind: str = events.EVENT_COMPLETED, **data) -> None:
    client.portal.call(events.publish_event, redis, user_id, kind, data)  # type: ignore[union-attr]


def wait_until_subscribed(client: TestClient, redis, user_id: uuid.UUID) -> None:
    """The server subscribes just after accepting the socket; publishing earlier would be lost (pub/sub keeps nothing
    it received before a subscriber joins)."""
    channel = events.user_channel(user_id)
    for _ in range(200):
        counts = dict(client.portal.call(redis.pubsub_numsub, channel))  # type: ignore[union-attr]
        if counts.get(channel, 0) >= 1:
            return
        time.sleep(0.02)
    raise AssertionError("the socket never subscribed")


def deliver(client: TestClient, redis, user_id: uuid.UUID, socket, **data) -> dict:
    wait_until_subscribed(client, redis, user_id)
    publish(client, redis, user_id, **data)
    return socket.receive_json()


def test_a_valid_ticket_receives_that_users_events(stack) -> None:
    client, redis = stack
    me = uuid.uuid4()
    with client.websocket_connect(f"/api/ws?ticket={ticket_for(client, redis, me)}") as socket:
        message = deliver(client, redis, me, socket, submission_id="abc", verdict="ACCEPTED")
    assert message["type"] == "submission.completed"
    assert message["data"]["verdict"] == "ACCEPTED"
    assert message["data"]["submission_id"] == "abc"
    assert "ts" in message


def test_other_users_events_are_never_delivered(stack) -> None:
    client, redis = stack
    me, someone_else = uuid.uuid4(), uuid.uuid4()
    with client.websocket_connect(f"/api/ws?ticket={ticket_for(client, redis, me)}") as socket:
        for _ in range(3):
            publish(client, redis, someone_else, secret="not-for-me")
        message = deliver(client, redis, me, socket, mine=True)
    assert "not-for-me" not in json.dumps(message)
    assert message["data"]["mine"] is True


@pytest.mark.parametrize("ticket", ["", "nope", "x" * 43, "a" * 101])
def test_bad_tickets_are_refused(stack, ticket) -> None:
    client, _ = stack
    with pytest.raises(WebSocketDisconnect), client.websocket_connect(f"/api/ws?ticket={ticket}"):
        pass


def test_a_ticket_works_once(stack) -> None:
    client, redis = stack
    ticket = ticket_for(client, redis, uuid.uuid4())
    with client.websocket_connect(f"/api/ws?ticket={ticket}"):
        pass
    with pytest.raises(WebSocketDisconnect), client.websocket_connect(f"/api/ws?ticket={ticket}"):
        pass


def test_a_foreign_origin_is_refused_even_with_a_valid_ticket(stack) -> None:
    client, redis = stack
    ticket = ticket_for(client, redis, uuid.uuid4())
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect(f"/api/ws?ticket={ticket}", headers={"origin": "https://evil.example"}),
    ):
        pass
    # The origin check comes before redemption, so the refused attempt did not burn the legitimate holder's ticket.
    with client.websocket_connect(f"/api/ws?ticket={ticket}", headers={"origin": "http://localhost:3000"}):
        pass


def test_the_subscription_is_released_when_the_client_leaves(stack) -> None:
    client, redis = stack
    me = uuid.uuid4()
    channel = events.user_channel(me)
    with client.websocket_connect(f"/api/ws?ticket={ticket_for(client, redis, me)}") as socket:
        deliver(client, redis, me, socket)
    for _ in range(40):
        counts = dict(client.portal.call(redis.pubsub_numsub, channel))  # type: ignore[union-attr]
        if counts.get(channel, 0) == 0:
            return
        time.sleep(0.05)
    raise AssertionError("the Redis subscription leaked after the socket closed")
