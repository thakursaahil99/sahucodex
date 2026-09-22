"""Public problem API: visibility, secrecy of hidden tests, filters, search, editorial gating, caching."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.conftest import TEST_DATABASE_URL, bearer, create_user, login, make_client, signed_in
from tests.problems_helpers import (
    HIDDEN_ANSWER,
    HIDDEN_SENTINEL,
    add_tags,
    admin_session,
    insert_problem,
    payload,
    set_progress,
)

ON_POSTGRES = bool(TEST_DATABASE_URL and TEST_DATABASE_URL.startswith("postgres"))


# --- Visibility ---------------------------------------------------------------------------------


async def test_only_published_non_archived_problems_are_public(app, client: AsyncClient):
    await insert_problem(app, "visible")
    await insert_problem(app, "draft", published=False)
    await insert_problem(app, "archived", archived=True)

    listing = (await client.get("/api/problems")).json()
    assert [item["slug"] for item in listing["items"]] == ["visible"]
    assert listing["total"] == 1

    assert (await client.get("/api/problems/visible")).status_code == 200
    for hidden in ("draft", "archived", "does-not-exist"):
        response = await client.get(f"/api/problems/{hidden}")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "PROBLEM_NOT_FOUND"


async def test_hidden_test_cases_never_appear_in_any_public_response(app, client: AsyncClient):
    await add_tags(app, "Array")
    await insert_problem(app, "secretive", tags=("array",), hints=("first hint",))

    async with signed_in(app, username="learner") as (member, headers), admin_session(app) as (admin, admin_headers):
        responses = []
        for who, hdrs in ((client, {}), (member, headers), (admin, admin_headers)):
            for path in (
                "/api/problems",
                "/api/problems?q=secret",
                "/api/problems/secretive",
                "/api/problems/secretive/hints/1",
                "/api/tags",
                "/api/languages",
            ):
                responses.append(await who.get(path, headers=hdrs))
    for response in responses:
        assert response.status_code == 200, response.url
        assert HIDDEN_SENTINEL not in response.text
        assert HIDDEN_ANSWER not in response.text
        assert "expected_output" not in response.text


async def test_detail_exposes_examples_but_not_hints_or_editorial(app, client: AsyncClient):
    await insert_problem(app, "shape", hints=("h1", "h2"))
    body = (await client.get("/api/problems/shape")).json()
    assert body["examples"] == [{"input": "1\n", "output": "2\n", "explanation": "one plus one"}]
    assert body["hint_count"] == 2
    assert "hints" not in body
    assert body["editorial"] is None and body["solution_unlocked"] is False
    assert body["starter_code"] == {"python": "pass\n"}


async def test_hints_are_revealed_one_at_a_time(app, client: AsyncClient):
    await insert_problem(app, "hinted", hints=("first", "second"))
    one = (await client.get("/api/problems/hinted/hints/1")).json()
    assert one == {"index": 1, "total": 2, "hint": "first"}
    assert (await client.get("/api/problems/hinted/hints/2")).json()["hint"] == "second"
    for bad in (0, 3, -1):
        assert (await client.get(f"/api/problems/hinted/hints/{bad}")).status_code == 404
    assert (await client.get("/api/problems/nope/hints/1")).status_code == 404


# --- Editorial gating ---------------------------------------------------------------------------


async def test_editorial_unlocks_only_after_solving_or_for_admins(app, client: AsyncClient):
    problem_id = await insert_problem(app, "guarded", editorial="THE-SECRET-EDITORIAL")
    async with signed_in(app, username="learner") as (member, headers):
        before = (await member.get("/api/problems/guarded", headers=headers)).json()
        assert before["editorial"] is None and before["solution_unlocked"] is False

        await set_progress(app, "learner", problem_id, "ATTEMPTED")
        attempted = (await member.get("/api/problems/guarded", headers=headers)).json()
        assert attempted["status"] == "ATTEMPTED" and attempted["editorial"] is None

        await set_progress_solved(app, "learner", problem_id)
        after = (await member.get("/api/problems/guarded", headers=headers)).json()
        assert after["status"] == "SOLVED"
        assert after["solution_unlocked"] is True
        assert after["editorial"] == "THE-SECRET-EDITORIAL"
        assert after["expected_time_complexity"] == "O(n)"

    async with admin_session(app) as (admin, admin_headers):
        seen = (await admin.get("/api/problems/guarded", headers=admin_headers)).json()
        assert seen["editorial"] == "THE-SECRET-EDITORIAL"
    assert "THE-SECRET-EDITORIAL" not in (await client.get("/api/problems/guarded")).text


async def set_progress_solved(app, username, problem_id):
    from sqlalchemy import select, update

    from app.modules.problems.models import UserProblemProgress
    from app.modules.users.models import User

    async with app.state.sessionmaker() as db:
        user_id = await db.scalar(select(User.id).where(User.username == username))
        await db.execute(
            update(UserProblemProgress)
            .where(UserProblemProgress.user_id == user_id, UserProblemProgress.problem_id == problem_id)
            .values(status="SOLVED")
        )
        await db.commit()


# --- Listing: pagination, filters, sorting ------------------------------------------------------


async def _seed_catalogue(app):
    await add_tags(app, "Array", "Graph", "Dynamic Programming")
    await insert_problem(
        app, "sum-pairs", title="Sum Pairs", difficulty="EASY", tags=("array",), total=100, accepted=80
    )
    await insert_problem(
        app, "island-count", title="Island Count", difficulty="MEDIUM", tags=("graph",), total=100, accepted=40
    )
    await insert_problem(
        app,
        "min-coins",
        title="Fewest Coins",
        difficulty="MEDIUM",
        tags=("dynamic-programming", "array"),
        total=50,
        accepted=10,
    )
    await insert_problem(
        app, "cheapest-route", title="Cheapest Route", difficulty="HARD", tags=("graph",), total=10, accepted=1
    )
    await insert_problem(
        app, "fresh-problem", title="Fresh Problem", difficulty="HARD", tags=("array",)
    )  # no submissions


async def test_pagination_reports_totals_and_bounds_the_page_size(app, client: AsyncClient):
    await _seed_catalogue(app)
    page1 = (await client.get("/api/problems?limit=2&page=1&sort=title")).json()
    page3 = (await client.get("/api/problems?limit=2&page=3&sort=title")).json()
    assert (page1["total"], page1["pages"], len(page1["items"])) == (5, 3, 2)
    assert len(page3["items"]) == 1
    assert (await client.get("/api/problems?limit=101")).status_code == 422
    assert (await client.get("/api/problems?page=0")).status_code == 422


async def test_filter_by_difficulty_and_tags(app, client: AsyncClient):
    await _seed_catalogue(app)

    async def slugs(query: str) -> set[str]:
        return {item["slug"] for item in (await client.get(f"/api/problems?{query}")).json()["items"]}

    assert await slugs("difficulty=HARD") == {"cheapest-route", "fresh-problem"}
    assert await slugs("difficulty=EASY&difficulty=HARD") == {"sum-pairs", "cheapest-route", "fresh-problem"}
    assert await slugs("tag=graph") == {"island-count", "cheapest-route"}
    assert await slugs("tag=graph&tag=dynamic-programming") == {"island-count", "cheapest-route", "min-coins"}  # ANY
    assert await slugs("difficulty=MEDIUM&tag=array") == {"min-coins"}
    assert (await client.get("/api/problems?difficulty=IMPOSSIBLE")).status_code == 422


async def test_filter_by_acceptance_rate_ignores_problems_without_submissions(app, client: AsyncClient):
    await _seed_catalogue(app)

    async def slugs(query: str) -> set[str]:
        return {item["slug"] for item in (await client.get(f"/api/problems?{query}")).json()["items"]}

    assert await slugs("min_acceptance=50") == {"sum-pairs"}
    assert await slugs("max_acceptance=40") == {"island-count", "min-coins", "cheapest-route"}
    assert await slugs("min_acceptance=10&max_acceptance=40") == {"island-count", "min-coins", "cheapest-route"}
    assert (await client.get("/api/problems?min_acceptance=101")).status_code == 422

    body = (await client.get("/api/problems?sort=acceptance")).json()["items"]
    assert [i["slug"] for i in body][:2] == ["sum-pairs", "island-count"]
    assert body[-1]["slug"] == "fresh-problem" and body[-1]["acceptance_rate"] is None  # NULLs sort last
    assert next(i for i in body if i["slug"] == "sum-pairs")["acceptance_rate"] == 80.0


async def test_sorting_by_difficulty_and_title(app, client: AsyncClient):
    await _seed_catalogue(app)
    by_difficulty = [i["difficulty"] for i in (await client.get("/api/problems?sort=difficulty")).json()["items"]]
    assert by_difficulty == ["EASY", "MEDIUM", "MEDIUM", "HARD", "HARD"]
    titles = [i["title"] for i in (await client.get("/api/problems?sort=title")).json()["items"]]
    assert titles == sorted(titles, key=str.lower)
    assert (await client.get("/api/problems?sort=bogus")).status_code == 422


async def test_status_filter_needs_sign_in_and_uses_real_progress(app, client: AsyncClient):
    await _seed_catalogue(app)
    assert (await client.get("/api/problems?status=solved")).status_code == 401

    async with signed_in(app, username="learner") as (member, headers):
        ids = {i["slug"]: i for i in (await member.get("/api/problems", headers=headers)).json()["items"]}
        from sqlalchemy import select

        from app.modules.problems.models import Problem

        async with app.state.sessionmaker() as db:
            pid = {row.slug: row.id for row in await db.scalars(select(Problem))}
        await set_progress(app, "learner", pid["sum-pairs"], "SOLVED")
        await set_progress(app, "learner", pid["island-count"], "ATTEMPTED")
        assert all(item["status"] is None for item in ids.values())

        async def slugs(query: str) -> set[str]:
            return {i["slug"] for i in (await member.get(f"/api/problems?{query}", headers=headers)).json()["items"]}

        assert await slugs("status=solved") == {"sum-pairs"}
        assert await slugs("status=attempted") == {"island-count"}
        assert await slugs("status=unsolved") == {"island-count", "min-coins", "cheapest-route", "fresh-problem"}

        with_status = {
            i["slug"]: i["status"] for i in (await member.get("/api/problems", headers=headers)).json()["items"]
        }
        assert with_status["sum-pairs"] == "SOLVED" and with_status["island-count"] == "ATTEMPTED"

    # Someone else's progress never leaks into another user's view.
    async with signed_in(app, username="other") as (other, other_headers):
        assert (await other.get("/api/problems?status=solved", headers=other_headers)).json()["total"] == 0


# --- Search -------------------------------------------------------------------------------------


async def test_search_matches_title_description_and_tags(app, client: AsyncClient):
    await add_tags(app, "Sliding Window", "Graph")
    await insert_problem(app, "longest-stretch", title="Longest Fresh Stretch", tags=("sliding-window",))
    await insert_problem(
        app, "moon-mail", title="Moon Mail", description="Deliver parcels between lunar stations.", tags=("graph",)
    )
    await insert_problem(app, "plain", title="Plain Thing")

    async def slugs(q: str) -> set[str]:
        return {i["slug"] for i in (await client.get("/api/problems", params={"q": q})).json()["items"]}

    assert await slugs("stretch") == {"longest-stretch"}  # title
    assert await slugs("lunar") == {"moon-mail"}  # description
    assert await slugs("sliding") == {"longest-stretch"}  # tag name
    assert await slugs("zzzz-no-match") == set()


async def test_search_treats_wildcards_and_sql_as_plain_text(app, client: AsyncClient):
    await insert_problem(app, "alpha", title="Alpha")
    for nasty in ("%", "_", "'; DROP TABLE problems; --", '"unbalanced', "a AND", "\\"):
        response = await client.get("/api/problems", params={"q": nasty})
        assert response.status_code == 200, nasty
        assert response.json()["total"] == 0, nasty
    assert (await client.get("/api/problems")).json()["total"] == 1  # table still there


@pytest.mark.skipif(not ON_POSTGRES, reason="full-text search needs PostgreSQL (TEST_DATABASE_URL)")
async def test_postgres_full_text_search_stems_and_ranks_title_above_description(app, client: AsyncClient):
    await insert_problem(app, "in-description", title="Coin Machine", description="Walk through the graphs in order.")
    await insert_problem(app, "in-title", title="Graph Traversal", description="Visit every node once.")
    await insert_problem(app, "unrelated", title="Bit Tricks", description="Flip some bits.")

    body = (await client.get("/api/problems", params={"q": "graph", "sort": "relevance"})).json()
    assert [i["slug"] for i in body["items"]] == ["in-title", "in-description"]  # stemmed: "graphs" matches "graph"

    quoted = (await client.get("/api/problems", params={"q": '"visit every"'})).json()
    assert [i["slug"] for i in quoted["items"]] == ["in-title"]  # websearch phrase syntax


# --- Reference data & caching -------------------------------------------------------------------


async def test_languages_and_tag_counts(app, client: AsyncClient):
    await add_tags(app, "Array", "Graph")
    await insert_problem(app, "one", tags=("array",))
    await insert_problem(app, "two", tags=("array",))
    await insert_problem(app, "hidden-draft", tags=("array", "graph"), published=False)

    languages = (await client.get("/api/languages")).json()
    assert [lang["key"] for lang in languages] == [
        "python",
        "cpp",
        "javascript",
        "c",
        "java",
        "csharp",
        "go",
        "rust",
        "typescript",
        "php",
    ]

    counts = {t["slug"]: t["problem_count"] for t in (await client.get("/api/tags")).json()}
    assert counts == {"array": 2, "graph": 0}  # drafts are not counted


async def test_detail_is_cached_and_invalidated_by_admin_changes(app, client: AsyncClient):
    await add_tags(app, "Array")
    async with admin_session(app) as (admin, headers):
        created = (await admin.post("/api/admin/problems", json=payload(), headers=headers)).json()
        assert (await admin.post(f"/api/admin/problems/{created['id']}/publish", headers=headers)).status_code == 200

        assert (await client.get("/api/problems/harbor-cranes")).json()["title"] == "Harbor Cranes"
        assert await app.state.redis.exists("cache:problem:detail:harbor-cranes") == 1

        renamed = payload(title="Harbor Cranes Reloaded")
        assert (
            await admin.put(f"/api/admin/problems/{created['id']}", json=renamed, headers=headers)
        ).status_code == 200
        assert await app.state.redis.exists("cache:problem:detail:harbor-cranes") == 0  # invalidated
        assert (await client.get("/api/problems/harbor-cranes")).json()["title"] == "Harbor Cranes Reloaded"

        # Archiving takes effect immediately, not when a cache entry expires.
        await client.get("/api/problems/harbor-cranes")
        assert (await admin.post(f"/api/admin/problems/{created['id']}/archive", headers=headers)).status_code == 200
        assert (await client.get("/api/problems/harbor-cranes")).status_code == 404
        assert (await admin.post(f"/api/admin/problems/{created['id']}/restore", headers=headers)).status_code == 200
        assert (await client.get("/api/problems/harbor-cranes")).status_code == 200


async def test_problem_pages_still_work_when_redis_is_down(build_app):
    from redis.exceptions import ConnectionError as RedisConnectionError

    class Broken:
        """Every Redis call fails: caching and rate limiting must degrade, not error."""

        def pipeline(self, *a, **k):
            raise RedisConnectionError("down")

        def __getattr__(self, name):
            async def fail(*a, **k):
                raise RedisConnectionError("down")

            return fail

        async def aclose(self):  # used on shutdown
            return None

    app = await build_app(redis=Broken())
    await insert_problem(app, "resilient")
    async with make_client(app) as anon:
        response = await anon.get("/api/problems/resilient")
        assert response.status_code == 200
        assert (await anon.get("/api/problems")).status_code == 200


async def test_expired_token_on_a_public_endpoint_is_rejected_not_ignored(app, client: AsyncClient):
    """A client that sends a stale token must be told to refresh, not silently served as anonymous."""
    await insert_problem(app, "p")
    response = await client.get("/api/problems", headers=bearer("not.a.real.token"))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "TOKEN_INVALID"


async def test_signed_in_users_get_personal_status_on_the_list(app, client: AsyncClient):
    problem_id = await insert_problem(app, "tracked")
    await create_user(app, email="who@example.com", username="who")
    await set_progress(app, "who", problem_id, "SOLVED")
    tokens = await login(client, "who@example.com")
    body = (await client.get("/api/problems", headers=bearer(tokens["access_token"]))).json()
    assert body["items"][0]["status"] == "SOLVED"
    assert (await client.get("/api/problems")).json()["items"][0]["status"] is None
