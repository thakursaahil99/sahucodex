"""Discussions, comments, voting, reporting, and moderation."""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from httpx import AsyncClient

from app.modules.users.models import RoleName
from tests.conftest import bearer, login, make_client, signed_in
from tests.problems_helpers import admin_session, insert_problem

pytestmark = pytest.mark.anyio


async def _new_discussion(app, client: AsyncClient, headers: dict, slug: str) -> str:
    r = await client.post(
        f"/api/problems/{slug}/discussions", json={"title": "How to approach this?", "body": "Stuck on part 2."}, headers=headers
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


@asynccontextmanager
async def _re_login(app, *, username: str):
    """Like `signed_in`, but for a user this test already created earlier — `signed_in` always creates a fresh
    account, so reusing it for the same username twice in one test is a duplicate-user error."""
    async with make_client(app) as client:
        tokens = await login(client, f"{username}@example.com")
        yield client, bearer(tokens["access_token"])


async def test_full_discussion_lifecycle(app) -> None:
    slug_id = await insert_problem(app, "two-sum")
    async with signed_in(app, username="alice") as (client, headers):
        r = await client.get("/api/problems/two-sum/discussions")
        assert r.status_code == 200 and r.json() == []

        discussion_id = await _new_discussion(app, client, headers, "two-sum")

        listing = await client.get("/api/problems/two-sum/discussions")
        assert listing.status_code == 200
        item = listing.json()[0]
        assert item["title"] == "How to approach this?" and item["author"]["username"] == "alice"
        assert item["vote_score"] == 0 and item["comment_count"] == 0

        detail = await client.get(f"/api/discussions/{discussion_id}")
        assert detail.status_code == 200
        body = detail.json()
        assert body["problem_slug"] == "two-sum" and body["body"] == "Stuck on part 2." and body["comments"] == []


async def test_comment_updates_thread_count_and_notifies_the_author(app) -> None:
    await insert_problem(app, "two-sum")
    async with signed_in(app, username="alice") as (alice, alice_headers):
        discussion_id = await _new_discussion(app, alice, alice_headers, "two-sum")

    async with signed_in(app, username="bob") as (bob, bob_headers):
        r = await bob.post(f"/api/discussions/{discussion_id}/comments", json={"body": "Try two pointers."}, headers=bob_headers)
        assert r.status_code == 201, r.text
        assert r.json()["author"]["username"] == "bob"

    async with _re_login(app, username="alice") as (alice, alice_headers):
        detail = await alice.get(f"/api/discussions/{discussion_id}")
        assert len(detail.json()["comments"]) == 1
        assert detail.json()["comments"][0]["body"] == "Try two pointers."

        notifications = await alice.get("/api/notifications", headers=alice_headers)
        assert notifications.status_code == 200
        assert len(notifications.json()) == 1
        note = notifications.json()[0]
        assert note["type"] == "DISCUSSION_REPLY" and note["data"]["actor_username"] == "bob" and note["read"] is False

        unread = await alice.get("/api/notifications/unread-count", headers=alice_headers)
        assert unread.json() == {"count": 1}


async def test_self_reply_does_not_notify_yourself(app) -> None:
    await insert_problem(app, "two-sum")
    async with signed_in(app, username="alice") as (client, headers):
        discussion_id = await _new_discussion(app, client, headers, "two-sum")
        await client.post(f"/api/discussions/{discussion_id}/comments", json={"body": "Update: solved it."}, headers=headers)
        unread = await client.get("/api/notifications/unread-count", headers=headers)
        assert unread.json() == {"count": 0}


async def test_marking_notifications_read(app) -> None:
    await insert_problem(app, "two-sum")
    async with signed_in(app, username="alice") as (alice, alice_headers):
        discussion_id = await _new_discussion(app, alice, alice_headers, "two-sum")

    async with signed_in(app, username="bob") as (bob, bob_headers):
        await bob.post(f"/api/discussions/{discussion_id}/comments", json={"body": "hi"}, headers=bob_headers)

    async with _re_login(app, username="alice") as (alice, alice_headers):
        notes = (await alice.get("/api/notifications", headers=alice_headers)).json()
        note_id = notes[0]["id"]
        r = await alice.post(f"/api/notifications/{note_id}/read", headers=alice_headers)
        assert r.status_code == 204
        assert (await alice.get("/api/notifications/unread-count", headers=alice_headers)).json() == {"count": 0}

        # Reading someone else's notification is a 404, not a leak of whether it exists.
        async with signed_in(app, username="carol") as (carol, carol_headers):
            r = await carol.post(f"/api/notifications/{note_id}/read", headers=carol_headers)
            assert r.status_code == 404


async def test_mark_all_read(app) -> None:
    await insert_problem(app, "two-sum")
    async with signed_in(app, username="alice") as (alice, alice_headers):
        d1 = await _new_discussion(app, alice, alice_headers, "two-sum")
        d2 = await _new_discussion(app, alice, alice_headers, "two-sum")

    async with signed_in(app, username="bob") as (bob, bob_headers):
        await bob.post(f"/api/discussions/{d1}/comments", json={"body": "a"}, headers=bob_headers)
        await bob.post(f"/api/discussions/{d2}/comments", json={"body": "b"}, headers=bob_headers)

    async with _re_login(app, username="alice") as (alice, alice_headers):
        assert (await alice.get("/api/notifications/unread-count", headers=alice_headers)).json() == {"count": 2}
        r = await alice.post("/api/notifications/read-all", headers=alice_headers)
        assert r.status_code == 204
        assert (await alice.get("/api/notifications/unread-count", headers=alice_headers)).json() == {"count": 0}


async def test_voting_a_discussion_up_then_down_then_removing_the_vote(app) -> None:
    await insert_problem(app, "two-sum")
    async with signed_in(app, username="alice") as (alice, alice_headers):
        discussion_id = await _new_discussion(app, alice, alice_headers, "two-sum")

    async with signed_in(app, username="bob") as (bob, bob_headers):
        r = await bob.put(f"/api/community/discussion/{discussion_id}/vote", json={"value": 1}, headers=bob_headers)
        assert r.status_code == 204
        detail = (await bob.get(f"/api/discussions/{discussion_id}", headers=bob_headers)).json()
        assert detail["vote_score"] == 1 and detail["my_vote"] == 1

        # Switching the same user's vote from +1 to -1 nets to -1, not -2.
        r = await bob.put(f"/api/community/discussion/{discussion_id}/vote", json={"value": -1}, headers=bob_headers)
        assert r.status_code == 204
        detail = (await bob.get(f"/api/discussions/{discussion_id}", headers=bob_headers)).json()
        assert detail["vote_score"] == -1 and detail["my_vote"] == -1

        r = await bob.delete(f"/api/community/discussion/{discussion_id}/vote", headers=bob_headers)
        assert r.status_code == 204
        detail = (await bob.get(f"/api/discussions/{discussion_id}", headers=bob_headers)).json()
        assert detail["vote_score"] == 0 and detail["my_vote"] == 0


async def test_voting_a_comment(app) -> None:
    await insert_problem(app, "two-sum")
    async with signed_in(app, username="alice") as (alice, alice_headers):
        discussion_id = await _new_discussion(app, alice, alice_headers, "two-sum")
        comment = (
            await alice.post(f"/api/discussions/{discussion_id}/comments", json={"body": "x"}, headers=alice_headers)
        ).json()

    async with signed_in(app, username="bob") as (bob, bob_headers):
        await bob.put(f"/api/community/comment/{comment['id']}/vote", json={"value": 1}, headers=bob_headers)
        detail = (await bob.get(f"/api/discussions/{discussion_id}")).json()
        assert detail["comments"][0]["vote_score"] == 1


async def test_repeating_the_same_vote_is_a_noop(app) -> None:
    await insert_problem(app, "two-sum")
    async with signed_in(app, username="alice") as (alice, alice_headers):
        discussion_id = await _new_discussion(app, alice, alice_headers, "two-sum")

    async with signed_in(app, username="bob") as (bob, bob_headers):
        await bob.put(f"/api/community/discussion/{discussion_id}/vote", json={"value": 1}, headers=bob_headers)
        await bob.put(f"/api/community/discussion/{discussion_id}/vote", json={"value": 1}, headers=bob_headers)
        detail = (await bob.get(f"/api/discussions/{discussion_id}")).json()
        assert detail["vote_score"] == 1


async def test_report_a_discussion_and_moderator_resolves_it(app) -> None:
    await insert_problem(app, "two-sum")
    async with signed_in(app, username="alice") as (alice, alice_headers):
        discussion_id = await _new_discussion(app, alice, alice_headers, "two-sum")

    async with signed_in(app, username="bob") as (bob, bob_headers):
        r = await bob.post(
            f"/api/community/discussion/{discussion_id}/report", json={"reason": "spam"}, headers=bob_headers
        )
        assert r.status_code == 204

    async with signed_in(app, username="mod", roles=(RoleName.MODERATOR, RoleName.USER)) as (mod, mod_headers):
        reports = await mod.get("/api/moderation/reports", headers=mod_headers)
        assert reports.status_code == 200
        assert len(reports.json()) == 1
        report = reports.json()[0]
        assert report["status"] == "OPEN" and report["reason"] == "spam" and report["target_snippet"]

        r = await mod.post(
            f"/api/moderation/reports/{report['id']}/resolve", json={"action": "remove_content"}, headers=mod_headers
        )
        assert r.status_code == 204

        reports_after = (await mod.get("/api/moderation/reports?status=OPEN", headers=mod_headers)).json()
        assert reports_after == []

    async with _re_login(app, username="alice") as (alice, alice_headers):
        detail = (await alice.get(f"/api/discussions/{discussion_id}")).json()
        assert detail["removed"] is True and detail["body"] == "[removed by a moderator]"

        # The removal itself notified the author.
        notes = (await alice.get("/api/notifications", headers=alice_headers)).json()
        assert any(n["type"] == "CONTENT_REMOVED" for n in notes)


async def test_dismissing_a_report_does_not_remove_content(app) -> None:
    await insert_problem(app, "two-sum")
    async with signed_in(app, username="alice") as (alice, alice_headers):
        discussion_id = await _new_discussion(app, alice, alice_headers, "two-sum")

    async with signed_in(app, username="bob") as (bob, bob_headers):
        await bob.post(f"/api/community/discussion/{discussion_id}/report", json={"reason": "bad"}, headers=bob_headers)

    async with signed_in(app, username="mod", roles=(RoleName.MODERATOR, RoleName.USER)) as (mod, mod_headers):
        report_id = (await mod.get("/api/moderation/reports", headers=mod_headers)).json()[0]["id"]
        await mod.post(f"/api/moderation/reports/{report_id}/resolve", json={"action": "dismiss"}, headers=mod_headers)

    async with _re_login(app, username="alice") as (alice, _):
        detail = (await alice.get(f"/api/discussions/{discussion_id}")).json()
        assert detail["removed"] is False


async def test_resolving_an_already_resolved_report_is_a_conflict(app) -> None:
    await insert_problem(app, "two-sum")
    async with signed_in(app, username="alice") as (alice, alice_headers):
        discussion_id = await _new_discussion(app, alice, alice_headers, "two-sum")
    async with signed_in(app, username="bob") as (bob, bob_headers):
        await bob.post(f"/api/community/discussion/{discussion_id}/report", json={"reason": "x"}, headers=bob_headers)

    async with signed_in(app, username="mod", roles=(RoleName.MODERATOR, RoleName.USER)) as (mod, mod_headers):
        report_id = (await mod.get("/api/moderation/reports", headers=mod_headers)).json()[0]["id"]
        await mod.post(f"/api/moderation/reports/{report_id}/resolve", json={"action": "dismiss"}, headers=mod_headers)
        r = await mod.post(f"/api/moderation/reports/{report_id}/resolve", json={"action": "dismiss"}, headers=mod_headers)
        assert r.status_code == 409


async def test_moderation_requires_moderator_role(app) -> None:
    async with signed_in(app, username="plain") as (client, headers):
        r = await client.get("/api/moderation/reports", headers=headers)
        assert r.status_code == 403


async def test_admin_can_also_moderate(app) -> None:
    async with admin_session(app) as (client, headers):
        r = await client.get("/api/moderation/reports", headers=headers)
        assert r.status_code == 200


async def test_discussion_on_unknown_or_draft_problem_is_404(app) -> None:
    await insert_problem(app, "hidden-one", published=False)
    async with signed_in(app, username="alice") as (client, headers):
        r = await client.get("/api/problems/no-such-problem/discussions")
        assert r.status_code == 404
        r = await client.post(
            "/api/problems/hidden-one/discussions", json={"title": "t", "body": "b"}, headers=headers
        )
        assert r.status_code == 404


async def test_removed_comment_body_is_hidden_but_still_present(app) -> None:
    await insert_problem(app, "two-sum")
    async with signed_in(app, username="alice") as (alice, alice_headers):
        discussion_id = await _new_discussion(app, alice, alice_headers, "two-sum")
        comment = (
            await alice.post(f"/api/discussions/{discussion_id}/comments", json={"body": "secret sauce"}, headers=alice_headers)
        ).json()

    async with signed_in(app, username="bob") as (bob, bob_headers):
        await bob.post(f"/api/community/comment/{comment['id']}/report", json={"reason": "bad"}, headers=bob_headers)

    async with signed_in(app, username="mod", roles=(RoleName.MODERATOR, RoleName.USER)) as (mod, mod_headers):
        report_id = (await mod.get("/api/moderation/reports", headers=mod_headers)).json()[0]["id"]
        await mod.post(f"/api/moderation/reports/{report_id}/resolve", json={"action": "remove_content"}, headers=mod_headers)

    async with signed_in(app, username="dave") as (dave, _):
        detail = (await dave.get(f"/api/discussions/{discussion_id}")).json()
        removed_comment = next(c for c in detail["comments"] if c["id"] == comment["id"])
        assert removed_comment["removed"] is True and removed_comment["body"] == "[removed by a moderator]"


async def test_body_and_title_length_limits_are_enforced(app) -> None:
    await insert_problem(app, "two-sum")
    async with signed_in(app, username="alice") as (client, headers):
        r = await client.post(
            "/api/problems/two-sum/discussions", json={"title": "", "body": "x"}, headers=headers
        )
        assert r.status_code == 422
        r = await client.post(
            "/api/problems/two-sum/discussions", json={"title": "x" * 201, "body": "x"}, headers=headers
        )
        assert r.status_code == 422


async def test_recent_discussions_feed_spans_problems_newest_first(app) -> None:
    await insert_problem(app, "two-sum")
    await insert_problem(app, "three-sum")
    async with signed_in(app, username="alice") as (client, headers):
        first = await _new_discussion(app, client, headers, "two-sum")
        second = await _new_discussion(app, client, headers, "three-sum")

        r = await client.get("/api/discussions")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total"] == 2 and len(body["items"]) == 2
        # Newest first.
        assert [item["id"] for item in body["items"]] == [second, first]
        assert body["items"][0]["problem_slug"] == "three-sum"
        assert body["items"][0]["problem_title"] and body["items"][1]["problem_slug"] == "two-sum"


async def test_recent_discussions_feed_excludes_unpublished_problems(app) -> None:
    import uuid as _uuid

    from app.modules.community.models import Discussion
    from app.modules.problems.models import Problem

    await insert_problem(app, "two-sum")
    await insert_problem(app, "hidden-one", published=False)

    async with signed_in(app, username="alice") as (client, headers):
        await _new_discussion(app, client, headers, "two-sum")

        # Discussions can only be created under visible problems via the public endpoint (which 404s on a
        # hidden problem), so seed one directly to prove the feed's join-filter excludes it too, not just the
        # create-time check.
        async with app.state.sessionmaker() as db:
            hidden = (await db.execute(Problem.__table__.select().where(Problem.slug == "hidden-one"))).first()
            db.add(
                Discussion(
                    id=_uuid.uuid4(),
                    problem_id=hidden.id,
                    author_id=None,
                    title="Should not appear",
                    body="x",
                )
            )
            await db.commit()

        r = await client.get("/api/discussions")
        assert r.status_code == 200
        assert all(item["problem_slug"] != "hidden-one" for item in r.json()["items"])


async def test_recent_discussions_feed_is_paginated(app) -> None:
    await insert_problem(app, "two-sum")
    async with signed_in(app, username="alice") as (client, headers):
        for _ in range(3):
            await _new_discussion(app, client, headers, "two-sum")

        r = await client.get("/api/discussions?page=1&limit=2")
        body = r.json()
        assert body["total"] == 3 and len(body["items"]) == 2 and body["pages"] == 2

        r2 = await client.get("/api/discussions?page=2&limit=2")
        assert len(r2.json()["items"]) == 1


async def test_reporting_requires_auth(app) -> None:
    await insert_problem(app, "two-sum")
    async with signed_in(app, username="alice") as (alice, alice_headers):
        discussion_id = await _new_discussion(app, alice, alice_headers, "two-sum")

    async with make_client(app) as anon:
        r = await anon.post(f"/api/community/discussion/{discussion_id}/report", json={"reason": "x"})
        assert r.status_code == 401
        r = await anon.put(f"/api/community/discussion/{discussion_id}/vote", json={"value": 1})
        assert r.status_code == 401


async def test_moderator_can_lock_a_discussion_blocking_new_comments(app) -> None:
    await insert_problem(app, "two-sum")
    async with signed_in(app, username="alice") as (alice, alice_headers):
        discussion_id = await _new_discussion(app, alice, alice_headers, "two-sum")

    async with signed_in(app, username="mod", roles=(RoleName.MODERATOR, RoleName.USER)) as (mod, mod_headers):
        r = await mod.post(f"/api/moderation/discussions/{discussion_id}/lock", headers=mod_headers)
        assert r.status_code == 204

    async with _re_login(app, username="alice") as (alice, alice_headers):
        detail = (await alice.get(f"/api/discussions/{discussion_id}")).json()
        assert detail["locked"] is True

        r = await alice.post(f"/api/discussions/{discussion_id}/comments", json={"body": "still here?"}, headers=alice_headers)
        assert r.status_code == 409

    async with signed_in(app, username="mod2", roles=(RoleName.MODERATOR, RoleName.USER)) as (mod, mod_headers):
        r = await mod.post(f"/api/moderation/discussions/{discussion_id}/unlock", headers=mod_headers)
        assert r.status_code == 204

    async with _re_login(app, username="alice") as (alice, alice_headers):
        detail = (await alice.get(f"/api/discussions/{discussion_id}")).json()
        assert detail["locked"] is False
        r = await alice.post(f"/api/discussions/{discussion_id}/comments", json={"body": "back now"}, headers=alice_headers)
        assert r.status_code == 201


async def test_locking_a_discussion_requires_moderator_role(app) -> None:
    await insert_problem(app, "two-sum")
    async with signed_in(app, username="alice") as (alice, alice_headers):
        discussion_id = await _new_discussion(app, alice, alice_headers, "two-sum")
        r = await alice.post(f"/api/moderation/discussions/{discussion_id}/lock", headers=alice_headers)
        assert r.status_code == 403
