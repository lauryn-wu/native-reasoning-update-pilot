from typing import *
UPDATED = False
def solve(intervals):
    from bisect import bisect_left
    rows=sorted((r,l,w,i) for i,(l,r,w) in enumerate(intervals));ends=[r for r,l,w,i in rows]
    prev=[bisect_left(ends,l) for r,l,w,i in rows];n=len(rows);K=4 if UPDATED else 5
    earlier=[(0,())]*(n+1)
    def best(a,b):return a if a[0]>b[0] or (a[0]==b[0] and a[1]<b[1]) else b
    for layer in range(1,K+1):
        current=[(0,())]*(n+1)
        for j,(r,l,w,index) in enumerate(rows,1):
            score,chosen=earlier[prev[j-1]]
            take=(score+w,tuple(sorted(chosen+(index,))))
            current[j]=best(current[j-1],take)
        earlier=current
    return list(earlier[n][1])

class Solution:
    def maximumweight(self, intervals):
        return solve(intervals)
