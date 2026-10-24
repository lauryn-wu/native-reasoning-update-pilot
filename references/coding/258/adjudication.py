"""Docker-only exact adjudication of published upstream test index 20.

The state reduction is exact without the parity winner theorem: already visited
indices are interchangeable because only the sum of their remaining capacities
affects future legal moves. Unvisited capacities remain fully represented.
"""
import functools
import json
import os

if not os.path.isfile('/.dockerenv'):
    raise RuntimeError('Executable reference checks must run only inside Docker')

CAPACITIES = (7, 16, 3, 3, 9, 8, 16, 12, 8, 3)


@functools.lru_cache(None)
def winning(unvisited, passes):
    if len(unvisited) == 1:
        return True
    if passes and not winning(unvisited, passes - 1):
        return True
    for i, amount in enumerate(unvisited):
        if i and unvisited[i - 1] == amount:
            continue
        if not winning(unvisited[:i] + unvisited[i + 1:], passes + amount - 1):
            return True
    return False


first = winning(tuple(sorted(CAPACITIES)), 0)
print(json.dumps({'first_player_wins': first,
                  'updated_winner': 'Fennec' if first else 'Snuke',
                  'original_winner': 'Snuke' if first else 'Fennec',
                  'states': winning.cache_info().currsize}))
