"""Eight HARD problems. All statements are original."""

from __future__ import annotations

import heapq
import random
from bisect import bisect_left
from collections import defaultdict, deque

from .spec import Example, Spec, joined, nums

# --- 23. Peak Window ----------------------------------------------------------------------------


def _peak_solve(text: str) -> str:
    tok = list(map(int, text.split()))
    n, k = tok[0], tok[1]
    a = tok[2 : 2 + n]
    window: deque[int] = deque()  # indices, values strictly decreasing
    out: list[int] = []
    for i, value in enumerate(a):
        while window and a[window[-1]] <= value:
            window.pop()
        window.append(i)
        if window[0] <= i - k:
            window.popleft()
        if i >= k - 1:
            out.append(a[window[0]])
    return nums(out)


def _peak_hidden(rng: random.Random) -> list[str]:
    def make(a: list[int], k: int) -> str:
        return joined(f"{len(a)} {k}", nums(a))

    big = [rng.randint(-10**9, 10**9) for _ in range(20000)]
    return [
        make([4, 2, 12, 11, -5], 2),
        make([7], 1),
        make([1, 2, 3, 4, 5], 5),
        make([5, 4, 3, 2, 1], 3),
        make([1, 3, 1, 2, 0, 5], 3),
        make([2, 2, 2, 2], 2),
        make(big, 1),
        make(big, 500),
        make(sorted(big), 1000),
        make(sorted(big, reverse=True), 1000),
    ]


PEAK_WINDOW = Spec(
    slug="peak-window",
    title="Peak Window",
    difficulty="HARD",
    tags=("Queue", "Sliding Window", "Array"),
    description=(
        "A wind farm records the wind speed at every minute of the day, `n` readings in total. For safety planning the "
        "engineers look at every **window of `k` consecutive minutes** and want the **strongest gust** in that window.\n\n"
        "Slide the window from the start of the day to the end, one minute at a time, and report the maximum reading "
        "inside each position of the window. With up to 100 000 readings and windows as wide as the whole day, "
        "recomputing each maximum from scratch will not be fast enough."
    ),
    input_format="The first line contains `n` and `k`. The second line contains the `n` readings.",
    output_format="`n − k + 1` integers separated by spaces: the maximum of each window.",
    constraints="- 1 ≤ k ≤ n ≤ 100 000\n- |reading| ≤ 10^9",
    examples=(
        Example("8 3\n1 3 -1 -3 5 3 6 7\n", "3 3 5 5 6 7\n", "The windows are [1 3 -1], [3 -1 -3], [-1 -3 5], [-3 5 3], [5 3 6], [3 6 7]."),
        Example("1 1\n9\n", "9\n", "A single window containing one reading."),
    ),
    solve=_peak_solve,
    hidden=_peak_hidden,
    hints=(
        "Rescanning k values for every window costs O(n·k). Can you reuse work between neighbouring windows?",
        "If a newer reading is at least as large as an older one in the window, the older one can never be a maximum again.",
        "Keep a deque of *indices* whose values are decreasing. The front is always the current maximum; drop it when it falls out of the window.",
    ),
    editorial="Monotonic deque. Maintain indices of candidate maxima with strictly decreasing values. For each new index: pop from the back while the back value ≤ the new value; push the new index; pop from the front if it is outside the window. Once the first full window is reached, the front of the deque is the window maximum. Each index is pushed and popped at most once.",
    time_complexity="O(n)",
    space_complexity="O(k)",
)

# --- 24. Word Morph -----------------------------------------------------------------------------


def _morph_solve(text: str) -> str:
    lines = text.split("\n")
    a = lines[0]
    b = lines[1] if len(lines) > 1 else ""
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return str(previous[-1])


def _morph_hidden(rng: random.Random) -> list[str]:
    def word(length: int, alphabet: str) -> str:
        return "".join(rng.choice(alphabet) for _ in range(length))

    base = word(700, "abcd")
    mutated = list(base)
    for _ in range(90):
        mutated[rng.randrange(len(mutated))] = rng.choice("abcd")
    return [
        joined("", "abc"),
        joined("abc", ""),
        joined("", ""),
        joined("intention", "execution"),
        joined("same", "same"),
        joined("abcdef", "azced"),
        joined("horse", "ros"),
        joined(base, "".join(mutated)),
        joined(word(1200, "abc"), word(1100, "abc")),
        joined(word(1500, "abcdefghij"), word(1500, "abcdefghij")),
    ]


WORD_MORPH = Spec(
    slug="word-morph",
    title="Word Morph",
    difficulty="HARD",
    tags=("Dynamic Programming", "String"),
    description=(
        "A spell-checker suggests corrections by measuring how far two words are from each other. The distance is the "
        "**smallest number of edits** needed to turn the first word into the second, where one edit is any of:\n\n"
        "- **insert** a letter anywhere,\n- **delete** a letter,\n- **replace** a letter with a different one.\n\n"
        "Compute the distance between two words. Either word may be empty."
    ),
    input_format="Two lines: the first word, then the second word (a line is empty for an empty word).",
    output_format="One integer: the minimum number of edits.",
    constraints="- 0 ≤ length of each word ≤ 2 000\n- lowercase English letters only",
    examples=(
        Example("kitten\nsitting\n", "3\n", "kitten → sitten (replace k) → sittin (replace e) → sitting (insert g)."),
        Example("flaw\nlawn\n", "2\n", "Delete `f`, then insert `n`."),
    ),
    solve=_morph_solve,
    hidden=_morph_hidden,
    hints=(
        "Let d[i][j] be the distance between the first i letters of A and the first j letters of B. What are the base cases when i or j is 0?",
        "If the i-th letter of A equals the j-th of B, the last letters need no edit: d[i][j] = d[i−1][j−1]. Otherwise consider the three edits.",
        "You only ever need the previous row, so two rows of memory suffice.",
    ),
    editorial="Levenshtein DP. `d[i][0] = i`, `d[0][j] = j`, and `d[i][j] = min(d[i−1][j] + 1, d[i][j−1] + 1, d[i−1][j−1] + (A[i] ≠ B[j]))`. The answer is `d[|A|][|B|]`. Row-by-row evaluation keeps memory at O(min(|A|, |B|)).",
    time_complexity="O(|A| · |B|)",
    space_complexity="O(min(|A|, |B|))",
)

# --- 25. Cheapest Route -------------------------------------------------------------------------


def _route_solve(text: str) -> str:
    tok = list(map(int, text.split()))
    n, m = tok[0], tok[1]
    graph: list[list[tuple[int, int]]] = [[] for _ in range(n + 1)]
    for i in range(m):
        u, v, w = tok[2 + 3 * i], tok[3 + 3 * i], tok[4 + 3 * i]
        graph[u].append((v, w))
    inf = float("inf")
    dist = [inf] * (n + 1)
    dist[1] = 0
    heap = [(0, 1)]
    while heap:
        d, u = heapq.heappop(heap)
        if d > dist[u]:
            continue
        if u == n:
            return str(d)
        for v, w in graph[u]:
            if d + w < dist[v]:
                dist[v] = d + w
                heapq.heappush(heap, (dist[v], v))
    return "-1"


def _route_hidden(rng: random.Random) -> list[str]:
    def make(n: int, edges: list[tuple[int, int, int]]) -> str:
        return joined(f"{n} {len(edges)}", *[f"{u} {v} {w}" for u, v, w in edges])

    def random_graph(n: int, m: int, max_w: int) -> list[tuple[int, int, int]]:
        edges = [(i, i + 1, rng.randint(1, max_w)) for i in range(1, n) if rng.random() < 0.9]
        while len(edges) < m:
            u, v = rng.randint(1, n), rng.randint(1, n)
            edges.append((u, v, rng.randint(0, max_w)))
        return edges

    return [
        make(1, []),
        make(2, [(1, 2, 0)]),
        make(3, [(1, 2, 5), (3, 2, 1)]),
        make(4, [(1, 2, 1), (1, 3, 10), (2, 3, 1), (3, 4, 1), (2, 4, 5)]),
        make(5, [(1, 2, 2), (2, 3, 2), (3, 5, 2), (1, 4, 1), (4, 5, 10), (5, 1, 1)]),
        make(4, [(2, 1, 3), (3, 2, 3), (4, 3, 3)]),
        make(200, random_graph(200, 800, 50)),
        make(6000, random_graph(6000, 12000, 10**6)),
        make(6000, [(i, i + 1, 10**9) for i in range(1, 6000)]),
    ]


CHEAPEST_ROUTE = Spec(
    slug="cheapest-route",
    title="Cheapest Route",
    difficulty="HARD",
    tags=("Graph", "Heap"),
    description=(
        "A courier company operates between `n` depots numbered 1 to `n`. There are `m` **one-way** roads; the road from "
        "`u` to `v` costs `w` in fuel. A parcel starts at depot **1** and must reach depot **n**.\n\n"
        "Find the **minimum total fuel cost** of a route from depot 1 to depot `n`, or `-1` if depot `n` cannot be "
        "reached. Roads may be listed in any order, several roads may connect the same depots, and a road may cost "
        "**zero**."
    ),
    input_format="The first line contains `n` and `m`. Each of the next `m` lines contains `u v w`, a one-way road from `u` to `v` costing `w`.",
    output_format="The minimum fuel cost from depot 1 to depot n, or `-1`.",
    constraints="- 1 ≤ n ≤ 100 000\n- 0 ≤ m ≤ 200 000\n- 0 ≤ w ≤ 10^9 (totals can exceed 32-bit integers)",
    examples=(
        Example("4 5\n1 2 1\n1 3 4\n2 3 2\n2 4 6\n3 4 3\n", "6\n", "1 → 2 → 3 → 4 costs 1 + 2 + 3 = 6, cheaper than 1 → 2 → 4 (7)."),
        Example("3 1\n1 2 5\n", "-1\n", "There is no road that leads to depot 3."),
    ),
    solve=_route_solve,
    hidden=_route_hidden,
    hints=(
        "All costs are non-negative, so once you have found the cheapest way to a depot, no later discovery can improve it.",
        "Repeatedly settle the not-yet-settled depot with the smallest known cost, and relax its outgoing roads.",
        "A priority queue (min-heap) keyed by cost finds that depot in O(log n). Skip stale heap entries.",
    ),
    editorial="Dijkstra's algorithm with a binary heap. Maintain `dist[]`, initially infinite except `dist[1] = 0`. Pop the smallest `(d, u)`; ignore it if `d > dist[u]`; otherwise relax each edge `(u, v, w)`. The first time depot `n` is popped its distance is optimal. Use 64-bit integers for distances.",
    time_complexity="O((n + m) log n)",
    space_complexity="O(n + m)",
)

# --- 26. Queens Standoff ------------------------------------------------------------------------


def _queens_solve(text: str) -> str:
    n = int(text.split()[0])
    full = (1 << n) - 1

    def place(cols: int, diag1: int, diag2: int) -> int:
        if cols == full:
            return 1
        total = 0
        free = full & ~(cols | diag1 | diag2)
        while free:
            bit = free & -free
            free ^= bit
            total += place(cols | bit, ((diag1 | bit) << 1) & full, (diag2 | bit) >> 1)
        return total

    return str(place(0, 0, 0))


QUEENS_STANDOFF = Spec(
    slug="queens-standoff",
    title="Queens Standoff",
    difficulty="HARD",
    tags=("Backtracking",),
    description=(
        "On an `n × n` chessboard you must place `n` queens so that **no two attack each other**. Two queens attack "
        "each other if they share a **row**, a **column** or a **diagonal**.\n\n"
        "Count the number of different ways to place the queens. Two placements are different if some square holds a "
        "queen in one and not in the other (rotations and reflections count separately)."
    ),
    input_format="A single integer `n`.",
    output_format="The number of valid placements.",
    constraints="- 1 ≤ n ≤ 10",
    examples=(
        Example("4\n", "2\n", "The two solutions on a 4 × 4 board are mirror images of each other."),
        Example("6\n", "4\n", "A 6 × 6 board has four solutions."),
    ),
    solve=_queens_solve,
    hidden=lambda rng: [f"{n}\n" for n in (1, 2, 3, 5, 7, 8, 9, 10)],
    hints=(
        "Place one queen per row, and decide only *which column* to use in each row.",
        "Remember which columns and which two kinds of diagonals are already attacked, so each check is O(1).",
        "Bitmasks work well: one integer for columns, one for '\\' diagonals, one for '/' diagonals, shifted as you go down a row.",
    ),
    editorial="Backtracking row by row. Keep three bitmasks: attacked columns, attacked '\\' diagonals and attacked '/' diagonals. The free squares of the current row are the bits not set in any mask; try each, shifting the diagonal masks for the next row. Counting every complete placement gives the answer (1, 0, 0, 2, 10, 4, 40, 92, 352, 724 for n = 1…10).",
    time_complexity="O(n!) in the worst case, far less with pruning",
    space_complexity="O(n)",
)

# --- 27. Prefix Directory -----------------------------------------------------------------------


def _directory_solve(text: str) -> str:
    tok = text.split()
    n, q = int(tok[0]), int(tok[1])
    counts: dict[str, int] = defaultdict(int)
    for word in tok[2 : 2 + n]:
        for end in range(1, len(word) + 1):
            counts[word[:end]] += 1
    return "\n".join(str(counts.get(prefix, 0)) for prefix in tok[2 + n : 2 + n + q])


def _directory_hidden(rng: random.Random) -> list[str]:
    def word(alphabet: str, low: int, high: int) -> str:
        return "".join(rng.choice(alphabet) for _ in range(rng.randint(low, high)))

    def make(words: list[str], prefixes: list[str]) -> str:
        return joined(f"{len(words)} {len(prefixes)}", " ".join(words), " ".join(prefixes))

    dense = [word("abc", 1, 10) for _ in range(15000)]
    dense_queries = [word("abc", 1, 6) for _ in range(4000)] + [rng.choice(dense)[: rng.randint(1, 4)] for _ in range(1000)]
    sparse = [word("abcdefghijklmnopqrstuvwxyz", 3, 12) for _ in range(8000)]
    sparse_queries = [w[: rng.randint(1, len(w))] for w in rng.sample(sparse, 3000)] + [word("xyz", 4, 8) for _ in range(500)]
    return [
        make(["a"], ["a", "b", "aa"]),
        make(["ab", "ab", "abc"], ["a", "ab", "abc", "abcd"]),
        make(["same"] * 5, ["s", "same", "samey"]),
        make(["bat", "batman", "batter", "cat"], ["b", "bat", "batt", "c", "d"]),
        make(dense, dense_queries),
        make(sparse, sparse_queries),
        make(["z" * 20] * 1000, ["z" * i for i in range(1, 21)]),
    ]


PREFIX_DIRECTORY = Spec(
    slug="prefix-directory",
    title="Prefix Directory",
    difficulty="HARD",
    tags=("Trie", "String"),
    description=(
        "A phone's contact list stores `n` names (the same name may be stored several times). While the owner types "
        "the first few letters of a name, the phone should instantly say **how many stored names start with what has "
        "been typed so far**.\n\n"
        "Given the stored names and `q` typed prefixes, answer each prefix query. A name counts once for every time it "
        "is stored, and a name counts as starting with itself."
    ),
    input_format="The first line contains `n` and `q`. The second line contains the `n` names. The third line contains the `q` prefixes.",
    output_format="`q` lines: for each prefix, the number of stored names that start with it.",
    constraints="- 1 ≤ n, q ≤ 100 000\n- every name and prefix has 1–20 lowercase letters",
    examples=(
        Example("5 3\napple app apply apt banana\nap app b\n", "4\n3\n1\n", "Four names start with `ap`, three with `app` (apple, app, apply), one with `b`."),
        Example("1 2\nhello\nhelp hello\n", "0\n1\n", "`help` is not a prefix of `hello`, but `hello` is a prefix of itself."),
    ),
    solve=_directory_solve,
    hidden=_directory_hidden,
    hints=(
        "Comparing every prefix against every name is O(n·q·L) — too slow.",
        "Names sharing a prefix share the beginning of the same path in a tree of letters. Which structure stores strings like that?",
        "In a trie, store at every node how many inserted names pass through it. A query walks the prefix and reads the counter.",
    ),
    editorial="Build a trie. Inserting a name walks (or creates) one node per letter and increments a `pass` counter on each visited node. A query follows the prefix letter by letter: if the path breaks the answer is 0, otherwise it is the `pass` counter of the last node. Insertion and query cost O(length).",
    time_complexity="O((n + q) · L)",
    space_complexity="O(n · L)",
)

# --- 28. Steady Median --------------------------------------------------------------------------


def _median_solve(text: str) -> str:
    tok = list(map(int, text.split()))
    n = tok[0]
    low: list[int] = []  # max-heap (negated)
    high: list[int] = []
    out: list[int] = []
    for x in tok[1 : 1 + n]:
        if not low or x <= -low[0]:
            heapq.heappush(low, -x)
        else:
            heapq.heappush(high, x)
        if len(low) > len(high) + 1:
            heapq.heappush(high, -heapq.heappop(low))
        elif len(high) > len(low):
            heapq.heappush(low, -heapq.heappop(high))
        out.append(-low[0])
    return nums(out)


def _median_hidden(rng: random.Random) -> list[str]:
    def make(a: list[int]) -> str:
        return joined(len(a), nums(a))

    return [
        make([7]),
        make([2, 1]),
        make([1, 2, 3, 4, 5, 6]),
        make([6, 5, 4, 3, 2, 1]),
        make([4, 4, 4, 4]),
        make([-1, 5, -3, 8, 0, 0]),
        make([rng.randint(-10**9, 10**9) for _ in range(20000)]),
        make([rng.randint(0, 10) for _ in range(20000)]),
        make(list(range(20000))),
    ]


STEADY_MEDIAN = Spec(
    slug="steady-median",
    title="Steady Median",
    difficulty="HARD",
    tags=("Heap",),
    description=(
        "A sensor sends a stream of `n` integer readings. After **each** reading arrives, the monitoring dashboard "
        "must show the **median** of all readings received so far.\n\n"
        "When an even number of readings have arrived there are two middle values; the dashboard shows the **lower** "
        "one (that is, the ⌈k/2⌉-th smallest after `k` readings). Print the median after every reading."
    ),
    input_format="The first line contains `n`. The second line contains the `n` readings in order of arrival.",
    output_format="`n` integers separated by spaces: the median after each reading.",
    constraints="- 1 ≤ n ≤ 100 000\n- |reading| ≤ 10^9",
    examples=(
        Example("5\n5 15 1 3 8\n", "5 5 5 3 5\n", "After [5]: 5. After [5,15]: lower middle 5. After [1,5,15]: 5. After [1,3,5,15]: lower middle 3. After [1,3,5,8,15]: 5."),
        Example("1\n42\n", "42\n", "One reading, so it is the median."),
    ),
    solve=_median_solve,
    hidden=_median_hidden,
    hints=(
        "Re-sorting after every reading costs O(n² log n).",
        "Split the readings into a *lower half* and an *upper half*. The median is at the border between them.",
        "Keep the lower half in a max-heap and the upper half in a min-heap, and rebalance so their sizes differ by at most one.",
    ),
    editorial="Two heaps. `low` is a max-heap holding the smaller half (always at least as large as `high`), `high` is a min-heap holding the larger half. Insert each value into the proper heap, then rebalance so `len(low) − len(high)` is 0 or 1. The lower median is the top of `low`. Each step is O(log n).",
    time_complexity="O(n log n)",
    space_complexity="O(n)",
)

# --- 29. Cheapest Network -----------------------------------------------------------------------


def _network_solve(text: str) -> str:
    tok = list(map(int, text.split()))
    n, m = tok[0], tok[1]
    edges = sorted((tok[4 + 3 * i], tok[2 + 3 * i], tok[3 + 3 * i]) for i in range(m))
    parent = list(range(n + 1))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    total = used = 0
    for w, u, v in edges:
        ru, rv = find(u), find(v)
        if ru != rv:
            parent[ru] = rv
            total += w
            used += 1
    return str(total) if used == n - 1 else "-1"


def _network_hidden(rng: random.Random) -> list[str]:
    def make(n: int, edges: list[tuple[int, int, int]]) -> str:
        return joined(f"{n} {len(edges)}", *[f"{u} {v} {w}" for u, v, w in edges])

    def connected_graph(n: int, extra: int, max_w: int) -> list[tuple[int, int, int]]:
        edges = [(rng.randint(1, i - 1), i, rng.randint(1, max_w)) for i in range(2, n + 1)]
        for _ in range(extra):
            u, v = rng.sample(range(1, n + 1), 2)
            edges.append((u, v, rng.randint(1, max_w)))
        rng.shuffle(edges)
        return edges

    return [
        make(1, []),
        make(2, [(1, 2, 7), (2, 1, 3)]),
        make(4, [(1, 2, 1), (3, 4, 1)]),
        make(5, [(1, 2, 3), (2, 3, 3), (3, 1, 3), (4, 5, 1), (3, 4, 2)]),
        make(6, [(1, 2, 4), (1, 3, 4), (2, 3, 2), (3, 4, 3), (4, 5, 4), (5, 6, 5), (4, 6, 1)]),
        make(100, connected_graph(100, 300, 20)),
        make(6000, connected_graph(6000, 6000, 10**6)),
        make(6000, connected_graph(5999, 6000, 10**9)),
    ]


CHEAPEST_NETWORK = Spec(
    slug="cheapest-network",
    title="Cheapest Network",
    difficulty="HARD",
    tags=("Union Find", "Graph", "Sorting"),
    description=(
        "A village council wants to connect its `n` houses (numbered 1 to `n`) with fibre-optic cable so that **every "
        "house can reach every other**, directly or through other houses. There are `m` possible cable routes; the "
        "route between houses `u` and `v` costs `w`. Cables work in both directions.\n\n"
        "Choose routes so that all houses are connected at the **lowest possible total cost**, and print that cost. If "
        "the routes on offer cannot connect all houses, print `-1`."
    ),
    input_format="The first line contains `n` and `m`. Each of the next `m` lines contains `u v w`.",
    output_format="The minimum total cost, or `-1` if the houses cannot all be connected.",
    constraints="- 1 ≤ n ≤ 100 000\n- 0 ≤ m ≤ 200 000\n- 1 ≤ w ≤ 10^9 (the total may exceed 32 bits)",
    examples=(
        Example("4 5\n1 2 1\n2 3 2\n3 4 3\n1 4 4\n1 3 5\n", "6\n", "Use the routes costing 1, 2 and 3; the others would create needless loops."),
        Example("3 1\n1 2 5\n", "-1\n", "House 3 has no route at all."),
    ),
    solve=_network_solve,
    hidden=_network_hidden,
    hints=(
        "You never need a cable that closes a loop: it would only add cost. So you need exactly n − 1 cables.",
        "Consider the routes from cheapest to most expensive. When is it safe to take one?",
        "Take a route if it joins two houses that are not yet connected. Union–find answers 'already connected?' quickly.",
    ),
    editorial="Kruskal's algorithm. Sort routes by cost; scan them in order, and use a disjoint-set structure to add a route only if its endpoints lie in different components. The result is a minimum spanning tree with `n − 1` routes; if fewer than `n − 1` routes were added the graph is disconnected and the answer is `-1`.",
    time_complexity="O(m log m)",
    space_complexity="O(n + m)",
)

# --- 30. Steady Climb ---------------------------------------------------------------------------


def _climb_solve(text: str) -> str:
    tok = list(map(int, text.split()))
    n = tok[0]
    tails: list[int] = []
    for x in tok[1 : 1 + n]:
        position = bisect_left(tails, x)
        if position == len(tails):
            tails.append(x)
        else:
            tails[position] = x
    return str(len(tails))


def _climb_hidden(rng: random.Random) -> list[str]:
    def make(a: list[int]) -> str:
        return joined(len(a), nums(a))

    return [
        make([3]),
        make([1, 2, 3, 4, 5]),
        make([5, 4, 3, 2, 1]),
        make([2, 2, 2]),
        make([0, 8, 4, 12, 2, 10, 6, 14, 1, 9, 5, 13, 3, 11, 7, 15]),
        make([1, 3, 2, 4, 3, 5]),
        make([rng.randint(-10**9, 10**9) for _ in range(20000)]),
        make([rng.randint(0, 100) for _ in range(20000)]),
        make(list(range(20000))),
        make(list(range(20000, 0, -1))),
    ]


STEADY_CLIMB = Spec(
    slug="steady-climb",
    title="Steady Climb",
    difficulty="HARD",
    tags=("Dynamic Programming", "Binary Search"),
    description=(
        "A hiker records the altitude at each of `n` checkpoints along a ridge. She wants to know the longest possible "
        "**steady climb**: a selection of checkpoints, in the order she visits them (she may **skip** some), whose "
        "altitudes are **strictly increasing**.\n\n"
        "Print the length of the longest such selection. With `n` up to 100 000, an O(n²) approach is too slow."
    ),
    input_format="The first line contains `n`. The second line contains the `n` altitudes.",
    output_format="One integer: the length of the longest strictly increasing subsequence.",
    constraints="- 1 ≤ n ≤ 100 000\n- |altitude| ≤ 10^9",
    examples=(
        Example("8\n10 9 2 5 3 7 101 18\n", "4\n", "For example 2, 3, 7, 18 (or 2, 5, 7, 101)."),
        Example("5\n7 7 7 7 7\n", "1\n", "Altitudes must strictly increase, so equal values do not chain."),
    ),
    solve=_climb_solve,
    hidden=_climb_hidden,
    hints=(
        "A classic DP: L[i] = 1 + max(L[j]) over j < i with a[j] < a[i]. That is O(n²).",
        "Instead keep `tails[k]`, the smallest possible last value of a climb of length k + 1. This array is always sorted.",
        "For each new value, binary-search where it belongs in `tails`: replace the first entry ≥ value, or append if there is none.",
    ),
    editorial="Patience-sorting style algorithm. `tails` stays sorted, so for each altitude `x` find the first index `p` with `tails[p] ≥ x` using binary search; set `tails[p] = x` (or append if `p` is past the end). The final length of `tails` is the LIS length. `tails` is not itself the subsequence, only a set of best endings.",
    time_complexity="O(n log n)",
    space_complexity="O(n)",
)

HARD = [
    PEAK_WINDOW,
    WORD_MORPH,
    CHEAPEST_ROUTE,
    QUEENS_STANDOFF,
    PREFIX_DIRECTORY,
    STEADY_MEDIAN,
    CHEAPEST_NETWORK,
    STEADY_CLIMB,
]
