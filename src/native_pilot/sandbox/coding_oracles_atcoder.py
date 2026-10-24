"""Docker-only independent exhaustive checks for the earlier ranked AtCoder rows."""
import functools
import itertools
import json
import math
import os

if not os.path.isfile('/.dockerenv'):
    raise RuntimeError('Executable checkers must run inside Docker')


@functools.lru_cache(None)
def minimax(state):
    # Literal remaining capacities and visited indices. Sorting merges only
    # symmetric positions; no parity theorem or optimized winner criterion.
    for i, (capacity, touched) in enumerate(state):
        if capacity <= 0:
            continue
        changed = list(state)
        changed[i] = (capacity - 1, True)
        if all(marked for _, marked in changed) or not minimax(tuple(sorted(changed))):
            return True
    return False


game = {'original': [], 'updated': []}
for n in range(1, 7):
    for capacities in itertools.combinations_with_replacement(range(1, 5), n):
        first = minimax(tuple((a, False) for a in capacities))
        stdin = str(n) + '\n' + ' '.join(map(str, capacities)) + '\n'
        game['original'].append({'stdin': stdin, 'stdout': 'Snuke' if first else 'Fennec'})
        game['updated'].append({'stdin': stdin, 'stdout': 'Fennec' if first else 'Snuke'})

arrays = {'original': [], 'updated': []}
for n in range(1, 5):
    for parent in itertools.product(range(n), repeat=n):
        for m in range(1, 4):
            exact = sum(all(values[i] <= values[parent[i]] for i in range(n))
                        for values in itertools.product(range(1, m + 1), repeat=n))
            stdin = f'{n} {m}\n' + ' '.join(str(a + 1) for a in parent) + '\n'
            for variant, mod in [('original', 1000000007), ('updated', 998244353)]:
                arrays[variant].append({'stdin': stdin, 'stdout': str(exact % mod)})
# Independent closed-form boundary families: all self-loops, one long cycle,
# and a monotone chain. They exercise full constraints and differing moduli.
for kind, n, m in [('self', 2025, 2025), ('cycle', 2025, 2025), ('chain', 2025, 2025)]:
    if kind == 'self':
        parent = list(range(1, n + 1)); exact = m ** n
    elif kind == 'cycle':
        parent = list(range(2, n + 1)) + [1]; exact = m
    else:
        parent = list(range(2, n + 1)) + [n]; exact = math.comb(m + n - 1, n)
    stdin = f'{n} {m}\n' + ' '.join(map(str, parent)) + '\n'
    for variant, mod in [('original', 1000000007), ('updated', 998244353)]:
        arrays[variant].append({'stdin': stdin, 'stdout': str(exact % mod)})

print(json.dumps({'scope': 'independent_literal_minimax_and_exhaustive_assignments',
                  'tasks': {'258': game, '167': arrays}}, separators=(',', ':')))
