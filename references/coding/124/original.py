from typing import *
UPDATED = False
def solve(edges, k):
    n = len(edges) + 1
    graph = [[] for _ in range(n)]
    for a, b, w in edges:
        graph[a].append((b, w)); graph[b].append((a, w))
    parent = [-1] * n; order = [0]
    for u in order:
        for v, w in graph[u]:
            if v != parent[u]: parent[v] = u; order.append(v)
    free = [0] * n; used = [0] * n
    for u in reversed(order):
        base = 0; gains = []
        for v, w in graph[u]:
            if parent[v] == u:
                base += free[v]
                if k: gains.append(max(0, w + used[v] - free[v]))
        gains.sort(reverse=True)
        free[u] = base + sum(gains[:k])
        used[u] = base + sum(gains[:max(k-1, 0)])
    return free[0]

class Solution:
    def maximizeSumWeights(self, edges, k):
        return solve(edges, k)
