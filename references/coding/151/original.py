from typing import *
UPDATED = False
def solve(s,numOps):
    runs=[];old=None
    for ch in s:
        if ch==old:runs[-1][1]+=1
        else:runs.append([ch,1]);old=ch
    def needed(limit):
        if not UPDATED:
            return sum(length//(limit+1) for ch,length in runs if ch=='1')
        if limit==1:
            mismatch=sum(int(ch)!=i%2 for i,ch in enumerate(s))
            return min(mismatch,len(s)-mismatch)
        return sum(length//(limit+1) for ch,length in runs)
    lo=1 if UPDATED else 0;hi=len(s)
    while lo<hi:
        mid=(lo+hi)//2
        if needed(mid)<=numOps:hi=mid
        else:lo=mid+1
    return lo

class Solution:
    def minLength(self, s, numOps):
        return solve(s, numOps)
