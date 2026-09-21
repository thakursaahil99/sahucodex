"""Twelve MEDIUM problems. All statements are original."""

from __future__ import annotations

import heapq
import random
from bisect import bisect_left
from collections import Counter, deque

from .spec import Example, Spec, joined, nums

# --- 11. Longest Fresh Stretch ------------------------------------------------------------------


def _stretch_solve(text: str) -> str:
    s = text.strip()
    last: dict[str, int] = {}
    start = best = 0
    for i, ch in enumerate(s):
        if ch in last and last[ch] >= start:
            start = last[ch] + 1
        last[ch] = i
        best = max(best, i - start + 1)
    return str(best)


def _stretch_hidden(rng: random.Random) -> list[str]:
    alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
    unique_run = "".join(rng.sample(alphabet, 36))
    noisy = "".join(rng.choice("abc") for _ in range(40000)) + unique_run + "".join(rng.choice("abc") for _ in range(40000))
    return [
        "a\n",
        "bbbbbbb\n",
        "pwwkew\n",
        "dvdf\n",
        "abba\n",
        "tmmzuxt\n",
        alphabet + alphabet + "\n",
        noisy + "\n",
        "".join(rng.choice("ab") for _ in range(100000)) + "\n",
    ]


LONGEST_FRESH_STRETCH = Spec(
    slug="longest-fresh-stretch",
    title="Longest Fresh Stretch",
    difficulty="MEDIUM",
    tags=("Sliding Window", "HashMap", "String"),
    description=(
        "A weather station logs one symbol per hour — a letter or a digit standing for the kind of weather. A "
        "*fresh stretch* is a run of consecutive hours in which **no symbol repeats**.\n\n"
        "Find the length of the longest fresh stretch in the log."
    ),
    input_format="A single line containing the log.",
    output_format="One integer: the length of the longest substring whose characters are all different.",
    constraints="- 1 ≤ length ≤ 100 000\n- lowercase letters and digits only",
    examples=(
        Example("abcabcbb\n", "3\n", "`abc` is the longest stretch without a repeated symbol."),
        Example("bbbb\n", "1\n", "Every stretch longer than one hour repeats `b`."),
    ),
    solve=_stretch_solve,
    hidden=_stretch_hidden,
    hints=(
        "Try every start and extend until a repeat: correct, but O(n²) or worse.",
        "Keep a window [start, i] with no repeats. When s[i] already occurs inside the window, where must the window start move to?",
        "Remember the last index of every symbol; jump `start` to just past the previous occurrence (never backwards).",
    ),
    editorial="Sliding window with a map from symbol to its most recent index. For each `i`, if `s[i]` was seen at an index ≥ `start`, set `start = last[s[i]] + 1`. Update `last[s[i]] = i` and the best length `i − start + 1`.",
    time_complexity="O(n)",
    space_complexity="O(alphabet)",
)

# --- 12. Shortest Supply Run --------------------------------------------------------------------


def _supply_solve(text: str) -> str:
    tok = text.split()
    n, target = int(tok[0]), int(tok[1])
    a = list(map(int, tok[2 : 2 + n]))
    best = n + 1
    left = total = 0
    for right, value in enumerate(a):
        total += value
        while total >= target:
            best = min(best, right - left + 1)
            total -= a[left]
            left += 1
    return "0" if best == n + 1 else str(best)


def _supply_hidden(rng: random.Random) -> list[str]:
    def make(a: list[int], target: int) -> str:
        return joined(f"{len(a)} {target}", nums(a))

    big = [rng.randint(1, 1000) for _ in range(30000)]
    return [
        make([5], 5),
        make([5], 6),
        make([1, 1, 1, 1], 4),
        make([1, 2, 3, 4, 5], 11),
        make([10, 2, 3], 6),
        make([1, 4, 4], 4),
        make(big, 3_000_000),
        make(big, 250_000),
        make(big, 1_000),
    ]


SHORTEST_SUPPLY_RUN = Spec(
    slug="shortest-supply-run",
    title="Shortest Supply Run",
    difficulty="MEDIUM",
    tags=("Sliding Window", "Two Pointer", "Array"),
    description=(
        "A mountain refuge is served by a chain of `n` huts along a trail. Hut `i` can donate `a[i]` litres of water "
        "(always a positive amount). A supply team walks a **contiguous** section of the trail, collecting from every "
        "hut on the way, and needs **at least `S` litres** in total.\n\n"
        "What is the smallest number of huts in a contiguous section that provides at least `S` litres? Print `0` if "
        "even the whole trail is not enough."
    ),
    input_format="The first line contains `n` and `S`. The second line contains `a[1] … a[n]`.",
    output_format="One integer: the minimum length of a contiguous section with sum ≥ S, or `0` if none exists.",
    constraints="- 1 ≤ n ≤ 100 000\n- 1 ≤ a[i] ≤ 10 000\n- 1 ≤ S ≤ 10^9",
    examples=(
        Example("6 7\n2 3 1 2 4 3\n", "2\n", "The section `4 3` sums to 7, and no single hut is enough."),
        Example("3 100\n1 2 3\n", "0\n", "Even all three huts give only 6 litres."),
    ),
    solve=_supply_solve,
    hidden=_supply_hidden,
    hints=(
        "Because every amount is positive, adding a hut can only increase the sum and removing one can only decrease it.",
        "Grow a window on the right until its sum reaches S, then shrink it from the left as far as it still qualifies.",
    ),
    editorial="Two pointers over positive numbers. Extend `right`, adding `a[right]` to the running sum. While the sum is at least `S`, record the window length and drop `a[left]`, advancing `left`. Each index enters and leaves the window once.",
    time_complexity="O(n)",
    space_complexity="O(1)",
)

# --- 13. Level Sums -----------------------------------------------------------------------------


def _level_solve(text: str) -> str:
    tok = text.split()
    n = int(tok[0])
    values = tok[1 : 1 + n]
    stream = iter(values[1:])
    level = [int(values[0])]
    sums: list[int] = []
    while level:
        sums.append(sum(level))
        following: list[int] = []
        for _ in level:
            for _ in range(2):
                token = next(stream, None)
                if token is None:
                    break
                if token != "null":
                    following.append(int(token))
        level = following
    return nums(sums)


def _random_tree_tokens(rng: random.Random, nodes: int, lo: int, hi: int, branch: float) -> str:
    values = [rng.randint(lo, hi) for _ in range(nodes)]
    children: list[list[int | None]] = [[None, None] for _ in range(nodes)]
    queue = deque([0])
    placed = 1
    last = 0
    while placed < nodes:
        if not queue:
            children[last][0] = placed  # keep the tree connected
            queue.append(placed)
            placed += 1
            continue
        current = queue.popleft()
        last = current
        for side in (0, 1):
            if placed < nodes and rng.random() < branch:
                children[current][side] = placed
                queue.append(placed)
                placed += 1
    out: list[str] = []
    walk: deque[int | None] = deque([0])
    while walk:
        node = walk.popleft()
        if node is None:
            out.append("null")
            continue
        out.append(str(values[node]))
        walk.extend(children[node])
    while out and out[-1] == "null":
        out.pop()
    return joined(len(out), " ".join(out))


def _level_hidden(rng: random.Random) -> list[str]:
    return [
        joined(1, "-7"),
        joined(3, "1 2 3"),
        joined(3, "1 null 2"),
        joined(5, "1 null 2 null 3"),
        joined(7, "0 -5 5 -6 null null 6"),
        _random_tree_tokens(rng, 15, -50, 50, 0.7),
        _random_tree_tokens(rng, 2000, -1000, 1000, 0.6),
        _random_tree_tokens(rng, 6000, -10**6, 10**6, 0.95),
        _random_tree_tokens(rng, 5000, 1, 9, 0.5),
    ]


LEVEL_SUMS = Spec(
    slug="level-sums",
    title="Level Sums",
    difficulty="MEDIUM",
    tags=("Tree", "BFS"),
    description=(
        "A family tree of a village is recorded as a binary tree: every person has at most two children, and each "
        "person carries a *fortune* value (possibly negative — some families are in debt).\n\n"
        "For every **generation** (all people at the same depth, with the ancestor at depth 0) print the **sum of "
        "fortunes** in that generation, from the oldest generation to the youngest.\n\n"
        "The tree is given in **level order**: the values are listed generation by generation, left to right, with "
        "the word `null` standing for a missing child. The children of a `null` are not listed. Trailing `null`s are "
        "omitted. For instance `3 9 20 null null 15 7` describes a root `3` with children `9` and `20`, where `20` has "
        "children `15` and `7`."
    ),
    input_format="The first line contains `m`, the number of tokens. The second line contains the `m` tokens (integers or `null`). The first token is never `null`.",
    output_format="The sum of each level from the root downwards, separated by spaces.",
    constraints="- 1 ≤ m ≤ 20 000\n- |value| ≤ 10^6",
    examples=(
        Example("7\n3 9 20 null null 15 7\n", "3 29 22\n", "Level 0: 3. Level 1: 9 + 20 = 29. Level 2: 15 + 7 = 22."),
        Example("1\n5\n", "5\n", "A tree with only a root."),
    ),
    solve=_level_solve,
    hidden=_level_hidden,
    hints=(
        "Rebuilding the whole tree is optional: you can consume the token list level by level.",
        "If the current level has `k` real nodes, the next `2k` tokens are their children (some may be `null`).",
        "Alternatively build nodes with a queue and do a breadth-first traversal, summing one full level at a time.",
    ),
    editorial="Process the tokens with a queue of real nodes. For each level, sum the values currently in the queue, then read two tokens per node to form the next level, skipping `null`. This is a breadth-first traversal driven directly by the serialization.",
    time_complexity="O(m)",
    space_complexity="O(m)",
)

# --- 14. Island Count ---------------------------------------------------------------------------


def _island_solve(text: str) -> str:
    tok = text.split()
    rows, cols = int(tok[0]), int(tok[1])
    grid = tok[2 : 2 + rows]
    seen = [[False] * cols for _ in range(rows)]
    count = 0
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] == "#" and not seen[r][c]:
                count += 1
                stack = [(r, c)]
                seen[r][c] = True
                while stack:
                    y, x = stack.pop()
                    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        ny, nx = y + dy, x + dx
                        if 0 <= ny < rows and 0 <= nx < cols and grid[ny][nx] == "#" and not seen[ny][nx]:
                            seen[ny][nx] = True
                            stack.append((ny, nx))
    return str(count)


def _grid_input(rows: list[str]) -> str:
    return joined(f"{len(rows)} {len(rows[0])}", *rows)


def _island_hidden(rng: random.Random) -> list[str]:
    def random_grid(r: int, c: int, density: float) -> list[str]:
        return ["".join("#" if rng.random() < density else "." for _ in range(c)) for _ in range(r)]

    checker = ["".join("#" if (r + c) % 2 == 0 else "." for c in range(60)) for r in range(60)]
    snake = ["#" * 59 if r % 2 == 0 else ("." * 58 + "#" if r % 4 == 1 else "#" + "." * 58) for r in range(59)]
    return [
        _grid_input(["#"]),
        _grid_input(["."]),
        _grid_input(["#.#", ".#.", "#.#"]),
        _grid_input(["###", "###"]),
        _grid_input(random_grid(12, 15, 0.45)),
        _grid_input(random_grid(100, 100, 0.5)),
        _grid_input(random_grid(150, 150, 0.6)),
        _grid_input(checker),
        _grid_input(snake),
    ]


ISLAND_COUNT = Spec(
    slug="island-count",
    title="Island Count",
    difficulty="MEDIUM",
    tags=("Graph", "DFS"),
    description=(
        "A satellite photo of an archipelago is a grid of `r` rows and `c` columns. Each cell is either land (`#`) or "
        "sea (`.`). Two land cells belong to the same island if you can walk from one to the other moving **up, down, "
        "left or right** over land only (diagonals do not connect).\n\n"
        "How many islands are in the photo?"
    ),
    input_format="The first line contains `r` and `c`. Each of the next `r` lines contains a string of `c` characters, `#` or `.`.",
    output_format="One integer: the number of islands.",
    constraints="- 1 ≤ r, c ≤ 300\n- every cell is `#` or `.`",
    examples=(
        Example("4 5\n##...\n#..#.\n...##\n.#...\n", "3\n", "Top-left cluster, the cluster in the middle right, and the lone cell at the bottom."),
        Example("2 2\n..\n..\n", "0\n", "Only sea."),
    ),
    solve=_island_solve,
    hidden=_island_hidden,
    hints=(
        "Scan the grid. The first time you meet an unvisited land cell you have found a new island.",
        "From that cell, visit every connected land cell and mark it so you never count it again (DFS or BFS).",
        "Prefer an explicit stack or queue over deep recursion — a 300 × 300 island can be 90 000 cells deep.",
    ),
    editorial="Flood fill. Iterate over all cells; whenever an unvisited `#` is found increment the counter and traverse its 4-connected component, marking visited cells. Every cell is marked once, so the total work is proportional to the grid size.",
    time_complexity="O(r · c)",
    space_complexity="O(r · c)",
)

# --- 15. Maze Runner ----------------------------------------------------------------------------


def _maze_solve(text: str) -> str:
    tok = text.split()
    rows, cols = int(tok[0]), int(tok[1])
    grid = tok[2 : 2 + rows]
    start = end = (0, 0)
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] == "S":
                start = (r, c)
            elif grid[r][c] == "E":
                end = (r, c)
    dist = {start: 0}
    queue = deque([start])
    while queue:
        y, x = queue.popleft()
        if (y, x) == end:
            return str(dist[(y, x)])
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < rows and 0 <= nx < cols and grid[ny][nx] != "#" and (ny, nx) not in dist:
                dist[(ny, nx)] = dist[(y, x)] + 1
                queue.append((ny, nx))
    return "-1"


def _maze_hidden(rng: random.Random) -> list[str]:
    def random_maze(r: int, c: int, wall: float) -> list[str]:
        grid = [["#" if rng.random() < wall else "." for _ in range(c)] for _ in range(r)]
        grid[0][0] = "S"
        grid[r - 1][c - 1] = "E"
        return ["".join(row) for row in grid]

    serpentine = []
    size = 41
    for r in range(size):
        if r % 2 == 0:
            serpentine.append("." * size)
        elif r % 4 == 1:
            serpentine.append("#" * (size - 1) + ".")
        else:
            serpentine.append("." + "#" * (size - 1))
    serpentine[0] = "S" + serpentine[0][1:]
    serpentine[-1] = serpentine[-1][:-1] + "E"
    return [
        _grid_input(["SE"]),
        _grid_input(["S#E"]),
        _grid_input(["S.", ".E"]),
        _grid_input(["S.#.", "..#.", "#...", "...E"]),
        _grid_input(random_maze(10, 12, 0.25)),
        _grid_input(random_maze(80, 80, 0.3)),
        _grid_input(random_maze(120, 120, 0.42)),
        _grid_input(serpentine),
    ]


MAZE_RUNNER = Spec(
    slug="maze-runner",
    title="Maze Runner",
    difficulty="MEDIUM",
    tags=("Graph", "BFS"),
    description=(
        "A robot vacuum is dropped at cell `S` of a warehouse floor plan and must reach the charging dock `E`. The "
        "plan is a grid where `.` is free floor, `#` is a wall and `S`/`E` are free cells. In one step the robot moves "
        "to a free cell **up, down, left or right**; it cannot pass through walls.\n\n"
        "What is the **fewest number of steps** to get from `S` to `E`? Print `-1` if the dock cannot be reached."
    ),
    input_format="The first line contains `r` and `c`. Each of the next `r` lines contains `c` characters from `S`, `E`, `.`, `#`. There is exactly one `S` and one `E`.",
    output_format="The minimum number of steps, or `-1`.",
    constraints="- 1 ≤ r, c ≤ 300\n- exactly one `S` and one `E`, and they are different cells",
    examples=(
        Example("3 4\nS..#\n.#..\n...E\n", "5\n", "Down the left side and along the bottom, or across the top and down: both take 5 steps."),
        Example("2 3\nS#E\n.#.\n", "-1\n", "The wall in the middle column separates the two halves."),
    ),
    solve=_maze_solve,
    hidden=_maze_hidden,
    hints=(
        "All steps cost the same, so exploring in *waves* from S finds shortest routes.",
        "Use a queue: pop a cell, push every unvisited free neighbour with distance + 1, and stop when you pop E.",
    ),
    editorial="Breadth-first search from `S`. The first time `E` is dequeued its recorded distance is minimal because BFS visits cells in non-decreasing distance order. If the queue empties first, `E` is unreachable.",
    time_complexity="O(r · c)",
    space_complexity="O(r · c)",
)

# --- 16. Hot Words ------------------------------------------------------------------------------


def _hot_solve(text: str) -> str:
    tok = text.split()
    n, k = int(tok[0]), int(tok[1])
    counts = Counter(tok[2 : 2 + n])
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:k]
    return "\n".join(f"{word} {count}" for word, count in ranked)


def _hot_hidden(rng: random.Random) -> list[str]:
    pool = ["".join(rng.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(rng.randint(1, 8))) for _ in range(400)]
    pool = list(dict.fromkeys(pool))
    weights = [1 / (rank + 1) for rank in range(len(pool))]

    def make(words: list[str], k: int) -> str:
        return joined(f"{len(words)} {k}", " ".join(words))

    zipf = rng.choices(pool, weights=weights, k=20000)
    uniform = [rng.choice(pool[:50]) for _ in range(5000)]
    return [
        make(["only"], 1),
        make(["b", "a", "b", "a"], 2),
        make(["x", "y", "z"], 3),
        make(["dog", "cat", "dog", "cat", "bird"], 2),
        make(zipf, 10),
        make(zipf, len(set(zipf))),
        make(uniform, 25),
        make(["same"] * 10000, 1),
    ]


HOT_WORDS = Spec(
    slug="hot-words",
    title="Hot Words",
    difficulty="MEDIUM",
    tags=("Heap", "HashMap", "Sorting"),
    description=(
        "A news site wants to show its **k hottest words** of the day. You are given every word that appeared in the "
        "headlines. Rank the words by how many times they appeared (**more is hotter**). If two words appeared the "
        "same number of times, the one that comes **first alphabetically** ranks higher.\n\n"
        "Print the top `k` words together with their counts."
    ),
    input_format="The first line contains `n` (number of words) and `k`. The second line contains the `n` words separated by spaces.",
    output_format="`k` lines, each `word count`, hottest first.",
    constraints="- 1 ≤ n ≤ 100 000\n- 1 ≤ k ≤ number of distinct words\n- each word has 1–20 lowercase letters",
    examples=(
        Example("6 2\nbanana apple banana cherry apple banana\n", "banana 3\napple 2\n", "banana appears 3 times, apple twice, cherry once."),
        Example("5 3\nb a c a b\n", "a 2\nb 2\nc 1\n", "`a` and `b` tie on count, so alphabetical order decides."),
    ),
    solve=_hot_solve,
    hidden=_hot_hidden,
    hints=(
        "First count how often each word occurs with a hash map.",
        "Sorting all distinct words by (−count, word) is fine here. For an even faster variant with huge vocabularies, keep a heap of size k.",
    ),
    editorial="Count with a dictionary, then sort the (word, count) pairs by descending count and ascending word and take the first `k`. Using a min-heap of size `k` instead gives O(d log k) for `d` distinct words.",
    time_complexity="O(n + d log d)",
    space_complexity="O(d)",
)

# --- 17. Fewest Coins ---------------------------------------------------------------------------


def _coins_solve(text: str) -> str:
    tok = text.split()
    n, amount = int(tok[0]), int(tok[1])
    coins = list(map(int, tok[2 : 2 + n]))
    inf = amount + 1
    best = [0] + [inf] * amount
    for value in range(1, amount + 1):
        for coin in coins:
            if coin <= value and best[value - coin] + 1 < best[value]:
                best[value] = best[value - coin] + 1
    return "-1" if best[amount] >= inf else str(best[amount])


def _coins_hidden(rng: random.Random) -> list[str]:
    def make(coins: list[int], amount: int) -> str:
        return joined(f"{len(coins)} {amount}", nums(coins))

    many = rng.sample(range(2, 10000), 100)
    return [
        make([2], 1),
        make([1], 0),
        make([5], 5),
        make([2, 5], 3),
        make([1, 3, 4], 6),
        make([186, 419, 83, 408], 6249),
        make([7, 13], 12),
        make(many, 9999),
        make([1, 2, 5, 10, 20, 50, 100, 200], 10000),
    ]


FEWEST_COINS = Spec(
    slug="fewest-coins",
    title="Fewest Coins",
    difficulty="MEDIUM",
    tags=("Dynamic Programming",),
    description=(
        "The Kingdom of Sahu mints `n` kinds of coins, with values `c[1] … c[n]`. Every kind is available in **unlimited "
        "supply**. A merchant needs to pay **exactly** `A` gold using as **few coins** as possible.\n\n"
        "Print the minimum number of coins, or `-1` if the amount cannot be made with the available coins. Paying "
        "zero gold takes zero coins."
    ),
    input_format="The first line contains `n` and `A`. The second line contains the `n` coin values.",
    output_format="The minimum number of coins, or `-1`.",
    constraints="- 1 ≤ n ≤ 100\n- 1 ≤ c[i] ≤ 10 000, all different\n- 0 ≤ A ≤ 10 000",
    examples=(
        Example("3 11\n1 2 5\n", "3\n", "5 + 5 + 1 uses three coins; no combination uses fewer."),
        Example("1 3\n2\n", "-1\n", "Only even amounts can be made with 2-gold coins."),
    ),
    solve=_coins_solve,
    hidden=_coins_hidden,
    hints=(
        "Greedily taking the biggest coin does not always work (try coins 1, 3, 4 and amount 6).",
        "Let best[v] be the fewest coins to make v. How does best[v] relate to best[v − coin] for each coin?",
    ),
    editorial="Bottom-up DP: `best[0] = 0`, and for every value `v ≥ 1`, `best[v] = 1 + min(best[v − c])` over coins `c ≤ v` with `best[v − c]` finite. The answer is `best[A]` or `-1` if it is infinite.",
    time_complexity="O(n · A)",
    space_complexity="O(A)",
)

# --- 18. Paren Forge ----------------------------------------------------------------------------


def _paren_solve(text: str) -> str:
    n = int(text.split()[0])
    out: list[str] = []

    def build(current: str, opened: int, closed: int) -> None:
        if len(current) == 2 * n:
            out.append(current)
            return
        if opened < n:
            build(current + "(", opened + 1, closed)
        if closed < opened:
            build(current + ")", opened, closed + 1)

    build("", 0, 0)
    return "\n".join(out)


PAREN_FORGE = Spec(
    slug="paren-forge",
    title="Paren Forge",
    difficulty="MEDIUM",
    tags=("Backtracking", "String"),
    description=(
        "A blacksmith forges chains of `n` pairs of brackets. A chain is **well-formed** if every `(` is later closed "
        "by a `)` and no `)` appears before its matching `(`, like `(())()`.\n\n"
        "List **every** well-formed chain of exactly `n` pairs, one per line, in **alphabetical order** (`(` comes "
        "before `)`)."
    ),
    input_format="A single integer `n`.",
    output_format="All well-formed strings with `n` pairs of brackets, one per line, in lexicographic order.",
    constraints="- 1 ≤ n ≤ 8 (there are at most 1 430 answers)",
    examples=(
        Example("3\n", "((()))\n(()())\n(())()\n()(())\n()()()\n", "The five well-formed chains with three pairs."),
        Example("1\n", "()\n", "Only one chain."),
    ),
    solve=_paren_solve,
    hidden=lambda rng: [f"{n}\n" for n in (2, 4, 5, 6, 7, 8)],
    hints=(
        "Build the string one character at a time. When may you still add a `(`? When may you add a `)`?",
        "You may add `(` while fewer than n have been used, and `)` only while it would not close more than were opened.",
        "Trying `(` before `)` at every step produces the strings already in alphabetical order.",
    ),
    editorial="Backtracking with two counters, `opened` and `closed`. Append `(` if `opened < n`; append `)` if `closed < opened`. When the string reaches length `2n` it is complete. Exploring `(` first yields lexicographic order automatically. The number of results is the n-th Catalan number.",
    time_complexity="O(Catalan(n) · n)",
    space_complexity="O(n)",
)

# --- 19. Max Bookings ---------------------------------------------------------------------------


def _bookings_solve(text: str) -> str:
    tok = list(map(int, text.split()))
    n = tok[0]
    intervals = sorted(((tok[1 + 2 * i], tok[2 + 2 * i]) for i in range(n)), key=lambda iv: (iv[1], iv[0]))
    count = 0
    free_at = -(10**18)
    for start, end in intervals:
        if start >= free_at:
            count += 1
            free_at = end
    return str(count)


def _bookings_hidden(rng: random.Random) -> list[str]:
    def make(intervals: list[tuple[int, int]]) -> str:
        return joined(len(intervals), *[f"{s} {e}" for s, e in intervals])

    def random_intervals(n: int, span: int, longest: int) -> list[tuple[int, int]]:
        out = []
        for _ in range(n):
            s = rng.randint(0, span)
            out.append((s, s + rng.randint(1, longest)))
        return out

    return [
        make([(1, 2)]),
        make([(1, 5), (2, 3), (3, 4)]),
        make([(1, 2), (2, 3), (3, 4), (4, 5)]),
        make([(0, 10), (0, 10), (0, 10)]),
        make([(1, 4), (2, 6), (5, 7), (6, 9), (8, 10)]),
        make(random_intervals(50, 100, 15)),
        make(random_intervals(20000, 10**6, 200)),
        make(random_intervals(20000, 1000, 500)),
    ]


MAX_BOOKINGS = Spec(
    slug="max-bookings",
    title="Max Bookings",
    difficulty="MEDIUM",
    tags=("Greedy", "Sorting"),
    description=(
        "A tiny recording studio has a single room. Bands request time slots `[start, end)`: the band arrives at "
        "`start` and leaves at `end`. Two bookings **clash** only if their times overlap; a band may start at exactly "
        "the moment the previous band leaves.\n\n"
        "The owner wants to accept as **many** requests as possible. What is the largest number of bookings that can "
        "be accepted without a clash?"
    ),
    input_format="The first line contains `n`. Each of the next `n` lines contains `start end`.",
    output_format="One integer: the maximum number of non-overlapping bookings.",
    constraints="- 1 ≤ n ≤ 100 000\n- 0 ≤ start < end ≤ 10^9",
    examples=(
        Example("4\n1 3\n2 4\n3 5\n4 6\n", "2\n", "For example take [1,3) and [3,5). Taking [2,4) and [4,6) is equally good."),
        Example("3\n1 10\n2 3\n4 5\n", "2\n", "Skip the long booking and accept the two short ones."),
    ),
    solve=_bookings_solve,
    hidden=_bookings_hidden,
    hints=(
        "Which booking should you accept first to leave the most room for the others?",
        "Not the earliest start, not the shortest — think about the one that *finishes* earliest.",
        "Sort by end time and greedily accept every request that starts at or after the end of the last accepted one.",
    ),
    editorial="Sort intervals by end time. Keep `free_at`, the end of the last accepted booking. For each interval in order, if `start ≥ free_at` accept it and set `free_at = end`. Finishing earliest can never hurt the remaining choices (exchange argument), so the greedy is optimal.",
    time_complexity="O(n log n)",
    space_complexity="O(n)",
)

# --- 20. Rotated Dial Search --------------------------------------------------------------------


def _rotated_solve(text: str) -> str:
    tok = list(map(int, text.split()))
    n, target = tok[0], tok[1]
    a = tok[2 : 2 + n]
    lo, hi = 0, n - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if a[mid] == target:
            return str(mid)
        if a[lo] <= a[mid]:
            if a[lo] <= target < a[mid]:
                hi = mid - 1
            else:
                lo = mid + 1
        elif a[mid] < target <= a[hi]:
            lo = mid + 1
        else:
            hi = mid - 1
    return "-1"


def _rotated_hidden(rng: random.Random) -> list[str]:
    def make(sorted_values: list[int], shift: int, target: int) -> str:
        rotated = sorted_values[shift:] + sorted_values[:shift]
        return joined(f"{len(rotated)} {target}", nums(rotated))

    base = sorted(rng.sample(range(-10**9, 10**9), 20000))
    small = [2, 4, 6, 8, 10, 12, 14]
    return [
        make([1], 0, 1),
        make([1], 0, 2),
        make([1, 3], 1, 3),
        make(small, 0, 12),
        make(small, 3, 2),
        make(small, 5, 9),
        make(base, 7345, base[123]),
        make(base, 19999, base[19999]),
        make(base, 10000, 123456789 if 123456789 not in base else 123456788),
    ]


ROTATED_DIAL_SEARCH = Spec(
    slug="rotated-dial-search",
    title="Rotated Dial Search",
    difficulty="MEDIUM",
    tags=("Binary Search", "Searching", "Array"),
    description=(
        "A safe's dial has `n` distinct numbers engraved around it in increasing order. Someone rotated the dial by an "
        "unknown amount, so what you read from the marked start is a sorted list that was **cut somewhere and its two "
        "parts swapped**, for example `4 5 6 7 0 1 2` from `0 1 2 4 5 6 7`.\n\n"
        "Find the position (0-based) of a target number in this rotated list, or `-1` if it is not there. Your solution "
        "must take **O(log n)** time."
    ),
    input_format="The first line contains `n` and the target `t`. The second line contains the `n` numbers of the rotated list.",
    output_format="The index of `t`, or `-1`.",
    constraints="- 1 ≤ n ≤ 100 000\n- all numbers are distinct, |value| ≤ 10^9",
    examples=(
        Example("7 0\n4 5 6 7 0 1 2\n", "4\n", "0 is at index 4."),
        Example("7 3\n4 5 6 7 0 1 2\n", "-1\n", "3 does not appear."),
    ),
    solve=_rotated_solve,
    hidden=_rotated_hidden,
    hints=(
        "After cutting the list at `mid`, at least one of the two halves is still perfectly sorted.",
        "Decide which half is sorted by comparing a[lo] with a[mid], then check whether the target lies inside that sorted half.",
    ),
    editorial="Modified binary search. At each step one of `[lo, mid]` or `[mid, hi]` is sorted. If the target lies within the sorted half's value range, search that half; otherwise search the other. Halving the range each time gives O(log n).",
    time_complexity="O(log n)",
    space_complexity="O(1)",
)

# --- 21. Friend Circles -------------------------------------------------------------------------


def _circles_solve(text: str) -> str:
    tok = list(map(int, text.split()))
    n, m = tok[0], tok[1]
    parent = list(range(n + 1))
    size = [1] * (n + 1)

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(m):
        a, b = find(tok[2 + 2 * i]), find(tok[3 + 2 * i])
        if a != b:
            if size[a] < size[b]:
                a, b = b, a
            parent[b] = a
            size[a] += size[b]
    roots = {find(x) for x in range(1, n + 1)}
    return f"{len(roots)} {max(size[r] for r in roots)}"


def _circles_hidden(rng: random.Random) -> list[str]:
    def make(n: int, pairs: list[tuple[int, int]]) -> str:
        return joined(f"{n} {len(pairs)}", *[f"{a} {b}" for a, b in pairs])

    n = 60000
    random_pairs = []
    for _ in range(30000):
        a, b = rng.sample(range(1, n + 1), 2)
        random_pairs.append((a, b))
    chain = [(i, i + 1) for i in range(1, 20000)]
    return [
        make(1, []),
        make(4, [(1, 2), (2, 1), (1, 2)]),
        make(5, [(1, 2), (3, 4), (2, 3), (4, 5)]),
        make(6, [(1, 6), (2, 5), (3, 4)]),
        make(8, [(1, 2), (2, 3), (3, 1), (5, 6)]),
        make(n, random_pairs),
        make(20000, chain),
        make(20000, list(reversed(chain))),
    ]


FRIEND_CIRCLES = Spec(
    slug="friend-circles",
    title="Friend Circles",
    difficulty="MEDIUM",
    tags=("Union Find", "Graph"),
    description=(
        "In a school of `n` students (numbered 1 to `n`), `m` friendships are announced. Friendship is **transitive "
        "for gossip**: if `a` is friends with `b`, and `b` with `c`, then all three belong to the same *friend "
        "circle*, even if `a` and `c` never met. A student with no friends forms a circle on their own.\n\n"
        "After all announcements, report how many circles there are and the size of the largest one."
    ),
    input_format="The first line contains `n` and `m`. Each of the next `m` lines contains a friendship `a b`.",
    output_format="Two integers: the number of circles and the size of the largest circle.",
    constraints="- 1 ≤ n ≤ 100 000\n- 0 ≤ m ≤ 200 000\n- 1 ≤ a, b ≤ n; the same pair may be announced more than once",
    examples=(
        Example("6 3\n1 2\n2 3\n4 5\n", "3 3\n", "Circles: {1,2,3}, {4,5} and {6}. The largest has 3 students."),
        Example("3 0\n", "3 1\n", "No friendships: everyone is alone."),
    ),
    solve=_circles_solve,
    hidden=_circles_hidden,
    hints=(
        "Think of students as nodes and friendships as edges; circles are connected components.",
        "A disjoint-set (union–find) structure merges two groups in nearly constant time.",
        "Keep a size per root; the size of the merged group is the sum of the two sizes.",
    ),
    editorial="Union–find with path compression and union by size. Process every friendship with `union(a, b)`. Afterwards the number of distinct roots is the number of circles, and the maximum stored size among roots is the largest circle.",
    time_complexity="O((n + m) · α(n))",
    space_complexity="O(n)",
)

# --- 22. Vault Combination ----------------------------------------------------------------------


def _vault_solve(text: str) -> str:
    tok = list(map(int, text.split()))
    t = tok[0]
    return "\n".join(str(pow(tok[1 + 3 * i], tok[2 + 3 * i], tok[3 + 3 * i])) for i in range(t))


def _vault_hidden(rng: random.Random) -> list[str]:
    def make(queries: list[tuple[int, int, int]]) -> str:
        return joined(len(queries), *[f"{a} {b} {m}" for a, b, m in queries])

    randoms = [(rng.randint(0, 10**18), rng.randint(0, 10**18), rng.randint(1, 10**9)) for _ in range(2000)]
    return [
        make([(0, 0, 7)]),
        make([(9, 4, 1)]),
        make([(2, 62, 10**9)]),
        make([(10**18, 10**18, 10**9)]),
        make([(123456789, 0, 1000)]),
        make([(999999999, 999999999999999999, 1000000000)]),
        make([(7, 1, 100), (2, 2, 3), (10, 9, 6)]),
        make(randoms),
    ]


VAULT_COMBINATION = Spec(
    slug="vault-combination",
    title="Vault Combination",
    difficulty="MEDIUM",
    tags=("Math",),
    description=(
        "The vault's combination for each day is `a^b mod m`: raise the number `a` to the power `b`, then keep only the "
        "remainder after dividing by `m`. Unfortunately `b` can be as large as 10^18, so multiplying `a` by itself "
        "`b` times is hopeless.\n\n"
        "For each of `t` days compute the combination. By convention `a^0 = 1` (including `0^0`), and any number "
        "modulo `1` is `0`."
    ),
    input_format="The first line contains `t`. Each of the next `t` lines contains `a b m`.",
    output_format="`t` lines: the value of `a^b mod m` for each day.",
    constraints="- 1 ≤ t ≤ 100 000\n- 0 ≤ a, b ≤ 10^18\n- 1 ≤ m ≤ 10^9\n- Beware of overflow in 64-bit arithmetic when multiplying",
    examples=(
        Example("3\n2 10 1000\n3 200 13\n7 0 5\n", "24\n9\n1\n", "2^10 = 1024 → 24. 3^3 ≡ 1 (mod 13), so 3^200 = 3^(3·66+2) ≡ 3^2 = 9. 7^0 = 1."),
        Example("1\n5 3 1\n", "0\n", "Anything modulo 1 is 0."),
    ),
    solve=_vault_solve,
    hidden=_vault_hidden,
    hints=(
        "Reduce `a` modulo `m` first, so the numbers you multiply stay below m.",
        "Use the identity a^(2k) = (a^k)² and a^(2k+1) = a · (a^k)². That needs only about log₂(b) multiplications.",
        "Take the remainder after every multiplication. In C++ a product of two numbers below 10^9 fits in a 64-bit integer.",
    ),
    editorial="Binary (square-and-multiply) exponentiation: process the bits of `b`, squaring the base each step and multiplying it into the result when the bit is set, reducing modulo `m` after every multiplication. That is O(log b) per query.",
    time_complexity="O(t · log b)",
    space_complexity="O(1)",
)

MEDIUM = [
    LONGEST_FRESH_STRETCH,
    SHORTEST_SUPPLY_RUN,
    LEVEL_SUMS,
    ISLAND_COUNT,
    MAZE_RUNNER,
    HOT_WORDS,
    FEWEST_COINS,
    PAREN_FORGE,
    MAX_BOOKINGS,
    ROTATED_DIAL_SEARCH,
    FRIEND_CIRCLES,
    VAULT_COMBINATION,
]

# Names referenced only to keep linters quiet about optional helpers used by some generators.
_ = (heapq, bisect_left)
