"""The 30 seed problems: structure, and — most importantly — correctness of their reference solutions.

Hidden-test outputs are *generated* by each problem's reference solution, so a bug there would poison every
test of that problem (and, in phase 3, wrongly fail correct submissions). Two independent guards:

1. every hand-written example output in a statement must equal the reference solution's output;
2. each reference solution is cross-checked against a separate, deliberately naive brute force on many small
   random inputs.
"""

from __future__ import annotations

import itertools
import random
import sys
from collections import Counter, deque
from functools import lru_cache
from pathlib import Path

import pytest
from sqlalchemy import func, select

SEEDS = Path(__file__).resolve().parents[3] / "database" / "seeds"
sys.path.insert(0, str(SEEDS))

from catalog import ALL_PROBLEMS, TAGS, slugify, starter_code  # noqa: E402
from catalog.spec import Spec  # noqa: E402
from problems_seed import build_test_inputs, seed_problems  # noqa: E402

from app.modules.problems import admin_service  # noqa: E402
from app.modules.problems.models import CaseKind, Problem, ProblemExample, ProblemTestCase, Tag  # noqa: E402
from app.modules.problems.schemas import MAX_CASE_CHARS  # noqa: E402

BY_SLUG = {spec.slug: spec for spec in ALL_PROBLEMS}


def normalise(text: str) -> str:
    return text.rstrip("\n") + "\n"


# --- Catalogue structure ------------------------------------------------------------------------


def test_the_catalogue_has_the_required_shape():
    assert len(ALL_PROBLEMS) == 30
    counts = Counter(spec.difficulty for spec in ALL_PROBLEMS)
    assert counts == {"EASY": 10, "MEDIUM": 12, "HARD": 8}
    assert len({spec.slug for spec in ALL_PROBLEMS}) == 30
    assert len({spec.title for spec in ALL_PROBLEMS}) == 30
    assert all(spec.slug == slugify(spec.title) or spec.slug for spec in ALL_PROBLEMS)


def test_every_required_topic_is_covered_and_no_unknown_topics_are_used():
    assert len(TAGS) == 23
    used = {tag for spec in ALL_PROBLEMS for tag in spec.tags}
    assert used == set(TAGS), (set(TAGS) - used, used - set(TAGS))


@pytest.mark.parametrize("spec", ALL_PROBLEMS, ids=lambda s: s.slug)
def test_each_problem_has_all_required_content(spec: Spec):
    assert len(spec.description) > 150
    assert spec.input_format.strip() and spec.output_format.strip() and spec.constraints.strip()
    assert 1 <= len(spec.tags) <= 4
    assert len(spec.examples) >= 2
    assert all(example.explanation.strip() for example in spec.examples)
    assert len(spec.hints) >= 1 and all(hint.strip() for hint in spec.hints)
    assert len(spec.editorial) > 80
    assert spec.time_complexity and spec.space_complexity
    assert 100 <= spec.time_limit_ms <= 10_000 and 16 <= spec.memory_limit_mb <= 1024


ALL_LANGUAGES = {"python", "cpp", "javascript", "c", "java", "csharp", "go", "rust", "typescript", "php"}


@pytest.mark.parametrize("spec", ALL_PROBLEMS, ids=lambda s: s.slug)
def test_starter_code_exists_for_every_language_and_python_is_valid(spec: Spec):
    starters = starter_code(spec)
    # A problem with a hand-written `starter_override` (its starter code shows how to use a helper the problem
    # statement describes, e.g. a supplied linked-list Node) may cover fewer languages than the generic template.
    assert set(starters) == ({"python", "cpp", "javascript"} if spec.starter_override else ALL_LANGUAGES)
    assert all(code.strip() for code in starters.values())
    compile(starters["python"], f"{spec.slug}.py", "exec")  # must at least be syntactically valid


# --- Correctness of examples and tests ----------------------------------------------------------


@pytest.mark.parametrize("spec", ALL_PROBLEMS, ids=lambda s: s.slug)
def test_hand_written_example_outputs_match_the_reference_solution(spec: Spec):
    for example in spec.examples:
        assert normalise(spec.solve(example.input)) == normalise(example.output), example.input


@pytest.mark.parametrize("spec", ALL_PROBLEMS, ids=lambda s: s.slug)
def test_hidden_tests_are_plentiful_deterministic_bounded_and_distinct(spec: Spec):
    inputs = build_test_inputs(spec)
    assert len(inputs) >= 6
    assert inputs == build_test_inputs(spec)  # same seed, same tests: the judge must be reproducible
    assert all(text.endswith("\n") for text in inputs)
    assert all(len(text) <= MAX_CASE_CHARS for text in inputs)
    everything = [example.input.rstrip() for example in spec.examples] + [text.rstrip() for text in inputs]
    assert len(set(everything)) == len(everything), "duplicate inputs across examples and hidden tests"
    for text in inputs:
        assert spec.solve(text).strip() != "", "expected output must not be blank"


# --- Independent brute-force cross-checks -------------------------------------------------------


def _ints(rng, count, lo, hi):
    return [rng.randint(lo, hi) for _ in range(count)]


def _line(values):
    return " ".join(map(str, values))


def brute_cranes(text):
    n, cap, *w = map(int, text.split())
    for i in range(n):
        for j in range(i + 1, n):
            if w[i] + w[j] == cap:
                return f"{i + 1} {j + 1}"
    return "-1"


def gen_cranes(rng):
    n = rng.randint(1, 9)
    return f"{n} {rng.randint(1, 12)}\n{_line(_ints(rng, n, 1, 8))}\n"


def brute_palindrome(text):
    s = "".join(c.lower() for c in text if c.isalnum())
    return "YES" if all(s[i] == s[-1 - i] for i in range(len(s))) else "NO"


def gen_palindrome(rng):
    return "".join(rng.choice("aAb ,!") for _ in range(rng.randint(0, 9))) + "\n"


def brute_brackets(text):
    s = text.strip()
    while True:
        reduced = s.replace("()", "").replace("[]", "").replace("{}", "")
        if reduced == s:
            return "YES" if not s else "NO"
        s = reduced


def gen_brackets(rng):
    return "".join(rng.choice("()[]{}") for _ in range(rng.randint(0, 10))) + "\n"


def brute_streak(text):
    n, *a = map(int, text.split())
    return str(max((len(list(g)) for k, g in itertools.groupby(a) if k == 1), default=0))


def gen_streak(rng):
    n = rng.randint(1, 12)
    return f"{n}\n{_line(_ints(rng, n, 0, 1))}\n"


def brute_lonely(text):
    s = text.strip()
    for i, c in enumerate(s):
        if s.count(c) == 1:
            return str(i + 1)
    return "-1"


def gen_lonely(rng):
    return "".join(rng.choice("abc") for _ in range(rng.randint(1, 9))) + "\n"


def brute_merge(text):
    n, m, *rest = map(int, text.split())
    return _line(sorted(rest[: n + m]))


def gen_merge(rng):
    n, m = rng.randint(0, 6), rng.randint(0, 6)
    if n + m == 0:
        n = 1
    return f"{n} {m}\n{_line(sorted(_ints(rng, n, -9, 9)))}\n{_line(sorted(_ints(rng, m, -9, 9)))}\n"


def brute_insert(text):
    n, q, *rest = map(int, text.split())
    a, queries = rest[:n], rest[n:]
    return "\n".join(str(next((i for i, v in enumerate(a) if v >= x), n)) for x in queries)


def gen_insert(rng):
    a = sorted(rng.sample(range(-20, 20), rng.randint(1, 8)))
    q = _ints(rng, rng.randint(1, 8), -22, 22)
    return f"{len(a)} {len(q)}\n{_line(a)}\n{_line(q)}\n"


def brute_bits(text):
    q, *xs = map(int, text.split())
    return "\n".join(str(sum((x >> b) & 1 for b in range(64))) for x in xs[:q])


def gen_bits(rng):
    q = rng.randint(1, 6)
    return f"{q}\n{_line([rng.randint(0, 10**18) for _ in range(q)])}\n"


def brute_tickets(text):
    n, k, *t = map(int, text.split())
    queue = deque((i, need) for i, need in enumerate(t))
    clock = 0
    while queue:
        i, need = queue.popleft()
        clock += 1
        if need == 1:
            if i == k - 1:
                return str(clock)
        else:
            queue.append((i, need - 1))
    raise AssertionError


def gen_tickets(rng):
    n = rng.randint(1, 6)
    return f"{n} {rng.randint(1, n)}\n{_line(_ints(rng, n, 1, 5))}\n"


def brute_stretch(text):
    s = text.strip()
    return str(max(j - i for i in range(len(s)) for j in range(i + 1, len(s) + 1) if len(set(s[i:j])) == j - i))


def gen_stretch(rng):
    return "".join(rng.choice("abc1") for _ in range(rng.randint(1, 10))) + "\n"


def brute_supply(text):
    n, target, *a = map(int, text.split())
    best = min((j - i for i in range(n) for j in range(i + 1, n + 1) if sum(a[i:j]) >= target), default=0)
    return str(best)


def gen_supply(rng):
    n = rng.randint(1, 8)
    return f"{n} {rng.randint(1, 30)}\n{_line(_ints(rng, n, 1, 9))}\n"


def brute_islands(text):
    r, c, *rows = text.split()
    r, c = int(r), int(c)
    land = {(y, x) for y in range(r) for x in range(c) if rows[y][x] == "#"}
    groups, seen = 0, set()
    for cell in sorted(land):
        if cell in seen:
            continue
        groups += 1
        frontier = [cell]
        while frontier:
            y, x = frontier.pop()
            if (y, x) in seen:
                continue
            seen.add((y, x))
            frontier += [p for p in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)) if p in land]
    return str(groups)


def gen_islands(rng):
    r, c = rng.randint(1, 6), rng.randint(1, 6)
    rows = ["".join(rng.choice("#.") for _ in range(c)) for _ in range(r)]
    return "\n".join([f"{r} {c}", *rows]) + "\n"


def brute_maze(text):
    r, c, *rows = text.split()
    r, c = int(r), int(c)
    cells = {(y, x): rows[y][x] for y in range(r) for x in range(c)}
    start = next(p for p, v in cells.items() if v == "S")
    end = next(p for p, v in cells.items() if v == "E")
    dist = {start: 0}
    for _ in range(r * c):  # Bellman-Ford style relaxation instead of a queue
        for (y, x), d in list(dist.items()):
            for p in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if p in cells and cells[p] != "#" and dist.get(p, 10**9) > d + 1:
                    dist[p] = d + 1
    return str(dist.get(end, -1))


def gen_maze(rng):
    r, c = rng.randint(1, 5), rng.randint(2, 6)
    grid = [[rng.choice("..#") for _ in range(c)] for _ in range(r)]
    grid[0][0] = "S"
    grid[r - 1][c - 1] = "E"
    return "\n".join([f"{r} {c}", *["".join(row) for row in grid]]) + "\n"


def brute_hot(text):
    n, k, *words = text.split()
    counts = {w: words.count(w) for w in set(words)}
    ordered = sorted(counts, key=lambda w: (-counts[w], w))[: int(k)]
    return "\n".join(f"{w} {counts[w]}" for w in ordered)


def gen_hot(rng):
    words = [rng.choice(["a", "b", "c", "d", "e"]) for _ in range(rng.randint(1, 10))]
    return f"{len(words)} {rng.randint(1, len(set(words)))}\n{_line(words)}\n"


def brute_coins(text):
    n, amount, *coins = map(int, text.split())

    @lru_cache(None)
    def go(rest):
        if rest == 0:
            return 0
        options = [go(rest - c) for c in coins if c <= rest]
        options = [o for o in options if o >= 0]
        return min(options) + 1 if options else -1

    return str(go(amount))


def gen_coins(rng):
    coins = rng.sample(range(1, 9), rng.randint(1, 4))
    return f"{len(coins)} {rng.randint(0, 25)}\n{_line(coins)}\n"


def brute_parens(text):
    n = int(text)
    out = []
    for combo in itertools.product("()", repeat=2 * n):
        depth = 0
        for ch in combo:
            depth += 1 if ch == "(" else -1
            if depth < 0:
                break
        else:
            if depth == 0:
                out.append("".join(combo))
    return "\n".join(sorted(out))


def brute_bookings(text):
    n, *flat = map(int, text.split())
    iv = [(flat[2 * i], flat[2 * i + 1]) for i in range(n)]
    best = 0
    for mask in range(1 << n):
        chosen = sorted(iv[i] for i in range(n) if mask >> i & 1)
        if all(chosen[i][1] <= chosen[i + 1][0] for i in range(len(chosen) - 1)):
            best = max(best, len(chosen))
    return str(best)


def gen_bookings(rng):
    n = rng.randint(1, 8)
    lines = []
    for _ in range(n):
        s = rng.randint(0, 10)
        lines.append(f"{s} {s + rng.randint(1, 5)}")
    return "\n".join([str(n), *lines]) + "\n"


def brute_rotated(text):
    n, target, *a = map(int, text.split())
    return str(a.index(target)) if target in a else "-1"


def gen_rotated(rng):
    base = sorted(rng.sample(range(-15, 15), rng.randint(1, 9)))
    shift = rng.randint(0, len(base) - 1)
    rotated = base[shift:] + base[:shift]
    return f"{len(rotated)} {rng.randint(-16, 16)}\n{_line(rotated)}\n"


def brute_circles(text):
    n, m, *pairs = map(int, text.split())
    group = {i: {i} for i in range(1, n + 1)}
    for i in range(m):
        a, b = pairs[2 * i], pairs[2 * i + 1]
        if group[a] is not group[b]:
            merged = group[a] | group[b]
            for member in merged:
                group[member] = merged
    unique = {id(g): g for g in group.values()}.values()
    return f"{len(unique)} {max(len(g) for g in unique)}"


def gen_circles(rng):
    n = rng.randint(1, 8)
    pairs = [f"{rng.randint(1, n)} {rng.randint(1, n)}" for _ in range(rng.randint(0, 8))]
    return "\n".join([f"{n} {len(pairs)}", *pairs]) + "\n"


def brute_vault(text):
    t, *rest = map(int, text.split())
    out = []
    for i in range(t):
        a, b, m = rest[3 * i : 3 * i + 3]
        value = 1 % m
        for _ in range(b):
            value = value * a % m
        out.append(str(value))
    return "\n".join(out)


def gen_vault(rng):
    t = rng.randint(1, 4)
    return (
        f"{t}\n" + "\n".join(f"{rng.randint(0, 30)} {rng.randint(0, 40)} {rng.randint(1, 50)}" for _ in range(t)) + "\n"
    )


def brute_window(text):
    n, k, *a = map(int, text.split())
    return _line([max(a[i : i + k]) for i in range(n - k + 1)])


def gen_window(rng):
    n = rng.randint(1, 10)
    return f"{n} {rng.randint(1, n)}\n{_line(_ints(rng, n, -9, 9))}\n"


def brute_edit(text):
    lines = text.split("\n")
    a, b = lines[0], lines[1]

    @lru_cache(None)
    def go(i, j):
        if i == 0:
            return j
        if j == 0:
            return i
        if a[i - 1] == b[j - 1]:
            return go(i - 1, j - 1)
        return 1 + min(go(i - 1, j), go(i, j - 1), go(i - 1, j - 1))

    return str(go(len(a), len(b)))


def gen_edit(rng):
    return (
        "".join(rng.choice("abc") for _ in range(rng.randint(0, 6)))
        + "\n"
        + "".join(rng.choice("abc") for _ in range(rng.randint(0, 6)))
        + "\n"
    )


def brute_route(text):
    n, m, *flat = map(int, text.split())
    edges = [(flat[3 * i], flat[3 * i + 1], flat[3 * i + 2]) for i in range(m)]
    dist = {1: 0}
    for _ in range(n):
        for u, v, w in edges:
            if u in dist and dist[u] + w < dist.get(v, float("inf")):
                dist[v] = dist[u] + w
    return str(dist.get(n, -1))


def gen_route(rng):
    n = rng.randint(1, 6)
    edges = [f"{rng.randint(1, n)} {rng.randint(1, n)} {rng.randint(0, 9)}" for _ in range(rng.randint(0, 10))]
    return "\n".join([f"{n} {len(edges)}", *edges]) + "\n"


def brute_directory(text):
    n, q, *tokens = text.split()
    words, prefixes = tokens[: int(n)], tokens[int(n) :]
    return "\n".join(str(sum(w.startswith(p) for w in words)) for p in prefixes)


def gen_directory(rng):
    words = ["".join(rng.choice("ab") for _ in range(rng.randint(1, 4))) for _ in range(rng.randint(1, 8))]
    prefixes = ["".join(rng.choice("ab") for _ in range(rng.randint(1, 3))) for _ in range(rng.randint(1, 6))]
    return f"{len(words)} {len(prefixes)}\n{_line(words)}\n{_line(prefixes)}\n"


def brute_median(text):
    n, *a = map(int, text.split())
    return _line([sorted(a[: i + 1])[i // 2] for i in range(n)])


def gen_median(rng):
    n = rng.randint(1, 10)
    return f"{n}\n{_line(_ints(rng, n, -9, 9))}\n"


def brute_network(text):
    n, m, *flat = map(int, text.split())
    edges = [(flat[3 * i], flat[3 * i + 1], flat[3 * i + 2]) for i in range(m)]
    best = None
    for subset in itertools.combinations(range(m), n - 1):
        comp = {i: i for i in range(1, n + 1)}

        def find(x, comp=comp):
            while comp[x] != x:
                x = comp[x]
            return x

        ok = True
        for index in subset:
            u, v, _ = edges[index]
            ru, rv = find(u), find(v)
            if ru == rv:
                ok = False
                break
            comp[ru] = rv
        if ok:
            cost = sum(edges[i][2] for i in subset)
            best = cost if best is None else min(best, cost)
    return str(best) if best is not None else "-1"


def gen_network(rng):
    n = rng.randint(1, 5)
    edges = [f"{rng.randint(1, n)} {rng.randint(1, n)} {rng.randint(1, 9)}" for _ in range(rng.randint(0, 7))]
    return "\n".join([f"{n} {len(edges)}", *edges]) + "\n"


def brute_climb(text):
    n, *a = map(int, text.split())
    best = [1] * n
    for i in range(n):
        for j in range(i):
            if a[j] < a[i]:
                best[i] = max(best[i], best[j] + 1)
    return str(max(best))


def gen_climb(rng):
    n = rng.randint(1, 10)
    return f"{n}\n{_line(_ints(rng, n, 0, 8))}\n"


CROSS_CHECKS = [
    ("harbor-cranes", gen_cranes, brute_cranes),
    ("mirror-message", gen_palindrome, brute_palindrome),
    ("toolbox-brackets", gen_brackets, brute_brackets),
    ("winning-streak", gen_streak, brute_streak),
    ("first-lonely-letter", gen_lonely, brute_lonely),
    ("merge-timetables", gen_merge, brute_merge),
    ("insert-position", gen_insert, brute_insert),
    ("bit-counter", gen_bits, brute_bits),
    ("ticket-counter", gen_tickets, brute_tickets),
    ("longest-fresh-stretch", gen_stretch, brute_stretch),
    ("shortest-supply-run", gen_supply, brute_supply),
    ("island-count", gen_islands, brute_islands),
    ("maze-runner", gen_maze, brute_maze),
    ("hot-words", gen_hot, brute_hot),
    ("fewest-coins", gen_coins, brute_coins),
    ("max-bookings", gen_bookings, brute_bookings),
    ("rotated-dial-search", gen_rotated, brute_rotated),
    ("friend-circles", gen_circles, brute_circles),
    ("vault-combination", gen_vault, brute_vault),
    ("peak-window", gen_window, brute_window),
    ("word-morph", gen_edit, brute_edit),
    ("cheapest-route", gen_route, brute_route),
    ("prefix-directory", gen_directory, brute_directory),
    ("steady-median", gen_median, brute_median),
    ("cheapest-network", gen_network, brute_network),
    ("steady-climb", gen_climb, brute_climb),
]


@pytest.mark.parametrize(("slug", "generate", "brute"), CROSS_CHECKS, ids=[c[0] for c in CROSS_CHECKS])
def test_reference_solution_agrees_with_an_independent_brute_force(slug, generate, brute):
    spec = BY_SLUG[slug]
    rng = random.Random(f"crosscheck:{slug}")
    for _ in range(150):
        text = generate(rng)
        assert spec.solve(text).strip() == brute(text).strip(), text


def test_paren_forge_matches_brute_force_and_catalan_numbers():
    spec = BY_SLUG["paren-forge"]
    for n in range(1, 7):
        assert spec.solve(f"{n}\n") == brute_parens(str(n))
    assert [len(spec.solve(f"{n}\n").splitlines()) for n in range(1, 9)] == [1, 2, 5, 14, 42, 132, 429, 1430]


def test_queens_standoff_matches_the_known_sequence():
    spec = BY_SLUG["queens-standoff"]
    assert [spec.solve(f"{n}\n") for n in range(1, 11)] == ["1", "0", "0", "2", "10", "4", "40", "92", "352", "724"]


def test_level_sums_matches_a_naive_tree_walk():
    spec = BY_SLUG["level-sums"]
    rng = random.Random("levels")

    def naive(tokens):
        # Rebuild explicit nodes, then sum by depth with a plain BFS.
        nodes = [None if t == "null" else {"v": int(t), "kids": []} for t in tokens]
        parents = deque([nodes[0]])
        i = 1
        while parents and i < len(nodes):
            parent = parents.popleft()
            for _ in range(2):
                if i < len(nodes):
                    if nodes[i] is not None:
                        parent["kids"].append(nodes[i])
                        parents.append(nodes[i])
                    i += 1
        sums, layer = [], [nodes[0]]
        while layer:
            sums.append(sum(n["v"] for n in layer))
            layer = [k for n in layer for k in n["kids"]]
        return _line(sums)

    for _ in range(100):
        tokens = ["5"]
        real = 1
        while real and len(tokens) < 14:
            take = min(real * 2, 14 - len(tokens))
            level = [rng.choice(["null", str(rng.randint(-9, 9))]) for _ in range(take)]
            tokens += level
            real = sum(1 for t in level if t != "null")
        while tokens and tokens[-1] == "null":
            tokens.pop()
        text = f"{len(tokens)}\n{' '.join(tokens)}\n"
        assert spec.solve(text) == naive(tokens), text


# --- Loading into the database ------------------------------------------------------------------


async def test_seeding_creates_publishable_problems_and_is_idempotent(app):
    async with app.state.sessionmaker() as db:
        created, skipped = await seed_problems(db)
    assert (created, skipped) == (30, 0)

    async with app.state.sessionmaker() as db:
        again = await seed_problems(db)
        assert again == (0, 30)
        assert await db.scalar(select(func.count()).select_from(Problem)) == 30
        assert await db.scalar(select(func.count()).select_from(Tag)) == 23
        assert await db.scalar(select(func.count()).select_from(ProblemExample)) == sum(
            len(s.examples) for s in ALL_PROBLEMS
        )

        enabled = await admin_service.enabled_language_keys(db)
        for problem in await db.scalars(select(Problem)):
            issues = admin_service.validate_problem(problem, enabled)
            assert issues == [], (problem.slug, [i.code for i in issues])
            assert problem.published is True
            public = [c for c in problem.test_cases if c.kind == CaseKind.PUBLIC]
            hidden = [c for c in problem.test_cases if c.kind == CaseKind.HIDDEN]
            assert len(public) == len(BY_SLUG[problem.slug].examples) and len(hidden) >= 6

        # The stored expected outputs are exactly the reference solution's output.
        sample = await db.scalar(
            select(ProblemTestCase)
            .join(Problem)
            .where(Problem.slug == "harbor-cranes", ProblemTestCase.kind == CaseKind.HIDDEN)
        )
        assert sample.expected_output == normalise(BY_SLUG["harbor-cranes"].solve(sample.input_data))


async def test_seeded_problems_are_served_by_the_public_api_without_leaking_hidden_tests(app, client):
    async with app.state.sessionmaker() as db:
        await seed_problems(db)
        hidden_inputs = [
            c.input_data
            for c in await db.scalars(select(ProblemTestCase).where(ProblemTestCase.kind == CaseKind.HIDDEN))
        ]
    listing = (await client.get("/api/problems?limit=100")).json()
    assert listing["total"] == 30
    assert (await client.get("/api/problems?difficulty=HARD")).json()["total"] == 8
    assert (await client.get("/api/problems?tag=trie")).json()["items"][0]["slug"] == "prefix-directory"
    assert (await client.get("/api/problems", params={"q": "coin"})).json()["items"][0]["slug"] == "fewest-coins"

    body = (await client.get("/api/problems/harbor-cranes")).text
    assert "hint_count" in body
    # A large hidden input must not appear anywhere in a public payload.
    biggest = max(hidden_inputs, key=len)
    assert biggest[:200] not in body
    assert biggest[:200] not in (await client.get("/api/problems?limit=100")).text
