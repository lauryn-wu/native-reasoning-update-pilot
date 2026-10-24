from typing import *
UPDATED = True
def solve(nums):
    from collections import defaultdict
    mod=10**9+(7 if UPDATED else 9);count=defaultdict(int);sums=defaultdict(int)
    answer=0
    for x in nums:
        nc=(1+count[x-1]+count[x+1])%mod
        ns=(x*nc+sums[x-1]+sums[x+1])%mod
        count[x]=(count[x]+nc)%mod;sums[x]=(sums[x]+ns)%mod
        answer=(answer+ns)%mod
    return answer

class Solution:
    def sumOfGoodSubsequences(self, nums):
        return solve(nums)
