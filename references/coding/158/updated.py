from typing import *
UPDATED = True
def solve(nums):
    from collections import Counter
    from math import comb
    mod=10**9+(7 if UPDATED else 9)
    left=Counter(); right=Counter(nums); answer=0
    def c(n,k): return comb(n,k) if n>=k>=0 else 0
    for i,x in enumerate(nums):
        right[x]-=1
        a,b=left[x],right[x]; l=i-a; r=len(nums)-i-1-b
        # At least three occurrences of x: it necessarily is the unique mode.
        for u in range(3):
            for v in range(3):
                if u+v>=2: answer+=c(a,u)*c(l,2-u)*c(b,v)*c(r,2-v)
        # Exactly two x's: the other three values must be pairwise distinct.
        rpairs=sum(c(count,2) for y,count in right.items() if y!=x)
        lpairs=sum(c(count,2) for y,count in left.items() if y!=x)
        for y,count in left.items():
            if y!=x:
                ry=right[y]
                answer+=a*count*(c(r-ry,2)-rpairs+c(ry,2))
        for y,count in right.items():
            if y!=x:
                ly=left[y]
                answer+=b*count*(c(l-ly,2)-lpairs+c(ly,2))
        left[x]+=1
        answer%=mod
    return answer

class Solution:
    def subsequencesWithMiddleMode(self, nums):
        return solve(nums)
