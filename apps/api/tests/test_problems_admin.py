"""Admin problem API: access control, validation, test-case sync, publish rules, audit trail."""

from __future__ import annotations

import copy

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.modules.audit.models import AuditLog
from app.modules.problems.models import ProblemExample, ProblemStarterCode, ProblemTestCase
from app.modules.users.models import RoleName
from tests.conftest import make_client, signed_in
from tests.problems_helpers import HIDDEN_SENTINEL, add_tags, admin_session, insert_problem, payload

ADMIN_ENDPOINTS = [
    ("GET", "/api/admin/problems"),
    ("POST", "/api/admin/problems"),
    ("GET", "/api/admin/problems/00000000-0000-0000-0000-000000000000"),
    ("PUT", "/api/admin/problems/00000000-0000-0000-0000-000000000000"),
    ("GET", "/api/admin/problems/00000000-0000-0000-0000-000000000000/validation"),
    ("POST", "/api/admin/problems/00000000-0000-0000-0000-000000000000/publish"),
    ("POST", "/api/admin/problems/00000000-0000-0000-0000-000000000000/unpublish"),
    ("POST", "/api/admin/problems/00000000-0000-0000-0000-000000000000/archive"),
    ("POST", "/api/admin/problems/00000000-0000-0000-0000-000000000000/restore"),
    ("POST", "/api/admin/tags"),
]


# --- Access control -----------------------------------------------------------------------------


@pytest.mark.parametrize(("method", "path"), ADMIN_ENDPOINTS)
async def test_admin_problem_endpoints_reject_anonymous_callers(client: AsyncClient, method, path):
    response = await client.request(method, path, json=payload() if method in {"POST", "PUT"} else None)
    assert response.status_code == 401


@pytest.mark.parametrize("role", [RoleName.USER, RoleName.MODERATOR])
@pytest.mark.parametrize(("method", "path"), ADMIN_ENDPOINTS)
async def test_admin_problem_endpoints_reject_non_admins(app, role, method, path):
    async with signed_in(app, username="member", roles=(role,)) as (client, headers):
        response = await client.request(
            method, path, json=payload() if method in {"POST", "PUT"} else None, headers=headers
        )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_users_cannot_smuggle_hidden_tests_into_a_problem(app):
    """There is no user-facing write API for problems or tests at all, so nothing to abuse.

    (`/api/submissions` is a real route from phase 3 onward, but it creates a *submission* — a program to be judged
    against a problem's existing tests — from an unrelated payload shape; it is not a way to write problem data, and
    its own validation is covered in test_submissions_api.py.)"""
    await add_tags(app, "Array")
    async with signed_in(app, username="mallory") as (client, headers):
        for method, path in (
            ("POST", "/api/problems"),
            ("PUT", "/api/problems/anything"),
            ("POST", "/api/problems/anything/test-cases"),
        ):
            response = await client.request(method, path, json=payload(), headers=headers)
            assert response.status_code in {404, 405}, (method, path)


# --- Create & validation ------------------------------------------------------------------------


async def test_admin_can_create_a_draft_and_read_everything_back(app):
    await add_tags(app, "Array")
    async with admin_session(app) as (client, headers):
        created = await client.post("/api/admin/problems", json=payload(), headers=headers)
        assert created.status_code == 201
        body = created.json()
        assert body["status"] == "DRAFT"
        assert body["tags"] == ["array"]
        assert body["starter_code"] == {"python": "print(-1)\n", "cpp": "int main(){}\n"}
        assert [c["kind"] for c in body["test_cases"]] == ["PUBLIC", "HIDDEN", "HIDDEN", "HIDDEN"]
        assert body["test_cases"][0]["show_as_example"] is True
        assert HIDDEN_SENTINEL in created.text  # the admin view *does* include hidden data

        again = (await client.get(f"/api/admin/problems/{body['id']}", headers=headers)).json()
        assert again == body

        # A draft is invisible to the public API.
        async with make_client(app) as anon:
            assert (await anon.get("/api/problems/harbor-cranes")).status_code == 404


async def test_create_rejects_bad_input(app):
    await add_tags(app, "Array")
    async with admin_session(app) as (client, headers):
        assert (await client.post("/api/admin/problems", json=payload(), headers=headers)).status_code == 201

        async def post(**overrides):
            return await client.post("/api/admin/problems", json=payload(**overrides), headers=headers)

        assert (await post()).json()["error"]["code"] == "SLUG_TAKEN"
        unknown_tag = await post(slug="other", tags=["array", "no-such-tag"])
        assert unknown_tag.status_code == 422 and unknown_tag.json()["error"]["code"] == "UNKNOWN_TAG"
        unknown_lang = await post(slug="other", starter_code={"cobol": "x"})
        assert unknown_lang.status_code == 422 and unknown_lang.json()["error"]["code"] == "UNKNOWN_LANGUAGE"

        for bad in (
            {"slug": "Has Spaces"},
            {"slug": "UPPER"},
            {"slug": "ab"},
            {"title": "x"},
            {"difficulty": "IMPOSSIBLE"},
            {"time_limit_ms": 5},
            {"time_limit_ms": 999_999},
            {"memory_limit_mb": 1},
            {"tags": ["array", "array"]},
            {"hints": ["  "]},
            {"unexpected_field": 1},
        ):
            response = await post(**({"slug": "fresh-slug"} | bad))
            assert response.status_code in {409, 422}, bad
            if "slug" not in bad:
                assert response.status_code == 422, bad


async def test_only_public_cases_can_be_examples(app):
    await add_tags(app, "Array")
    body = payload()
    body["test_cases"][1]["show_as_example"] = True  # a HIDDEN case
    async with admin_session(app) as (client, headers):
        response = await client.post("/api/admin/problems", json=body, headers=headers)
    assert response.status_code == 422


# --- Publishing ---------------------------------------------------------------------------------


async def test_publish_is_blocked_until_the_problem_is_complete(app):
    await add_tags(app, "Array")
    incomplete = payload(
        description="short",
        input_format="",
        tags=[],
        starter_code={},
        test_cases=[
            {"kind": "PUBLIC", "input": "1\n", "expected_output": "", "show_as_example": False},
            {"kind": "HIDDEN", "input": "1\n", "expected_output": "1\n"},
        ],
    )
    async with admin_session(app) as (client, headers):
        created = (await client.post("/api/admin/problems", json=incomplete, headers=headers)).json()
        pid = created["id"]

        report = (await client.get(f"/api/admin/problems/{pid}/validation", headers=headers)).json()
        codes = {issue["code"] for issue in report["issues"]}
        assert report["ok"] is False
        assert {
            "DESCRIPTION_TOO_SHORT",
            "REQUIRED",
            "NO_TAGS",
            "NO_EXAMPLE",
            "TOO_FEW_HIDDEN",
            "EMPTY_OUTPUT",
            "DUPLICATE_TEST",
            "NO_STARTER_CODE",
        } <= codes

        blocked = await client.post(f"/api/admin/problems/{pid}/publish", headers=headers)
        assert blocked.status_code == 422
        assert blocked.json()["error"]["code"] == "PROBLEM_NOT_READY"
        assert len(blocked.json()["error"]["details"]) >= 5
        assert (await client.get(f"/api/admin/problems/{pid}", headers=headers)).json()["status"] == "DRAFT"

        # Fix it and publish.
        fixed = await client.put(f"/api/admin/problems/{pid}", json=payload(), headers=headers)
        assert fixed.status_code == 200
        assert (await client.get(f"/api/admin/problems/{pid}/validation", headers=headers)).json() == {
            "ok": True,
            "issues": [],
        }
        published = await client.post(f"/api/admin/problems/{pid}/publish", headers=headers)
        assert published.status_code == 200 and published.json()["status"] == "PUBLISHED"
        assert published.json()["published_at"] is not None

        async with make_client(app) as anon:
            listing = (await anon.get("/api/problems")).json()
            assert [i["slug"] for i in listing["items"]] == ["harbor-cranes"]


async def test_publish_lifecycle_unpublish_archive_restore(app):
    await add_tags(app, "Array")
    async with admin_session(app) as (client, headers):
        pid = (await client.post("/api/admin/problems", json=payload(), headers=headers)).json()["id"]

        async def act(action):
            return (await client.post(f"/api/admin/problems/{pid}/{action}", headers=headers)).json()["status"]

        async def public_count():
            async with make_client(app) as anon:
                return (await anon.get("/api/problems")).json()["total"]

        assert await act("publish") == "PUBLISHED" and await public_count() == 1
        assert await act("unpublish") == "DRAFT" and await public_count() == 0
        assert await act("publish") == "PUBLISHED"
        assert await act("archive") == "ARCHIVED" and await public_count() == 0

        blocked = await client.post(f"/api/admin/problems/{pid}/publish", headers=headers)
        assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "PROBLEM_ARCHIVED"

        assert await act("restore") == "PUBLISHED" and await public_count() == 1  # published flag survived


async def test_admin_actions_are_audited(app):
    await add_tags(app, "Array")
    async with admin_session(app) as (client, headers):
        pid = (await client.post("/api/admin/problems", json=payload(), headers=headers)).json()["id"]
        await client.put(f"/api/admin/problems/{pid}", json=payload(title="Renamed Cranes"), headers=headers)
        await client.post(f"/api/admin/problems/{pid}/publish", headers=headers)
        await client.post(f"/api/admin/problems/{pid}/archive", headers=headers)
    async with app.state.sessionmaker() as db:
        actions = list(
            await db.scalars(
                select(AuditLog.action).where(AuditLog.action.like("problem.%")).order_by(AuditLog.created_at)
            )
        )
    assert actions == ["problem.create", "problem.update", "problem.publish", "problem.archive"]


# --- Updating: test-case and starter-code sync --------------------------------------------------


async def test_updating_keeps_test_case_ids_and_applies_adds_removes_and_reorders(app):
    await add_tags(app, "Array")
    async with admin_session(app) as (client, headers):
        created = (await client.post("/api/admin/problems", json=payload(), headers=headers)).json()
        pid = created["id"]
        original = {c["input"]: c["id"] for c in created["test_cases"]}

        edited = copy.deepcopy(payload())
        cases = created["test_cases"]
        edited["test_cases"] = [{**c, "input": c["input"], "expected_output": c["expected_output"]} for c in cases]
        for c in edited["test_cases"]:
            c.pop("id", None)
        # Keep ids for the first two (reordered), drop the last hidden one, add a new hidden one.
        edited["test_cases"] = [
            {
                "id": cases[1]["id"],
                **{k: cases[1][k] for k in ("kind", "input", "expected_output")},
                "show_as_example": False,
            },
            {
                "id": cases[0]["id"],
                **{k: cases[0][k] for k in ("kind", "input", "expected_output")},
                "show_as_example": True,
                "example_explanation": "Changed explanation.",
            },
            {
                "id": cases[2]["id"],
                **{k: cases[2][k] for k in ("kind", "input", "expected_output")},
                "show_as_example": False,
            },
            {"kind": "HIDDEN", "input": "brand new\n", "expected_output": "42\n"},
        ]
        updated = await client.put(f"/api/admin/problems/{pid}", json=edited, headers=headers)
        assert updated.status_code == 200, updated.text
        result = updated.json()["test_cases"]

        assert [c["input"] for c in result] == [cases[1]["input"], cases[0]["input"], cases[2]["input"], "brand new\n"]
        assert result[0]["id"] == original[cases[1]["input"]]  # ids survive
        assert result[1]["id"] == original[cases[0]["input"]]
        assert cases[3]["input"] not in [c["input"] for c in result]  # omitted -> deleted
        assert result[1]["example_explanation"] == "Changed explanation."

    async with app.state.sessionmaker() as db:
        assert len(list(await db.scalars(select(ProblemTestCase)))) == 4
        assert len(list(await db.scalars(select(ProblemExample)))) == 1  # no orphans


async def test_repeated_updates_do_not_collide_on_unique_keys(app):
    """Re-saving must update starter code / examples in place; replacing them would violate their keys."""
    await add_tags(app, "Array")
    async with admin_session(app) as (client, headers):
        created = (await client.post("/api/admin/problems", json=payload(), headers=headers)).json()
        pid = created["id"]
        for round_number in range(3):
            body = payload(
                starter_code={"python": f"# round {round_number}\n", "javascript": "// js\n"}
                if round_number
                else {"python": "a"},
            )
            body["test_cases"] = [
                {
                    **{
                        k: c[k]
                        for k in ("id", "kind", "input", "expected_output", "show_as_example", "example_explanation")
                    }
                }
                for c in (await client.get(f"/api/admin/problems/{pid}", headers=headers)).json()["test_cases"]
            ]
            response = await client.put(f"/api/admin/problems/{pid}", json=body, headers=headers)
            assert response.status_code == 200, (round_number, response.text)
        final = response.json()
        assert final["starter_code"] == {"python": "# round 2\n", "javascript": "// js\n"}  # cpp removed
        assert [c["show_as_example"] for c in final["test_cases"]] == [True, False, False, False]

    async with app.state.sessionmaker() as db:
        assert len(list(await db.scalars(select(ProblemStarterCode)))) == 2
        assert len(list(await db.scalars(select(ProblemExample)))) == 1


async def test_update_rejects_test_case_ids_from_another_problem(app):
    await add_tags(app, "Array")
    async with admin_session(app) as (client, headers):
        first = (await client.post("/api/admin/problems", json=payload(), headers=headers)).json()
        second = (
            await client.post(
                "/api/admin/problems", json=payload(slug="second-one", title="Second One"), headers=headers
            )
        ).json()
        stolen = first["test_cases"][1]["id"]
        body = payload(slug="second-one", title="Second One")
        body["test_cases"] = [{"id": stolen, "kind": "HIDDEN", "input": "x", "expected_output": "y"}]
        response = await client.put(f"/api/admin/problems/{second['id']}", json=body, headers=headers)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "UNKNOWN_TEST_CASE"

        # ...and the first problem's cases are untouched.
        untouched = (await client.get(f"/api/admin/problems/{first['id']}", headers=headers)).json()
        assert len(untouched["test_cases"]) == 4


async def test_slug_can_change_but_not_to_a_taken_one(app):
    await add_tags(app, "Array")
    async with admin_session(app) as (client, headers):
        a = (await client.post("/api/admin/problems", json=payload(), headers=headers)).json()
        await client.post("/api/admin/problems", json=payload(slug="taken", title="Taken"), headers=headers)
        clash = await client.put(f"/api/admin/problems/{a['id']}", json=payload(slug="taken"), headers=headers)
        assert clash.status_code == 409
        moved = await client.put(f"/api/admin/problems/{a['id']}", json=payload(slug="renamed"), headers=headers)
        assert moved.status_code == 200 and moved.json()["slug"] == "renamed"


async def test_unknown_problem_ids_are_404(app):
    async with admin_session(app) as (client, headers):
        missing = "11111111-1111-1111-1111-111111111111"
        for method, path in (("GET", ""), ("GET", "/validation"), ("POST", "/publish"), ("POST", "/archive")):
            response = await client.request(method, f"/api/admin/problems/{missing}{path}", headers=headers)
            assert response.status_code == 404 and response.json()["error"]["code"] == "PROBLEM_NOT_FOUND"
        assert (await client.get("/api/admin/problems/not-a-uuid", headers=headers)).status_code == 422


# --- Admin list & tags --------------------------------------------------------------------------


async def test_admin_list_shows_drafts_and_archived_with_counts_and_filters(app):
    await add_tags(app, "Array")
    await insert_problem(app, "live-one", title="Live One", tags=("array",))
    await insert_problem(app, "a-draft", title="A Draft", published=False)
    await insert_problem(app, "old-one", title="Old One", archived=True)
    async with admin_session(app) as (client, headers):
        everything = (await client.get("/api/admin/problems", headers=headers)).json()
        assert everything["total"] == 3
        by_slug = {i["slug"]: i for i in everything["items"]}
        assert by_slug["live-one"]["status"] == "PUBLISHED" and by_slug["a-draft"]["status"] == "DRAFT"
        assert by_slug["old-one"]["status"] == "ARCHIVED"
        assert (by_slug["live-one"]["public_tests"], by_slug["live-one"]["hidden_tests"]) == (1, 1)

        for status_value, expected in (("DRAFT", {"a-draft"}), ("PUBLISHED", {"live-one"}), ("ARCHIVED", {"old-one"})):
            got = (await client.get(f"/api/admin/problems?status={status_value}", headers=headers)).json()["items"]
            assert {i["slug"] for i in got} == expected
        found = (await client.get("/api/admin/problems?q=draft", headers=headers)).json()["items"]
        assert [i["slug"] for i in found] == ["a-draft"]
        assert (await client.get("/api/admin/problems?status=BOGUS", headers=headers)).status_code == 422


async def test_admin_can_create_tags_and_they_show_up_publicly(app, client: AsyncClient):
    async with admin_session(app) as (admin, headers):
        created = await admin.post("/api/admin/tags", json={"name": "Union Find"}, headers=headers)
        assert created.status_code == 201 and created.json() == {"name": "Union Find", "slug": "union-find"}
        assert (await admin.post("/api/admin/tags", json={"name": "union find"}, headers=headers)).status_code == 409
        assert (await admin.post("/api/admin/tags", json={"name": "!!"}, headers=headers)).status_code == 422
    assert [t["slug"] for t in (await client.get("/api/tags")).json()] == ["union-find"]


# --- Request size limits ------------------------------------------------------------------------


async def test_admin_can_upload_large_test_files_but_others_are_capped(app):
    await add_tags(app, "Array")
    big = payload()
    # Three 600 KB cases: each under the per-case cap, together ~1.8 MB, above the 1 MB default body limit.
    for index in range(3):
        big["test_cases"].append({"kind": "HIDDEN", "input": f"{index}" + "x" * 600_000, "expected_output": "1\n"})
    async with admin_session(app) as (admin, headers):
        assert (await admin.post("/api/admin/problems", json=big, headers=headers)).status_code == 201

    # The same body is refused for a non-admin caller and for an anonymous one (the raised limit is bearer-only).
    async with signed_in(app, username="member") as (member, _):
        assert (
            await member.post("/api/auth/login", json={"identifier": "x" * 2_000_000, "password": "y"})
        ).status_code == 413
    async with make_client(app) as anon:
        assert (await anon.post("/api/admin/problems", json=big)).status_code == 413
