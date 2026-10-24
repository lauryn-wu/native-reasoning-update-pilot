from typing import *
UPDATED = False
def solve(n,m,k):
    mod=10**9+7
    equal=k if UPDATED else n-1-k
    if not 0<=equal<n:return 0
    choose=min(equal,n-1-equal);num=den=1
    for i in range(1,choose+1):num=num*(n-i)%mod;den=den*i%mod
    return num*pow(den,mod-2,mod)%mod*m%mod*pow(m-1,n-1-equal,mod)%mod

class Solution:
    def countGoodArrays(self, n, k, m):
        return solve(n, m, k)
