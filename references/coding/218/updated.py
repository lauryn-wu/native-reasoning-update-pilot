# Authored reference; execute only inside Docker.
UPDATED=True
MOD=998244353
MOVE=1
import sys, heapq

def solve(data):
    v=list(map(int,data.split())); n,m,x=v[:3]
    edges=[[[] for _ in range(n)] for _ in range(2)]
    for i in range(m):
        a,b=v[3+2*i:5+2*i]; a-=1; b-=1
        edges[0][a].append(b); edges[1][b].append(a)
    distance=[10**30]*(2*n); distance[0]=0; queue=[(0,0)]
    while queue:
        cost,state=heapq.heappop(queue)
        if cost!=distance[state]: continue
        direction,node=divmod(state,n)
        if node==n-1: return str(cost)
        other=(1-direction)*n+node
        if cost+x<distance[other]:
            distance[other]=cost+x; heapq.heappush(queue,(cost+x,other))
        for child in edges[direction][node]:
            target=direction*n+child
            if cost+MOVE<distance[target]:
                distance[target]=cost+MOVE; heapq.heappush(queue,(cost+MOVE,target))
    raise ValueError('Source guarantees reachability')
if __name__=='__main__': print(solve(sys.stdin.read()))
