from typing import *
UPDATED = False
def solve(m,n,k):
    mod=10**9+7;cells=m*n
    if k<2:return 0
    choose=min(k-2,cells-k);num=den=1
    for i in range(1,choose+1):num=num*(cells-1-i)%mod;den=den*i%mod
    ways=num*pow(den,mod-2,mod)%mod
    pair_sum=(n*n*m*(m*m-1)+m*m*n*(n*n-1))//6
    return pair_sum*ways*(1 if UPDATED else 2)%mod

class Solution:
    def distance_sum(self, m, n, k):
        return solve(m, n, k)
