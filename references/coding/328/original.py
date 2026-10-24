from typing import *
UPDATED = False
def solve(caption):
    # f[i][c][r] is optimal suffix cost after previous char c has run r (cap3).
    from array import array
    n=len(caption)
    if n<3:return ''
    inf=10**9
    codes=[ord(c)-97 for c in caption]
    table=[None]*(n+1)
    last=array('i',[inf])*78
    for c in range(26):last[c*3+2]=0
    table[n]=last
    for i in range(n-1,-1,-1):
        nxt=table[i+1];curr=array('i',[inf])*78
        start=[abs(codes[i]-c)+nxt[c*3] for c in range(26)]
        ranked=sorted(range(26),key=lambda c:start[c]);best,second=ranked[:2]
        for c in range(26):
            cost=abs(codes[i]-c)
            curr[c*3]=cost+nxt[c*3+1]
            curr[c*3+1]=cost+nxt[c*3+2]
            other=start[best if best!=c else second]
            curr[c*3+2]=min(cost+nxt[c*3+2],other)
        table[i]=curr
    remaining=min(abs(codes[0]-c)+table[1][c*3] for c in range(26))
    out=[];prev=-1;run=0
    order=range(26) if UPDATED else range(25,-1,-1)
    for i in range(n):
        for c in order:
            if prev!=-1 and c!=prev and run<3:continue
            newrun=min(3,run+1) if c==prev else 1
            cost=abs(codes[i]-c)
            if cost+table[i+1][c*3+newrun-1]==remaining:
                out.append(chr(c+97));remaining-=cost;prev=c;run=newrun;break
    return ''.join(out)

class Solution:
    def minCostGoodCapiton(self, caption):
        return solve(caption)
