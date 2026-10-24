"""Independently authored literal-state oracle; run only inside Docker.

Every move removes two neighbors in the CURRENT remaining sequence. No interval
DP, matching theorem, optimized reference, or published answer is imported.
"""
import functools
import itertools
import json
import os
import random

if not os.path.isfile('/.dockerenv'):
    raise RuntimeError('Independent executable checks must run only in Docker')


def literal(values):
    @functools.lru_cache(None)
    def remaining(mask):
        indices = [i for i in range(len(values)) if mask >> i & 1]
        if len(indices) < 2:
            return (0, 0)
        low, high = None, None
        for i, j in zip(indices, indices[1:]):
            tail_low, tail_high = remaining(mask ^ (1 << i) ^ (1 << j))
            score = abs(values[i] - values[j])
            low = score + tail_low if low is None else min(low, score + tail_low)
            high = score + tail_high if high is None else max(high, score + tail_high)
        return low, high
    return remaining((1 << len(values)) - 1)


cases = []


def add(values, family):
    values = tuple(values)
    low, high = literal(values)
    cases.append({'stdin': str(len(values)) + '\n' + ' '.join(map(str, values)) + '\n',
                  'minimum': str(low), 'maximum': str(high), 'family': family})


for n in range(2, 10):
    for values in itertools.product((1, 10**9), repeat=n):
        add(values, 'all_binary_extreme_values_n2_to_n9')
for n in range(2, 7):
    for values in itertools.product((-2, 0, 3), repeat=n):
        add(values, 'all_signed_ternary_n2_to_n6')
rng = random.Random(20261024)
for _ in range(180):
    add([rng.randint(-10**9, 10**9) for _ in range(rng.randint(2, 11))], 'signed_random')
lo, hi = -(2**63), 2**63 - 1
for values in [(), (7,), (lo, hi), (hi, lo), (lo, 0, hi), (lo, hi, lo, hi),
               (0, 2**63-1, 0, 2**63-1), (0, 2**63, 0, 2**63),
               (lo, lo+1, hi-1, hi), (lo, hi, 7, lo, hi),
               (0, 4, 5, 9), (0, 50, 100, 1, 50, 101),
               (10**80, -(10**80)), (10**80, 1, -(10**80)),
               (10**80, 10**80+7, -(10**80), -(10**80)+5),
               (10**80, -10**80, 10**80, -10**80, 17)]:
    add(values, 'arithmetic_parity_and_greedy_counterexample_boundaries')
print(json.dumps({'seed':20261024, 'method':'literal_current_adjacency_bitmask',
                  'cases':cases}, separators=(',', ':')))
