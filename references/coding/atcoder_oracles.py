"""Independent literal/exhaustive oracles. Run this file only inside Docker."""
import itertools,json,math,random
from collections import deque
rng=random.Random(20261024)
MODS={'original':1000000007,'updated':998244353}
tasks={str(i):{'original':[],'updated':[]} for i in [218,233,268,269]}
def add(i,stdin,values):
    for variant,value in values.items():tasks[str(i)][variant].append({'stdin':stdin,'stdout':str(value)+'\n'})
# Literal palindrome search over added strings, independent of KMP.
for n in range(1,8):
 for tup in itertools.product('AB',repeat=n):
    s=''.join(tup)
    for k in range(n+1):
      candidates=[s+''.join(t) for t in itertools.product('AB',repeat=k)]
      good=[v for v in candidates if v==v[::-1]]
      if good:updated=min(good);break
    for k in range(n+1):
      candidates=[''.join(t)+s for t in itertools.product('AB',repeat=k)]
      good=[v for v in candidates if v==v[::-1]]
      if good:original=min(good);break
    add(233,s+'\n',{'original':original,'updated':updated})
# Direct closure under every permitted substring reversal, without tree encoding.
def valid(s):
 balance=0
 for c in s:
  balance+=1 if c=='(' else -1
  if balance<0:return False
 return balance==0
for n in range(2,11,2):
 for tup in itertools.product('()',repeat=n):
  s=''.join(tup)
  if not valid(s):continue
  seen={s};queue=deque([s])
  while queue:
   current=queue.popleft()
   for l in range(n):
    for r in range(l+2,n+1,2):
     piece=current[l:r]
     if not valid(piece):continue
     transformed=current[:l]+''.join(')' if c=='(' else '(' for c in piece[::-1])+current[r:]
     if transformed not in seen:seen.add(transformed);queue.append(transformed)
  add(268,f'{n}\n{s}\n',{v:len(seen)%p for v,p in MODS.items()})
# Distinct chain-shaped root children: exactly k! sibling permutations.
for k in [13,14,20,40]:
 s=''.join('('*j+')'*j for j in range(1,k+1))
 add(268,f'{len(s)}\n{s}\n',{v:math.factorial(k)%p for v,p in MODS.items()})
# Enumerate every recursive parent sequence and compute distances by literal DFS.
for n in range(2,8):
 for rep in range(3):
  a=[0,0]+[rng.randint(1,10**9) if rep else 1 for _ in range(2,n+1)]
  pairs=list(itertools.combinations(range(1,n+1),2));total=[0]*len(pairs)
  for parent in itertools.product(*(range(1,i) for i in range(2,n+1))):
   graph=[[] for _ in range(n+1)]
   for i,p in enumerate(parent,2):graph[i].append((p,a[i]));graph[p].append((i,a[i]))
   for j,(u,v) in enumerate(pairs):
    pending=[(u,0,0)]
    while pending:
     current,prev,distance=pending.pop()
     if current==v:total[j]+=distance;break
     pending.extend((child,current,distance+weight) for child,weight in graph[current] if child!=prev)
  stdin=f'{n} {len(pairs)}\n'+ ' '.join(map(str,a[2:]))+'\n'+'\n'.join(f'{u} {v}' for u,v in pairs)+'\n'
  add(269,stdin,{v:'\n'.join(str(d%p) for d in total) for v,p in MODS.items()})
# Bellman-Ford over all state transitions, independent of heap Dijkstra.
for n in [2,3,4]:
 potential=[(u,v) for u in range(n) for v in range(n) if u!=v]
 masks=range(1,1<<len(potential)) if n<4 else [rng.randrange(1,1<<len(potential)) for _ in range(50)]
 for mask in masks:
  edges=[edge for i,edge in enumerate(potential) if mask>>i&1]
  for x in [1,3]:
   answers={}
   for variant,move in [('original',2),('updated',1)]:
    arcs=[(u,v,move) for u,v in edges]+[(n+v,n+u,move) for u,v in edges]+[(u,u+n,x) for u in range(n)]+[(u+n,u,x) for u in range(n)]
    distance=[10**18]*(2*n);distance[0]=0
    for _ in range(2*n-1):
     for u,v,c in arcs:distance[v]=min(distance[v],distance[u]+c)
    answers[variant]=min(distance[n-1],distance[2*n-1])
   if answers['updated']>=10**18:continue
   stdin=f'{n} {len(edges)} {x}\n'+'\n'.join(f'{u+1} {v+1}' for u,v in edges)+'\n'
   add(218,stdin,answers)
print(json.dumps({'seed':20261024,'tasks':tasks},separators=(',',':')))
