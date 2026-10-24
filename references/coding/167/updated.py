# Source original modulus. Execute only inside Docker.
# Functional-graph DP; independently checked by exhaustive assignments.
# Official proof: https://atcoder.jp/contests/abc387/editorial/11869?lang=en
import sys
from collections import deque
MOD = 998244353
data = list(map(int, sys.stdin.buffer.read().split()))
n, m = data[:2]
parent = [a - 1 for a in data[2:]]
assert len(parent) == n and m >= 1 and all(0 <= a < n for a in parent)
degree = [0] * n
for a in parent:
    degree[a] += 1
queue = deque(i for i in range(n) if degree[i] == 0)
ways = [[1] * m for _ in range(n)]
while queue:
    node = queue.popleft()
    ancestor = parent[node]
    cumulative = 0
    for value in range(m):
        cumulative = (cumulative + ways[node][value]) % MOD
        ways[ancestor][value] = ways[ancestor][value] * cumulative % MOD
    ways[node] = None
    degree[ancestor] -= 1
    if degree[ancestor] == 0:
        queue.append(ancestor)
answer = 1
seen = set()
for node in range(n):
    if degree[node] == 0 or node in seen:
        continue
    product = [1] * m
    current = node
    while current not in seen:
        seen.add(current)
        for value in range(m):
            product[value] = product[value] * ways[current][value] % MOD
        current = parent[current]
    answer = answer * sum(product) % MOD
print(answer)
