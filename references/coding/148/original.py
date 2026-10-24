from typing import *
UPDATED = False
def solve(s):
    from collections import Counter
    c=[s.count(chr(97+i)) for i in range(26)]
    if not UPDATED:c.reverse()
    result=len(s)
    for target in range(1,max(c)+1):
        previous=[c[0],abs(c[0]-target)]
        for i in range(1,26):
            current=[10**9,10**9]
            for choice in range(2):
                goal=target*choice;deficit=max(0,goal-c[i]);cost=abs(c[i]-goal)
                for old in range(2):
                    surplus=max(0,c[i-1]-target*old)
                    current[choice]=min(current[choice],previous[old]+cost-min(surplus,deficit))
            previous=current
        result=min(result,*previous)
    return result

class Solution:
    def makeStringGood(self, s):
        return solve(s)
