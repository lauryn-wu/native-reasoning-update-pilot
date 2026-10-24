"""Authored exact reference. Execute only inside the pinned Docker sandbox."""
import heapq
import sys

UPDATED = False


def optimum(cakes, k):
    n = len(cakes)
    ranked = sorted(((max(row), i) for i, row in enumerate(cakes)), reverse=True)
    selected = {i for _, i in ranked[:2*k]}
    baseline = sum(value for value, _ in ranked[:2*k])
    labels = [row.index(max(row)) if i in selected else 3 for i, row in enumerate(cakes)]
    parity = 0
    for label in labels:
        if label < 3:
            parity ^= 1 << label
    if parity == 0:
        return baseline

    # An optimum changes at most four items. Retain the best four for every
    # old-label -> new-label action so an unused replacement is always present.
    cheapest = {(a, b): [] for a in range(4) for b in range(4) if a != b}
    for i, (row, old) in enumerate(zip(cakes, labels)):
        old_value = row[old] if old < 3 else 0
        for new in range(4):
            if new == old:
                continue
            loss = old_value - (row[new] if new < 3 else 0)
            heap = cheapest[old, new]
            item = (-loss, i)
            if len(heap) < 4:
                heapq.heappush(heap, item)
            elif item > heap[0]:
                heapq.heapreplace(heap, item)
    candidates = sorted({i for heap in cheapest.values() for _, i in heap})
    # State is (changed items, change in number selected, parity toggles).
    dp = {(0, 0, 0): 0}
    for i in candidates:
        row, old = cakes[i], labels[i]
        old_value = row[old] if old < 3 else 0
        actions = []
        for new in range(4):
            if new != old:
                delta = int(new < 3) - int(old < 3)
                mask = (1 << old if old < 3 else 0) ^ (1 << new if new < 3 else 0)
                actions.append((delta, mask, old_value - (row[new] if new < 3 else 0)))
        nxt = dp.copy()
        for (changed, delta, mask), loss in dp.items():
            if changed == 4:
                continue
            for d, m, cost in actions:
                key = changed+1, delta+d, mask^m
                new_loss = loss+cost
                if key not in nxt or new_loss < nxt[key]:
                    nxt[key] = new_loss
        dp = nxt
    loss = min(value for (changed, delta, mask), value in dp.items() if delta == 0 and mask == parity)
    return baseline-loss


def solve(data):
    values = iter(map(int, data.split()))
    cases = next(values)
    answers = []
    for _ in range(cases):
        n, k = next(values), next(values)
        cakes = [tuple(next(values) for _ in range(3)) for _ in range(n)]
        answer = optimum(cakes, k)
        answers.append(str(answer+(0 if UPDATED else k)))
    return '\n'.join(answers)


if __name__ == '__main__':
    print(solve(sys.stdin.read()))
