"""Ten EASY problems. All statements are original."""

from __future__ import annotations

import random
from bisect import bisect_left, bisect_right
from collections import defaultdict

from .spec import Example, Spec, joined, nums

# --- 1. Harbor Cranes ---------------------------------------------------------------------------


def _cranes_solve(text: str) -> str:
    tok = text.split()
    n, cap = int(tok[0]), int(tok[1])
    weights = list(map(int, tok[2 : 2 + n]))
    positions: dict[int, list[int]] = defaultdict(list)
    for index, weight in enumerate(weights):
        positions[weight].append(index)
    for i, weight in enumerate(weights):
        later = positions.get(cap - weight)
        if later:
            k = bisect_right(later, i)
            if k < len(later):
                return f"{i + 1} {later[k] + 1}"
    return "-1"


def _cranes_hidden(rng: random.Random) -> list[str]:
    tests = [
        joined("4 8", "3 5 3 5"),
        joined("2 4", "2 2"),
        joined("5 10", "5 1 9 5 3"),
        joined("1 5", "5"),
        joined("4 100", "1 2 3 4"),
    ]
    n = 15000
    weights = [rng.randint(1, 10**9) for _ in range(n)]
    i, j = sorted(rng.sample(range(n), 2))
    tests.append(joined(f"{n} {weights[i] + weights[j]}", nums(weights)))
    tests.append(joined(f"{n} 1", nums([rng.randint(1, 10**9) for _ in range(n)])))
    tests.append(joined(f"{n} 10", nums([rng.choice([1, 2, 3, 4, 5]) for _ in range(n)])))
    return tests


HARBOR_CRANES = Spec(
    slug="harbor-cranes",
    title="Harbor Cranes",
    difficulty="EASY",
    tags=("Array", "HashMap"),
    description=(
        "The night shift at Port Sahu has `n` shipping containers lined up on the quay. Container `i` weighs `w[i]` "
        "tonnes. The only crane that still works can lift **exactly two different containers at once**, and it is only "
        "safe when their combined weight equals the crane's rated capacity `C` exactly.\n\n"
        "Find two different containers whose weights add up to `C`. If several pairs work, report the pair with the "
        "**smallest first position**; if that still leaves a choice, take the **smallest second position**. Positions "
        "are numbered from 1 in the order the containers stand."
    ),
    input_format="The first line contains `n` and `C`. The second line contains the `n` weights.",
    output_format="Two integers `i j` with `i < j`, or `-1` if no pair adds up to `C`.",
    constraints="- 1 ≤ n ≤ 200 000\n- 1 ≤ w[i] ≤ 10^9\n- 1 ≤ C ≤ 2·10^9",
    examples=(
        Example("5 9\n2 7 11 15 1\n", "1 2\n", "The first two containers weigh 2 + 7 = 9."),
        Example("3 100\n1 2 3\n", "-1\n", "No two containers add up to 100."),
    ),
    solve=_cranes_solve,
    hidden=_cranes_hidden,
    hints=(
        "Checking every pair works, but it is far too slow for n = 200 000.",
        "When you stand at container i, exactly one weight would complete the pair: C − w[i]. Where could you look it up instantly?",
        "Remember where each weight occurs. For each i you need the *first later* occurrence of C − w[i].",
    ),
    editorial=(
        "Store, for every weight, the sorted list of positions where it appears. Walk the containers from the left; for "
        "container `i` binary-search the list for weight `C − w[i]` for the first position after `i`. The first `i` that "
        "succeeds gives the required pair. A single left-to-right pass with a hash map of *earlier* weights also finds a "
        "valid pair, but not necessarily the one with the smallest first position, which is why this version scans "
        "forward."
    ),
    time_complexity="O(n log n)",
    space_complexity="O(n)",
)

# --- 2. Mirror Message --------------------------------------------------------------------------


def _mirror_solve(text: str) -> str:
    line = text[:-1] if text.endswith("\n") else text
    kept = [c.lower() for c in line if c.isascii() and c.isalnum()]
    return "YES" if kept == kept[::-1] else "NO"


def _mirror_hidden(rng: random.Random) -> list[str]:
    letters = "abcdefghijklmnopqrstuvwxyz0123456789"
    half = "".join(rng.choice(letters) for _ in range(25000))
    noisy = "".join(c + rng.choice(["", " ", ",", "!"]) for c in half)
    broken = list(half + half[::-1])
    broken[len(half) + 7] = "#" if broken[len(half) + 7] != "#" else "@"
    near = list(half + half[::-1])
    near[123] = "A" if near[123] != "a" else "b"
    return [
        "\n",
        "!!! ... ???\n",
        "a\n",
        "Ab\n",
        "No 'x' in Nixon\n",
        "0P\n",
        noisy + noisy[::-1] + "\n",
        "".join(near) + "\n",
        "".join(broken) + "\n",
    ]


MIRROR_MESSAGE = Spec(
    slug="mirror-message",
    title="Mirror Message",
    difficulty="EASY",
    tags=("String", "Two Pointer"),
    description=(
        "A lighthouse keeper leaves notes for the next keeper, and superstition says a note only brings good weather if "
        "it reads the same forwards and backwards. The catch: only **letters and digits** count, and **capital letters "
        "match lowercase ones**. Spaces and punctuation are ignored.\n\n"
        "Decide whether a note is a *mirror message*. A note with no letters or digits at all counts as one."
    ),
    input_format="A single line containing the note (possibly empty).",
    output_format="`YES` if the note is a mirror message, otherwise `NO`.",
    constraints="- 0 ≤ length of the note ≤ 200 000\n- The note contains printable ASCII characters only",
    examples=(
        Example("A man, a plan, a canal: Panama\n", "YES\n", "Ignoring punctuation and case it reads `amanaplanacanalpanama`."),
        Example("race a car\n", "NO\n", "`raceacar` reversed is `racaecar`."),
    ),
    solve=_mirror_solve,
    hidden=_mirror_hidden,
    hints=(
        "Build a cleaned version of the note first, then compare it with its reverse.",
        "You can avoid the extra copy: keep one pointer at each end and skip anything that is not a letter or digit.",
    ),
    editorial=(
        "Two pointers, one from each end. Advance the left pointer past non-alphanumeric characters, retreat the right "
        "pointer the same way, and compare the two characters case-insensitively. If they ever differ the answer is "
        "`NO`; if the pointers meet, it is `YES`."
    ),
    time_complexity="O(n)",
    space_complexity="O(1)",
)

# --- 3. Toolbox Brackets ------------------------------------------------------------------------


def _brackets_solve(text: str) -> str:
    pairs = {")": "(", "]": "[", "}": "{"}
    stack: list[str] = []
    for ch in text.strip():
        if ch in "([{":
            stack.append(ch)
        elif not stack or stack.pop() != pairs[ch]:
            return "NO"
    return "NO" if stack else "YES"


def _brackets_hidden(rng: random.Random) -> list[str]:
    def balanced(depth_pairs: int) -> str:
        out: list[str] = []
        stack: list[str] = []
        opens = "([{"
        closes = {"(": ")", "[": "]", "{": "}"}
        remaining = depth_pairs
        while remaining or stack:
            if remaining and (not stack or rng.random() < 0.55):
                b = rng.choice(opens)
                out.append(b)
                stack.append(b)
                remaining -= 1
            else:
                out.append(closes[stack.pop()])
        return "".join(out)

    long_ok = balanced(40000)
    swapped = list(long_ok)
    swapped[len(swapped) // 2] = ")" if swapped[len(swapped) // 2] != ")" else "]"
    return [
        "\n",
        "()\n",
        "(\n",
        ")(\n",
        "[(])\n",
        "{[]}()\n",
        "((((((((((\n",
        long_ok + "\n",
        long_ok + ")\n",
        "".join(swapped) + "\n",
    ]


TOOLBOX_BRACKETS = Spec(
    slug="toolbox-brackets",
    title="Toolbox Brackets",
    difficulty="EASY",
    tags=("Stack", "String"),
    description=(
        "A mechanic labels every drawer of her toolbox with a string of brackets: `(` `)` for small parts, `[` `]` for "
        "medium ones and `{` `}` for large ones. A drawer label is **valid** when every opening bracket is closed by "
        "the *same kind* of bracket, in the correct order, and nothing is left open.\n\n"
        "For example `{[()]}` is valid, but `([)]` is not: the `[` is closed while a `(` is still open inside it. The "
        "empty label is valid."
    ),
    input_format="A single line with the label (possibly empty).",
    output_format="`YES` if the label is valid, otherwise `NO`.",
    constraints="- 0 ≤ length ≤ 100 000\n- The label only contains the characters `(` `)` `[` `]` `{` `}`",
    examples=(
        Example("{[()]}\n", "YES\n", "Each bracket closes the most recent unclosed one of the same kind."),
        Example("([)]\n", "NO\n", "The `]` arrives while `(` is the most recent unclosed bracket."),
    ),
    solve=_brackets_solve,
    hidden=_brackets_hidden,
    hints=(
        "The bracket you must close first is always the one opened most recently.",
        "A stack gives you exactly that behaviour. What should happen when you meet a closing bracket and the stack is empty?",
    ),
    editorial=(
        "Scan left to right. Push every opening bracket. For a closing bracket, the stack must be non-empty and its top "
        "must be the matching opener; pop it. After the scan the stack must be empty. Each character is handled once."
    ),
    time_complexity="O(n)",
    space_complexity="O(n)",
)

# --- 4. Winning Streak --------------------------------------------------------------------------


def _streak_solve(text: str) -> str:
    tok = text.split()
    n = int(tok[0])
    best = run = 0
    for value in tok[1 : 1 + n]:
        run = run + 1 if value == "1" else 0
        best = max(best, run)
    return str(best)


def _streak_hidden(rng: random.Random) -> list[str]:
    def make(bits: list[int]) -> str:
        return joined(len(bits), nums(bits))

    runs: list[int] = []
    while len(runs) < 30000:
        runs += [1] * rng.randint(1, 400) + [0] * rng.randint(1, 30)
    return [
        make([1]),
        make([0]),
        make([0] * 6),
        make([1] * 6),
        make([1, 0] * 10),
        make([1, 0, 1, 1, 1, 1, 0, 1, 1]),
        make(runs[:30000]),
        make([1] * 25000 + [0] + [1] * 3000),
    ]


WINNING_STREAK = Spec(
    slug="winning-streak",
    title="Winning Streak",
    difficulty="EASY",
    tags=("Array",),
    description=(
        "A chess club records every match of the season as `1` for a win and `0` for anything else. The chairperson "
        "wants to congratulate the player with the **longest winning streak** — the most wins in a row without a "
        "single non-win in between.\n\n"
        "Given the season's results in order, report the length of the longest streak. If there were no wins, the "
        "answer is `0`."
    ),
    input_format="The first line contains `n`. The second line contains `n` values, each `0` or `1`.",
    output_format="One integer: the length of the longest run of consecutive `1`s.",
    constraints="- 1 ≤ n ≤ 100 000\n- each value is `0` or `1`",
    examples=(
        Example("8\n1 1 0 1 1 1 0 1\n", "3\n", "The longest run of wins is the three in the middle."),
        Example("3\n0 0 0\n", "0\n", "There are no wins at all."),
    ),
    solve=_streak_solve,
    hidden=_streak_hidden,
    hints=("Keep a counter of the current run and reset it whenever you see a 0.", "Also remember the largest value the counter ever reached."),
    editorial=(
        "Single pass with two variables: `run` (current streak) and `best`. On `1` increment `run`; on `0` reset it to "
        "zero. After each step update `best = max(best, run)`."
    ),
    time_complexity="O(n)",
    space_complexity="O(1)",
)

# --- 5. First Lonely Letter ---------------------------------------------------------------------


def _lonely_solve(text: str) -> str:
    s = text.strip()
    counts: dict[str, int] = defaultdict(int)
    for ch in s:
        counts[ch] += 1
    for index, ch in enumerate(s, start=1):
        if counts[ch] == 1:
            return str(index)
    return "-1"


def _lonely_hidden(rng: random.Random) -> list[str]:
    letters = "abcdefghijklmnopqrstuvwxyz"
    body = [rng.choice(letters[:10]) for _ in range(25000)]
    doubled = body + body
    rng.shuffle(doubled)
    doubled.insert(rng.randint(0, len(doubled)), "z")
    everything_twice = list("abcdefghij" * 2)
    rng.shuffle(everything_twice)
    return [
        "a\n",
        "aa\n",
        "abab\n",
        "abcabcd\n",
        "zzzzzzzzzzq\n",
        "aabbccddeeffgghh\n",
        "".join(everything_twice) + "\n",
        "".join(doubled) + "\n",
    ]


FIRST_LONELY_LETTER = Spec(
    slug="first-lonely-letter",
    title="First Lonely Letter",
    difficulty="EASY",
    tags=("String", "HashMap"),
    description=(
        "In a word game, a letter is **lonely** if it appears exactly once in the whole word. Your job is to find the "
        "*first* lonely letter, reading from the left, and report where it stands.\n\n"
        "Positions are numbered from 1. If every letter appears at least twice, report `-1`."
    ),
    input_format="A single line containing a word made of lowercase letters.",
    output_format="The 1-based position of the first lonely letter, or `-1` if there is none.",
    constraints="- 1 ≤ length ≤ 100 000\n- lowercase English letters only",
    examples=(
        Example("swiss\n", "2\n", "`s` appears three times, but `w` at position 2 appears once."),
        Example("aabb\n", "-1\n", "Both letters appear twice."),
    ),
    solve=_lonely_solve,
    hidden=_lonely_hidden,
    hints=("You need two passes: one to learn how often each letter occurs, and one to find the first with a count of 1.",),
    editorial=(
        "Count the occurrences of each letter (an array of 26 counters is enough). Then scan the word again and return "
        "the position of the first letter whose count is exactly 1."
    ),
    time_complexity="O(n)",
    space_complexity="O(1)",
)

# --- 6. Merge Timetables ------------------------------------------------------------------------


def _merge_solve(text: str) -> str:
    tok = text.split()
    n, m = int(tok[0]), int(tok[1])
    a = list(map(int, tok[2 : 2 + n]))
    b = list(map(int, tok[2 + n : 2 + n + m]))
    i = j = 0
    out: list[int] = []
    while i < n and j < m:
        if a[i] <= b[j]:
            out.append(a[i])
            i += 1
        else:
            out.append(b[j])
            j += 1
    out += a[i:]
    out += b[j:]
    return nums(out)


def _merge_hidden(rng: random.Random) -> list[str]:
    def make(a: list[int], b: list[int]) -> str:
        return joined(f"{len(a)} {len(b)}", nums(a), nums(b))

    big_a = sorted(rng.randint(-10**9, 10**9) for _ in range(10000))
    big_b = sorted(rng.randint(-10**9, 10**9) for _ in range(9000))
    return [
        make([1], []),
        make([], [7]),
        make([1, 2, 3], [4, 5, 6]),
        make([4, 5, 6], [1, 2, 3]),
        make([2, 2, 2], [2, 2]),
        make([-5, 0, 5], [-6, -1, 1, 6]),
        make(big_a, big_b),
        make(list(range(10000)), list(range(0, 10000, 2))),
    ]


MERGE_TIMETABLES = Spec(
    slug="merge-timetables",
    title="Merge Timetables",
    difficulty="EASY",
    tags=("Array", "Two Pointer", "Sorting"),
    description=(
        "Two bus companies each publish their departure times for the day as a list already sorted from earliest to "
        "latest. The city wants a single combined timetable, also sorted, keeping every departure (including "
        "duplicates).\n\n"
        "Merge the two lists. Because both are already sorted, you should not need to sort the result from scratch."
    ),
    input_format="The first line contains `n` and `m`. The second line has the `n` times of the first company, the third line the `m` times of the second (a line is empty when its list is empty).",
    output_format="All `n + m` times in non-decreasing order, separated by spaces.",
    constraints="- 0 ≤ n, m ≤ 100 000 and n + m ≥ 1\n- −10^9 ≤ time ≤ 10^9\n- each input list is sorted in non-decreasing order",
    examples=(
        Example("3 3\n1 4 9\n2 3 10\n", "1 2 3 4 9 10\n", "Take whichever front value is smaller, one at a time."),
        Example("0 2\n\n5 7\n", "5 7\n", "The first company has no departures."),
    ),
    solve=_merge_solve,
    hidden=_merge_hidden,
    hints=("Keep one pointer into each list.", "Repeatedly copy the smaller of the two front elements; when one list runs out, append the rest of the other."),
    editorial="Classic merge step from merge sort with two indices. Each element is copied exactly once.",
    time_complexity="O(n + m)",
    space_complexity="O(n + m)",
)

# --- 7. Insert Position -------------------------------------------------------------------------


def _insert_solve(text: str) -> str:
    tok = text.split()
    n, q = int(tok[0]), int(tok[1])
    a = list(map(int, tok[2 : 2 + n]))
    queries = list(map(int, tok[2 + n : 2 + n + q]))
    return "\n".join(str(bisect_left(a, x)) for x in queries)


def _insert_hidden(rng: random.Random) -> list[str]:
    def make(a: list[int], queries: list[int]) -> str:
        return joined(f"{len(a)} {len(queries)}", nums(a), nums(queries))

    big = sorted(rng.sample(range(-10**9, 10**9), 10000))
    queries = [rng.choice(big) for _ in range(1500)] + [rng.randint(-10**9, 10**9) for _ in range(1500)] + [-10**9 - 1, 10**9 + 1]
    return [
        make([5], [1, 5, 9]),
        make([1, 2, 3, 4], [0, 1, 4, 5]),
        make([10, 20, 30], [15, 25, 35, 5]),
        make(list(range(0, 200, 2)), list(range(-3, 205))),
        make([7], [7, 8, 6]),
        make(big, queries),
    ]


INSERT_POSITION = Spec(
    slug="insert-position",
    title="Insert Position",
    difficulty="EASY",
    tags=("Binary Search", "Searching", "Array"),
    description=(
        "A librarian keeps the shelf numbers of her books in a sorted list of **distinct** integers. Visitors ask, for "
        "many values `x`: *\"where would `x` go?\"* — that is, the smallest index `i` (counting from 0) such that "
        "`a[i] ≥ x`. If every number on the shelf is smaller than `x`, the answer is `n`, the position just after the "
        "last book.\n\n"
        "Answer all the queries quickly; scanning the whole list for each one is too slow."
    ),
    input_format="The first line contains `n` and `q`. The second line contains the `n` sorted numbers. The third line contains the `q` queries.",
    output_format="`q` lines, one answer per query, in order.",
    constraints="- 1 ≤ n ≤ 100 000, 1 ≤ q ≤ 100 000\n- the numbers are strictly increasing, |a[i]| ≤ 10^9\n- |x| ≤ 10^9 + 1",
    examples=(
        Example("5 4\n1 3 5 7 9\n0 5 6 10\n", "0\n2\n3\n5\n", "0 belongs before everything; 5 is at index 2; 6 fits before 7 (index 3); 10 goes at the end."),
        Example("1 2\n4\n4 5\n", "0\n1\n", "4 is already at index 0; 5 would come after it."),
    ),
    solve=_insert_solve,
    hidden=_insert_hidden,
    hints=("The list is sorted, so each query can discard half of the remaining candidates.", "You are looking for the first index where a[i] ≥ x: keep a range [lo, hi) and shrink it while remembering that hi itself may be the answer."),
    editorial="This is a lower-bound binary search. With `lo = 0, hi = n`, while `lo < hi` compute `mid`; if `a[mid] < x` set `lo = mid + 1`, otherwise `hi = mid`. The answer is `lo`. Each query costs O(log n).",
    time_complexity="O((n + q) log n)",
    space_complexity="O(n)",
)

# --- 8. Bit Counter -----------------------------------------------------------------------------


def _bits_solve(text: str) -> str:
    tok = text.split()
    q = int(tok[0])
    return "\n".join(str(bin(int(x)).count("1")) for x in tok[1 : 1 + q])


def _bits_hidden(rng: random.Random) -> list[str]:
    def make(values: list[int]) -> str:
        return joined(len(values), nums(values))

    special = [0, 1, 2, 3, 2**59, 2**59 + 12345, 10**18, 2**40 + 2**20 + 1, 999999999999999999]
    randoms = [rng.randint(0, 10**18) for _ in range(3000)]
    return [make([0, 0]), make([1]), make([255, 256, 257]), make(special), make(randoms), make([10**18] * 50)]


BIT_COUNTER = Spec(
    slug="bit-counter",
    title="Bit Counter",
    difficulty="EASY",
    tags=("Bit Manipulation", "Math"),
    description=(
        "A control panel shows a machine's state as a single non-negative integer. Written in binary, each `1` bit "
        "means one switch is turned on. The technician wants to know, for many panel readings, **how many switches are "
        "on** — that is, how many `1`s the binary form of the number contains.\n\n"
        "Readings can be as large as 10^18, so think about how to count bits without building giant strings."
    ),
    input_format="The first line contains `q`. The second line contains the `q` readings.",
    output_format="`q` lines: the number of `1` bits in each reading.",
    constraints="- 1 ≤ q ≤ 100 000\n- 0 ≤ reading ≤ 10^18",
    examples=(
        Example("3\n5 7 1024\n", "2\n3\n1\n", "5 = 101₂ has two ones, 7 = 111₂ has three, 1024 = 10000000000₂ has one."),
        Example("1\n0\n", "0\n", "Zero has no bits set."),
    ),
    solve=_bits_solve,
    hidden=_bits_hidden,
    hints=("`x & 1` tells you the lowest bit; `x >> 1` drops it.", "A neat trick: `x & (x - 1)` clears the lowest set bit. How many times can you apply it before x becomes 0?"),
    editorial="Kernighan's method: repeat `x &= x - 1` and count iterations; each iteration removes exactly one set bit, so it runs popcount(x) ≤ 60 times. Most languages also offer a built-in popcount.",
    time_complexity="O(q · 60)",
    space_complexity="O(1)",
)

# --- 9. Reverse the Chain -----------------------------------------------------------------------


def _chain_solve(text: str) -> str:
    tok = text.split()
    n = int(tok[0])
    return nums(list(reversed(list(map(int, tok[1 : 1 + n])))))


def _chain_hidden(rng: random.Random) -> list[str]:
    def make(values: list[int]) -> str:
        return joined(len(values), nums(values))

    return [
        make([42]),
        make([1, 2]),
        make([1, 2, 3]),
        make([5, 5, 5, 5]),
        make([-3, 0, 9, -3]),
        make(list(range(1, 51))),
        make([rng.randint(-10**9, 10**9) for _ in range(20000)]),
    ]


_CHAIN_STARTERS = {
    "python": (
        "import sys\n\n\n"
        "class Node:\n"
        "    def __init__(self, value):\n"
        "        self.value = value\n"
        "        self.next = None\n\n\n"
        "def reverse(head):\n"
        "    # TODO: relink the nodes so the list runs the other way, and return the new head.\n"
        "    return head\n\n\n"
        'if __name__ == "__main__":\n'
        "    tokens = sys.stdin.read().split()\n"
        "    n = int(tokens[0])\n"
        "    head = tail = None\n"
        "    for token in tokens[1 : 1 + n]:\n"
        "        node = Node(int(token))\n"
        "        if head is None:\n"
        "            head = tail = node\n"
        "        else:\n"
        "            tail.next = node\n"
        "            tail = node\n"
        "    head = reverse(head)\n"
        "    values = []\n"
        "    while head is not None:\n"
        "        values.append(str(head.value))\n"
        "        head = head.next\n"
        '    print(" ".join(values))\n'
    ),
    "cpp": (
        "#include <bits/stdc++.h>\n"
        "using namespace std;\n\n"
        "struct Node {\n"
        "    long long value;\n"
        "    Node* next = nullptr;\n"
        "};\n\n"
        "Node* reverse(Node* head) {\n"
        "    // TODO: relink the nodes so the list runs the other way, and return the new head.\n"
        "    return head;\n"
        "}\n\n"
        "int main() {\n"
        "    int n;\n"
        "    cin >> n;\n"
        "    Node *head = nullptr, *tail = nullptr;\n"
        "    for (int i = 0; i < n; i++) {\n"
        "        long long v;\n"
        "        cin >> v;\n"
        "        Node* node = new Node{v};\n"
        "        if (!head) head = tail = node; else { tail->next = node; tail = node; }\n"
        "    }\n"
        "    head = reverse(head);\n"
        "    for (Node* p = head; p; p = p->next) cout << p->value << (p->next ? ' ' : '\\n');\n"
        "    return 0;\n"
        "}\n"
    ),
    "javascript": (
        'const tokens = require("fs").readFileSync(0, "utf8").split(/\\s+/).filter(Boolean);\n\n'
        "class Node {\n"
        "  constructor(value) {\n"
        "    this.value = value;\n"
        "    this.next = null;\n"
        "  }\n"
        "}\n\n"
        "function reverse(head) {\n"
        "  // TODO: relink the nodes so the list runs the other way, and return the new head.\n"
        "  return head;\n"
        "}\n\n"
        "const n = Number(tokens[0]);\n"
        "let head = null, tail = null;\n"
        "for (let i = 1; i <= n; i++) {\n"
        "  const node = new Node(tokens[i]);\n"
        "  if (!head) head = tail = node; else { tail.next = node; tail = node; }\n"
        "}\n"
        "head = reverse(head);\n"
        "const values = [];\n"
        "for (let p = head; p; p = p.next) values.push(p.value);\n"
        'console.log(values.join(" "));\n'
    ),
}

REVERSE_THE_CHAIN = Spec(
    slug="reverse-the-chain",
    title="Reverse the Chain",
    difficulty="EASY",
    tags=("Linked List",),
    description=(
        "A row of paper lanterns is strung on a single cord: each lantern is tied only to the **next** one. To hang "
        "the row the other way round you cannot untie everything and start over — you may only **re-tie the knots** "
        "(change each lantern's `next` link).\n\n"
        "Given the brightness values of the lanterns in order, build the singly linked list, reverse it **in place** by "
        "relinking nodes, and print the values from the new first lantern to the last. The starter code already builds "
        "and prints the list for you; you only have to write `reverse`."
    ),
    input_format="The first line contains `n`. The second line contains the `n` brightness values in order.",
    output_format="The values after reversing, separated by spaces.",
    constraints="- 1 ≤ n ≤ 100 000\n- |value| ≤ 10^9\n- Use O(1) extra memory beyond the list itself",
    examples=(
        Example("4\n1 2 3 4\n", "4 3 2 1\n", "The last lantern becomes the first."),
        Example("1\n7\n", "7\n", "A single lantern stays as it is."),
    ),
    solve=_chain_solve,
    hidden=_chain_hidden,
    hints=(
        "Walk down the list once, keeping track of the node you just left behind (`prev`).",
        "At each node, save `next` *before* you overwrite it, then point the node back at `prev`.",
    ),
    editorial="Iterate with three references: `prev` (initially null), `curr` (the head) and a temporary `nxt`. For each node set `nxt = curr.next`, `curr.next = prev`, `prev = curr`, `curr = nxt`. When `curr` is null, `prev` is the new head.",
    time_complexity="O(n)",
    space_complexity="O(1)",
    starter_override=_CHAIN_STARTERS,
)

# --- 10. Ticket Counter -------------------------------------------------------------------------


def _tickets_solve(text: str) -> str:
    tok = text.split()
    n, k = int(tok[0]), int(tok[1])
    needs = list(map(int, tok[2 : 2 + n]))
    target = needs[k - 1]
    total = 0
    for index, need in enumerate(needs):
        total += min(need, target) if index < k else min(need, target - 1)
    return str(total)


def _tickets_hidden(rng: random.Random) -> list[str]:
    def make(k: int, needs: list[int]) -> str:
        return joined(f"{len(needs)} {k}", nums(needs))

    big = [rng.randint(1, 10**9) for _ in range(30000)]
    return [
        make(1, [1]),
        make(1, [5, 5, 5]),
        make(3, [5, 5, 5]),
        make(2, [1, 1, 1]),
        make(4, [3, 1, 4, 1, 5, 9, 2, 6]),
        make(5, [2, 2, 2, 2, 2]),
        make(15000, big),
        make(1, big),
        make(30000, [10**9] * 30000),
    ]


TICKET_COUNTER = Spec(
    slug="ticket-counter",
    title="Ticket Counter",
    difficulty="EASY",
    tags=("Queue", "Array", "Math"),
    description=(
        "There are `n` people in line at a cinema, numbered 1 to `n` from the front. Person `i` wants to buy `t[i]` "
        "tickets. The clerk is strict: she sells **one ticket** to the person at the front, which takes exactly "
        "**1 second**. If that person still wants more tickets they go to the **back** of the line; otherwise they "
        "leave.\n\n"
        "How many seconds pass until person `k` buys their last ticket (counting that final sale)?"
    ),
    input_format="The first line contains `n` and `k`. The second line contains `t[1] … t[n]`.",
    output_format="One integer: the number of seconds until person `k` is done.",
    constraints="- 1 ≤ k ≤ n ≤ 100 000\n- 1 ≤ t[i] ≤ 10^9\n- Simulating second by second is too slow for large `t[i]`",
    examples=(
        Example("3 2\n2 3 2\n", "7\n", "Sales go to persons 1,2,3,1,2,3,2 — person 2's last (third) ticket is sale number 7."),
        Example("1 1\n5\n", "5\n", "One person buys five tickets in a row."),
    ),
    solve=_tickets_solve,
    hidden=_tickets_hidden,
    hints=(
        "Simulating with a queue works for tiny inputs. For big ones, count how many tickets each person sells *before* person k finishes.",
        "Person i sells at most t[k] tickets in front of k's last sale. People behind k get one fewer chance: they are served after k in the final round.",
    ),
    editorial="Let `T = t[k]`. Every person `i ≤ k` contributes `min(t[i], T)` sales before (and including) k's last one; every person `i > k` contributes `min(t[i], T − 1)`, because in the last round k is served before them. Summing gives the answer in one pass.",
    time_complexity="O(n)",
    space_complexity="O(1)",
)

EASY = [
    HARBOR_CRANES,
    MIRROR_MESSAGE,
    TOOLBOX_BRACKETS,
    WINNING_STREAK,
    FIRST_LONELY_LETTER,
    MERGE_TIMETABLES,
    INSERT_POSITION,
    BIT_COUNTER,
    REVERSE_THE_CHAIN,
    TICKET_COUNTER,
]
