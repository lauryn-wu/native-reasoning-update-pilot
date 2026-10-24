# Authored reference; execute only inside Docker.
UPDATED=True
MOD=998244353
MOVE=1
import sys
from collections import Counter

def solve(data):
    parts=data.split(); s=parts[1]; n=len(s)//2+1
    fact=[1]*(n+1)
    for i in range(1,n+1): fact[i]=fact[i-1]*i%MOD
    invfact=[1]*(n+1); invfact[n]=pow(fact[n],MOD-2,MOD)
    for i in range(n,0,-1): invfact[i-1]=invfact[i]*i%MOD
    stack=[[]]; identities={}; ways=[]
    for c in s+')':
        if c=='(': stack.append([])
        else:
            children=stack.pop(); children.sort(); key=tuple(children)
            if key not in identities:
                value=fact[len(children)]
                for child in children: value=value*ways[child]%MOD
                for count in Counter(children).values(): value=value*invfact[count]%MOD
                identities[key]=len(ways); ways.append(value)
            child=identities[key]
            if stack: stack[-1].append(child)
    return str(ways[child])
if __name__=='__main__': print(solve(sys.stdin.read()))
