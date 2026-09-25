"""RAG (Phase 8): semantic "similar problems" and search, backed by an in-process Qdrant (`:memory:`) and a
deterministic fake embedder — no real Ollama or Qdrant server needed, same hermetic-test philosophy as the rest of
this suite."""

from __future__ import annotations

import pytest

from tests.conftest import FakeAiProvider, FakeEmbeddingProvider, make_client, make_settings, signed_in
from tests.problems_helpers import add_tags, admin_session, insert_problem, payload

pytestmark = pytest.mark.anyio

# The RAG collection is fixed at 768 dimensions (nomic-embed-text's real output size — see
# app.modules.rag.service._VECTOR_SIZE), so every fake vector here must match that shape even though only the
# first couple of components actually vary between "directions" in these tests.
_DIM = 768


def _vec(*hot: int) -> list[float]:
    v = [0.0] * _DIM
    for i in hot:
        v[i] = 1.0
    return v


def _rag_settings():
    return make_settings(qdrant_url="http://unused:6333")


async def test_disabled_without_qdrant_url(build_app) -> None:
    app = await build_app(settings=make_settings())  # no QDRANT_URL -> rag_configured is False
    await insert_problem(app, "two-sum")
    async with make_client(app) as client:
        r = await client.get("/api/problems/two-sum/similar")
        assert r.status_code == 503
        assert r.json()["error"]["code"] == "RAG_UNAVAILABLE"


async def test_a_configured_but_unreachable_embedder_is_a_clean_503(build_app) -> None:
    app = await build_app(settings=_rag_settings(), embedding_provider=FakeEmbeddingProvider(down=True))
    await insert_problem(app, "two-sum")
    async with make_client(app) as client:
        r = await client.get("/api/problems/two-sum/similar")
        assert r.status_code == 503
        assert r.json()["error"]["code"] == "RAG_UNAVAILABLE"


async def test_admin_publish_indexes_the_problem_and_similar_finds_it(build_app) -> None:
    embedder = FakeEmbeddingProvider(vectors={"array": _vec(0), "graph": _vec(1)})
    app = await build_app(settings=_rag_settings(), embedding_provider=embedder)
    await add_tags(app, "array", "misc")

    async with admin_session(app) as (admin, headers):
        body = payload(
            slug="array-neighbour", title="Array Neighbour",
            description="A classic array traversal problem.", tags=["array"],
        )  # fmt: skip
        created = await admin.post("/api/admin/problems", json=body, headers=headers)
        assert created.status_code == 201, created.text
        problem_id = created.json()["id"]
        publish = await admin.post(f"/api/admin/problems/{problem_id}/publish", headers=headers)
        assert publish.status_code == 200, publish.text

        # A second, semantically-close (also "array") problem to be found as a neighbour.
        body2 = payload(
            slug="another-array-problem", title="Another Array Problem",
            description="Also an array problem, much like the other one.", tags=["array"],
        )  # fmt: skip
        created2 = await admin.post("/api/admin/problems", json=body2, headers=headers)
        await admin.post(f"/api/admin/problems/{created2.json()['id']}/publish", headers=headers)

        # And an unrelated ("graph") problem that should rank behind it. Tagged "misc" (not "array") so the tag
        # itself doesn't leak into the embedded text and spuriously match the "array" fake vector.
        body3 = payload(
            slug="a-graph-problem", title="A Graph Problem", description="A graph traversal problem instead.", tags=["misc"]
        )
        created3 = await admin.post("/api/admin/problems", json=body3, headers=headers)
        await admin.post(f"/api/admin/problems/{created3.json()['id']}/publish", headers=headers)

    async with make_client(app) as client:
        r = await client.get("/api/problems/array-neighbour/similar")
        assert r.status_code == 200, r.text
        slugs = [item["slug"] for item in r.json()]
        assert "array-neighbour" not in slugs  # a problem is never its own "similar" result
        assert slugs[0] == "another-array-problem"
        assert "a-graph-problem" in slugs
        assert slugs.index("another-array-problem") < slugs.index("a-graph-problem")


async def test_unpublishing_removes_it_from_similar_results(build_app) -> None:
    embedder = FakeEmbeddingProvider(vectors={"array": _vec(0)})
    app = await build_app(settings=_rag_settings(), embedding_provider=embedder)
    await add_tags(app, "array")

    async with admin_session(app) as (admin, headers):
        anchor = await admin.post(
            "/api/admin/problems",
            json=payload(slug="anchor", title="Anchor", description="An array problem for the tests.", tags=["array"]),
            headers=headers,
        )
        await admin.post(f"/api/admin/problems/{anchor.json()['id']}/publish", headers=headers)

        target = await admin.post(
            "/api/admin/problems",
            json=payload(slug="target", title="Target", description="Also an array problem here.", tags=["array"]),
            headers=headers,
        )
        target_id = target.json()["id"]
        await admin.post(f"/api/admin/problems/{target_id}/publish", headers=headers)

    async with make_client(app) as client:
        before = await client.get("/api/problems/anchor/similar")
        assert "target" in [item["slug"] for item in before.json()]

    async with admin_session(app, username="boss2") as (admin, headers):
        await admin.post(f"/api/admin/problems/{target_id}/unpublish", headers=headers)

    async with make_client(app) as client:
        after = await client.get("/api/problems/anchor/similar")
        assert "target" not in [item["slug"] for item in after.json()]


async def test_semantic_search_ranks_by_meaning_not_keyword(build_app) -> None:
    embedder = FakeEmbeddingProvider(vectors={"topological": _vec(0), "brute force": _vec(1)})
    app = await build_app(settings=_rag_settings(), embedding_provider=embedder)
    await add_tags(app, "misc")

    async with admin_session(app) as (admin, headers):
        close = await admin.post(
            "/api/admin/problems",
            json=payload(slug="dependency-order", title="Dependency Order", description="Uses a topological sort.", tags=["misc"]),
            headers=headers,
        )  # fmt: skip
        await admin.post(f"/api/admin/problems/{close.json()['id']}/publish", headers=headers)

        far = await admin.post(
            "/api/admin/problems",
            json=payload(slug="brute-search", title="Brute Search", description="Solved with brute force.", tags=["misc"]),
            headers=headers,
        )  # fmt: skip
        await admin.post(f"/api/admin/problems/{far.json()['id']}/publish", headers=headers)

    async with make_client(app) as client:
        r = await client.get("/api/search/semantic", params={"q": "topological sort ordering"})
        assert r.status_code == 200, r.text
        slugs = [item["slug"] for item in r.json()]
        assert slugs[0] == "dependency-order"


async def test_similar_requires_a_real_problem(build_app) -> None:
    app = await build_app(settings=_rag_settings(), embedding_provider=FakeEmbeddingProvider())
    async with make_client(app) as client:
        r = await client.get("/api/problems/no-such-problem/similar")
        assert r.status_code == 404


async def test_chat_with_no_attached_problem_gets_rag_context_in_its_system_prompt(build_app) -> None:
    """A chat message that isn't tied to any specific problem (see app.modules.ai.service._related_problems) should
    surface semantically related problems in the system prompt, so the model can point the learner at them by
    slug/title instead of inventing one."""
    embedder = FakeEmbeddingProvider(vectors={"two pointers": _vec(0)})
    chat_provider = FakeAiProvider(tokens=["ok"])
    app = await build_app(
        settings=make_settings(qdrant_url="http://unused:6333", ollama_model="test-model"),
        ai_provider=chat_provider,
        embedding_provider=embedder,
    )
    await add_tags(app, "two-pointers")

    async with admin_session(app) as (admin, headers):
        created = await admin.post(
            "/api/admin/problems",
            json=payload(
                slug="two-pointer-classic", title="Two Pointer Classic",
                description="A classic two pointers problem for arrays.", tags=["two-pointers"],
            ),
            headers=headers,
        )  # fmt: skip
        await admin.post(f"/api/admin/problems/{created.json()['id']}/publish", headers=headers)

    async with signed_in(app, username="ada") as (client, auth):
        response = await client.post(
            "/api/ai/conversations", json={"message": "How do I use two pointers to solve array problems?"}, headers=auth
        )
        assert response.status_code == 200, response.text

    system_prompt = str(chat_provider.chat_calls[0]["system"])
    assert "Two Pointer Classic" in system_prompt
    assert "two-pointer-classic" in system_prompt


async def test_chat_with_an_attached_problem_never_gets_rag_context(build_app) -> None:
    """When a problem is already attached, the model already has its full statement — RAG context would be noise,
    or worse, a distraction from the one problem the learner is actually asking about."""
    embedder = FakeEmbeddingProvider(vectors={"two pointers": _vec(0)})
    chat_provider = FakeAiProvider(tokens=["ok"])
    app = await build_app(
        settings=make_settings(qdrant_url="http://unused:6333", ollama_model="test-model"),
        ai_provider=chat_provider,
        embedding_provider=embedder,
    )
    await add_tags(app, "two-pointers")

    async with admin_session(app) as (admin, headers):
        created = await admin.post(
            "/api/admin/problems",
            json=payload(
                slug="two-pointer-classic", title="Two Pointer Classic",
                description="A classic two pointers problem for arrays.", tags=["two-pointers"],
            ),
            headers=headers,
        )  # fmt: skip
        await admin.post(f"/api/admin/problems/{created.json()['id']}/publish", headers=headers)

        target = await admin.post(
            "/api/admin/problems",
            json=payload(slug="two-sum", title="Two Sum", description="Find two numbers that add to a target.", tags=["two-pointers"]),
            headers=headers,
        )  # fmt: skip
        await admin.post(f"/api/admin/problems/{target.json()['id']}/publish", headers=headers)

    async with signed_in(app, username="ada") as (client, auth):
        response = await client.post(
            "/api/ai/conversations",
            json={"message": "How do I use two pointers here?", "problem_slug": "two-sum"},
            headers=auth,
        )
        assert response.status_code == 200, response.text

    system_prompt = str(chat_provider.chat_calls[0]["system"])
    assert "Two Pointer Classic" not in system_prompt
    assert "two-pointer-classic" not in system_prompt
