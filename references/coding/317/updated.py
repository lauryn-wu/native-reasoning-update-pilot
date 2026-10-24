from typing import *
UPDATED = True
def solve(queries):
    base=4 if UPDATED else 5
    def prefix(n):
        total=0;power=1;steps=1
        while power<=n:
            upper=min(n,power*base-1)
            total+=(upper-power+1)*steps
            power*=base;steps+=1
        return total
    return sum((prefix(r)-prefix(l-1)+1)//2 for l,r in queries)

class Solution:
    def minOperations(self, queries):
        return solve(queries)
