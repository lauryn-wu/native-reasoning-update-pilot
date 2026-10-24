"""Independent small-instance oracles; execute this file ONLY inside Docker.

No candidate/reference is loaded here. The returned expected values stay on
the host when candidate programs are subsequently executed in a new container.
These are verification cases for real released specifications, not pilot tasks.
"""
import itertools as it
import collections
import json
import math
import os
import random
import re

if not os.path.isfile("/.dockerenv"):
    raise RuntimeError("Independent executable checkers must run inside Docker")

RNG = random.Random(20261024)
RECORDS = {}


def add(task_id, original_args, original_expected, updated_args=None, updated_expected=None):
    item = RECORDS.setdefault(str(task_id), {"original": [], "updated": []})
    item["original"].append({"args": original_args, "expected": original_expected})
    item["updated"].append({"args": original_args if updated_args is None else updated_args,
                            "expected": original_expected if updated_expected is None else updated_expected})


def tree_weight(edges, k):
    best = 0
    for mask in range(1 << len(edges)):
        degree = collections.Counter()
        score = 0
        for i, (u, v, w) in enumerate(edges):
            if mask >> i & 1:
                degree[u] += 1
                degree[v] += 1
                score += w
        if max(degree.values(), default=0) <= k:
            best = max(best, score)
    return best


for _ in range(55):
    n = RNG.randrange(2, 9)
    edges = [[i, RNG.randrange(i), RNG.randrange(1, 15)] for i in range(1, n)]
    k = RNG.randrange(1, n)
    add(124, [edges, k], tree_weight(edges, k))


def diagonal(grid, clockwise):
    # Direct path enumeration of every initial ray and each possible turn site.
    n, m = len(grid), len(grid[0])
    best = 0
    for r in range(n):
        for c in range(m):
            if grid[r][c] != 1:
                continue
            best = max(best, 1)
            for dr, dc in ((1, 1), (1, -1), (-1, -1), (-1, 1)):
                path = [(r, c)]
                nr, nc = r + dr, c + dc
                while 0 <= nr < n and 0 <= nc < m and grid[nr][nc] == (2 if len(path) % 2 else 0):
                    path.append((nr, nc))
                    nr, nc = nr + dr, nc + dc
                best = max(best, len(path))
                # Coordinates increase down/right: clockwise maps (dr,dc)->(dc,-dr).
                tr, tc = (dc, -dr) if clockwise else (-dc, dr)
                for pivot in range(len(path)):
                    nr, nc = path[pivot][0] + tr, path[pivot][1] + tc
                    length = pivot + 1
                    while 0 <= nr < n and 0 <= nc < m and grid[nr][nc] == (2 if length % 2 else 0):
                        length += 1
                        nr, nc = nr + tr, nc + tc
                    best = max(best, length)
    return best


for values in it.product(range(3), repeat=4):
    grid = [list(values[:2]), list(values[2:])]
    add(299, [grid], diagonal(grid, False), updated_expected=diagonal(grid, True))
for _ in range(120):
    n, m = RNG.randrange(1, 6), RNG.randrange(1, 6)
    grid = [[RNG.randrange(3) for _ in range(m)] for _ in range(n)]
    add(299, [grid], diagonal(grid, False), updated_expected=diagonal(grid, True))


def middle_mode(nums):
    answer = 0
    for indices in it.combinations(range(len(nums)), 5):
        seq = [nums[i] for i in indices]
        count = collections.Counter(seq)
        answer += all(count[seq[2]] > count[v] for v in count if v != seq[2])
    return answer


for _ in range(130):
    nums = [RNG.randrange(-1, 4) for _ in range(RNG.randrange(5, 12))]
    add(158, [nums], middle_mode(nums))
add(158, [[7] * 1000], math.comb(1000, 5) % 1000000009,
    updated_expected=math.comb(1000, 5) % 1000000007)


def common_prefix(words, k, absent):
    result = []
    for removed in range(len(words)):
        remaining = words[:removed] + words[removed + 1:]
        if len(remaining) < k:
            result.append(absent)
            continue
        best = 0
        for chosen in it.combinations(remaining, k):
            length = 0
            for letters in zip(*chosen):
                if len(set(letters)) != 1:
                    break
                length += 1
            best = max(best, length)
        result.append(best)
    return result


for _ in range(95):
    words = [''.join(RNG.choice('abc') for _ in range(RNG.randrange(1, 5)))
             for _ in range(RNG.randrange(1, 8))]
    k = RNG.randrange(1, len(words) + 1)
    add(337, [words, k], common_prefix(words, k, -1), updated_expected=common_prefix(words, k, 0))


def division_bfs(l, r, base):
    start = tuple(range(l, r + 1))
    queue = collections.deque([(start, 0)])
    seen = {start}
    while queue:
        state, distance = queue.popleft()
        if not any(state):
            return distance
        for i, j in it.combinations(range(len(state)), 2):
            new = list(state)
            new[i] //= base
            new[j] //= base
            new = tuple(sorted(new))
            if new not in seen:
                seen.add(new)
                queue.append((new, distance + 1))
    raise AssertionError("Finite reduction failed")


for l in range(1, 12):
    for r in range(l + 1, min(l + 4, 15)):
        add(317, [[[l, r]]], division_bfs(l, r, 5), updated_expected=division_bfs(l, r, 4))


GOOD = {}
for n in range(1, 9):
    GOOD[n] = [''.join(chars) for chars in it.product('abc', repeat=n)
               if all(len(list(group)) >= 3 for _, group in it.groupby(chars))]
for n in range(1, 9):
    for _ in range(15):
        caption = ''.join(RNG.choice('abc') for _ in range(n))
        if GOOD[n]:
            costs = [(sum(abs(ord(a) - ord(b)) for a, b in zip(caption, target)), target) for target in GOOD[n]]
            optimum = min(cost for cost, target in costs)
            choices = sorted(target for cost, target in costs if cost == optimum)
            add(328, [caption], choices[-1], updated_expected=choices[0])
        else:
            add(328, [caption], "")


def min_run(s, ops, ones_only):
    best = len(s)
    for mask in range(1 << len(s)):
        if mask.bit_count() > ops:
            continue
        changed = ''.join(str(int(ch) ^ (mask >> i & 1)) for i, ch in enumerate(s))
        largest = max((len(list(g)) for ch, g in it.groupby(changed) if ch == '1' or not ones_only), default=0)
        best = min(best, largest)
    return best


for n in range(1, 6):
    for bits in it.product('01', repeat=n):
        s = ''.join(bits)
        for ops in range(n + 1):
            add(151, [s, ops], min_run(s, ops, True), updated_expected=min_run(s, ops, False))


def shortest(s, p):
    regex = re.compile('.*'.join(re.escape(part) for part in p.split('*')))
    answer = len(s) + 1
    for start in range(len(s) + 1):
        for end in range(start, len(s) + 1):
            if regex.fullmatch(s[start:end]):
                answer = min(answer, end - start)
    return -1 if answer > len(s) else answer


for _ in range(140):
    s = ''.join(RNG.choice('ab') for _ in range(RNG.randrange(1, 10)))
    parts = [''.join(RNG.choice('ab') for _ in range(RNG.randrange(3))) for _ in range(4)]
    p3 = '*'.join(parts)
    p2 = '*'.join(parts[:3])
    add(331, [p3, s], shortest(s, p3), [s, p2], shortest(s, p2))


for n in range(1, 7):
    for m in range(1, 4):
        counts = collections.Counter(sum(a == b for a, b in zip(arr, arr[1:])) for arr in it.product(range(m), repeat=n))
        for k in range(n):
            add(154, [n, k, m], counts[n - 1 - k], [n, m, k], counts[k])


for m in range(1, 4):
    for n in range(1, 4):
        if m * n > 8:
            continue
        cells = list(it.product(range(m), range(n)))
        for k in range(2, len(cells) + 1):
            total = sum(sum(abs(a[0] - b[0]) + abs(a[1] - b[1]) for a, b in it.combinations(chosen, 2))
                        for chosen in it.combinations(cells, k))
            add(325, [m, n, k], 2 * total, updated_expected=total)


def subsequence_sum(nums):
    total = 0
    for mask in range(1, 1 << len(nums)):
        seq = [value for i, value in enumerate(nums) if mask >> i & 1]
        if all(abs(a - b) == 1 for a, b in zip(seq, seq[1:])):
            total += sum(seq)
    return total


for _ in range(120):
    nums = [RNG.randrange(5) for _ in range(RNG.randrange(1, 10))]
    add(117, [nums], subsequence_sum(nums))
# Count embeddings of every alternating binary target string, independently
# of a per-value sum recurrence. This exact integer count crosses both moduli.
nums = [0, 1] * 40
total = 0
for length in range(1, len(nums) + 1):
    for start in (0, 1):
        pattern = [(start + i) % 2 for i in range(length)]
        count = [1] + [0] * length
        for value in nums:
            for i in range(length - 1, -1, -1):
                if pattern[i] == value:
                    count[i + 1] += count[i]
        total += count[-1] * sum(pattern)
add(117, [nums], total % 1000000009, updated_expected=total % 1000000007)


def interval_choice(intervals, maximum):
    best_score, best_indices = -1, None
    for size in range(min(maximum, len(intervals)) + 1):
        for indices in it.combinations(range(len(intervals)), size):
            if any(not(intervals[i][1] < intervals[j][0] or intervals[j][1] < intervals[i][0]) for i, j in it.combinations(indices, 2)):
                continue
            score = sum(intervals[i][2] for i in indices)
            if score > best_score or score == best_score and indices < best_indices:
                best_score, best_indices = score, indices
    return list(best_indices)


for _ in range(100):
    intervals = []
    for i in range(RNG.randrange(1, 10)):
        l = RNG.randrange(1, 10)
        intervals.append([l, l + RNG.randrange(4), RNG.randrange(1, 8)])
    add(162, [intervals], interval_choice(intervals, 5), updated_expected=interval_choice(intervals, 4))
intervals = [[2 * i, 2 * i, 1] for i in range(6)]
add(162, [intervals], [0, 1, 2, 3, 4], updated_expected=[0, 1, 2, 3])


def frequency_bfs(counts, direction):
    start = (0,) + tuple(counts) + (0,)
    queue = collections.deque([(start, 0)])
    seen = {start}
    # All-positive equal frequencies are the exact terminal predicate. A
    # two-step move costs as much as delete+insert; outer neighbors suffice.
    while queue:
        state, distance = queue.popleft()
        if len({c for c in state if c}) <= 1:
            return distance
        neighbors = []
        for i in range(5):
            if state[i]:
                new = list(state); new[i] -= 1; neighbors.append(tuple(new))
                j = i + direction
                if 0 <= j < 5:
                    new = list(state); new[i] -= 1; new[j] += 1; neighbors.append(tuple(new))
            new = list(state); new[i] += 1; neighbors.append(tuple(new))
        for new in neighbors:
            if new not in seen:
                seen.add(new); queue.append((new, distance + 1))


for counts in it.product(range(4), repeat=3):
    if not 3 <= sum(counts) <= 7:
        continue
    s = ''.join(ch * count for ch, count in zip('bcd', counts))
    add(148, [s], frequency_bfs(counts, -1), updated_expected=frequency_bfs(counts, 1))

print(json.dumps({"seed": 20261024, "scope": "independent_exact_small_instance_oracles", "tasks": RECORDS}, separators=(',', ':')))
