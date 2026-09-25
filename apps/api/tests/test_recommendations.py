"""Personalised "what to solve next" (Phase 8): content-based on the caller's own tag history and difficulty
progression — no other user's data is ever consulted."""

from __future__ import annotations

import pytest

from tests.conftest import bearer, create_user, login, make_client
from tests.problems_helpers import add_tags, insert_problem, set_progress

pytestmark = pytest.mark.anyio


async def test_requires_auth(app, client) -> None:
    r = await client.get("/api/recommendations")
    assert r.status_code == 401


async def test_cold_start_prefers_easy_highest_acceptance(app, client) -> None:
    """No solves yet -> the platform's most-accepted EASY problems, not an arbitrary order."""
    await insert_problem(app, "easy-low-acceptance", difficulty="EASY", total=100, accepted=10)
    await insert_problem(app, "easy-high-acceptance", difficulty="EASY", total=100, accepted=90)
    await insert_problem(app, "hard-one", difficulty="HARD", total=100, accepted=90)

    await create_user(app, email="ada@example.com", username="ada")
    async with make_client(app) as anon:
        tokens = await login(anon, "ada@example.com")
    headers = bearer(tokens["access_token"])

    r = await client.get("/api/recommendations", headers=headers)
    assert r.status_code == 200
    slugs = [item["slug"] for item in r.json()]
    assert slugs[0] == "easy-high-acceptance"
    assert slugs[1] == "easy-low-acceptance"
    assert "hard-one" in slugs  # still present, just ranked behind both EASY problems


async def test_excludes_solved_and_attempted_problems(app, client) -> None:
    tags = await add_tags(app, "array")
    solved_id = await insert_problem(app, "already-solved", difficulty="EASY", tags=("array",))
    attempted_id = await insert_problem(app, "already-attempted", difficulty="EASY", tags=("array",))
    fresh_id = await insert_problem(app, "still-fresh", difficulty="EASY", tags=("array",))
    assert tags  # sanity: the tag exists

    await create_user(app, email="bob@example.com", username="bob")
    await set_progress(app, "bob", solved_id, "SOLVED")
    await set_progress(app, "bob", attempted_id, "ATTEMPTED")

    async with make_client(app) as anon:
        tokens = await login(anon, "bob@example.com")
    headers = bearer(tokens["access_token"])

    r = await client.get("/api/recommendations", headers=headers)
    slugs = [item["slug"] for item in r.json()]
    assert slugs == ["still-fresh"]
    assert fresh_id  # sanity


async def test_ranks_by_shared_tags_with_solved_history(app, client) -> None:
    await add_tags(app, "array", "graph")
    solved = await insert_problem(app, "solved-array-problem", difficulty="EASY", tags=("array",))
    array_match = await insert_problem(app, "another-array-problem", difficulty="EASY", tags=("array",))
    graph_only = await insert_problem(app, "unrelated-graph-problem", difficulty="EASY", tags=("graph",))

    await create_user(app, email="cleo@example.com", username="cleo")
    await set_progress(app, "cleo", solved, "SOLVED")

    async with make_client(app) as anon:
        tokens = await login(anon, "cleo@example.com")
    headers = bearer(tokens["access_token"])

    r = await client.get("/api/recommendations", headers=headers)
    slugs = [item["slug"] for item in r.json()]
    assert slugs.index("another-array-problem") < slugs.index("unrelated-graph-problem")
    assert array_match and graph_only  # sanity


async def test_target_difficulty_steps_up_from_most_solved(app, client) -> None:
    """Mostly solving EASY problems should surface MEDIUM ones ahead of HARD ones, all else equal."""
    await insert_problem(app, "solved-easy-1", difficulty="EASY")
    solved_2 = await insert_problem(app, "solved-easy-2", difficulty="EASY")
    await insert_problem(app, "candidate-medium", difficulty="MEDIUM")
    await insert_problem(app, "candidate-hard", difficulty="HARD")

    await create_user(app, email="dave@example.com", username="dave")
    solved_1_id = await insert_problem(app, "solved-easy-3", difficulty="EASY")
    for pid in (solved_1_id, solved_2):
        await set_progress(app, "dave", pid, "SOLVED")

    async with make_client(app) as anon:
        tokens = await login(anon, "dave@example.com")
    headers = bearer(tokens["access_token"])

    r = await client.get("/api/recommendations", headers=headers)
    slugs = [item["slug"] for item in r.json()]
    assert slugs.index("candidate-medium") < slugs.index("candidate-hard")
