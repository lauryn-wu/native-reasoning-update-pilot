from typing import *
UPDATED = True
def solve(words,k):
    import heapq
    if len(words)-1<k: return [0 if UPDATED else -1]*len(words)
    children=[{}]; count=[0]; depth=[0]; paths=[]
    for word in words:
        node=0; path=[]
        for char in word:
            if char not in children[node]:
                children[node][char]=len(children); children.append({});count.append(0);depth.append(depth[node]+1)
            node=children[node][char];count[node]+=1;path.append(node)
        paths.append(path)
    good=[0]*(max(depth)+1)
    for node in range(1,len(children)):
        if count[node]>=k:good[depth[node]]+=1
    heap=[-d for d,c in enumerate(good) if c];heapq.heapify(heap);result=[]
    for path in paths:
        changed=[depth[node] for node in path if count[node]==k]
        for d in changed:good[d]-=1
        while heap and not good[-heap[0]]:heapq.heappop(heap)
        result.append(-heap[0] if heap else 0)
        for d in changed:
            if not good[d]:heapq.heappush(heap,-d)
            good[d]+=1
    return result

class Solution:
    def longestCommonPrefix(self, words, k):
        return solve(words, k)
