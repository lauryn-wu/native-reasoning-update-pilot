"""Second mathematical verifier; execute only in pinned Docker, never the host.
Independent formulations supplement the written derivation review.
"""
from fractions import Fraction as F
from itertools import product
from math import comb
import json
out={}
# Hensel lift each mod17 root instead of sweeping all residues modulo17^3.
r=[x for x in range(17) if (x**4+1)%17==0]
for power in (1,2):
 q=17**power
 r=[x+t*q for x in r for t in range(17) if ((x+t*q)**4+1)%(17*q)==0]
 out['roots_'+str(power+1)]=sorted(r)
assert out['roots_2']==[110,134,155,179] and out['roots_3']==[399,1022,3891,4514]
# Independent digit-vector replacement, including leading positions.
valid=[]
for ds in product(range(10),repeat=4):
 if ds[0] and all(sum((1 if j==k else ds[j])*10**(3-j) for j in range(4))%7==0 for k in range(4)):
  valid.append(sum(ds[j]*10**(3-j) for j in range(4)))
assert valid==[5624,5694];out['digit_values']=valid
# Cube count with full ordered first-two *integer* domain, not paired residue frequencies.
counts=[]
for start,end,mod in [(0,2187,6561),(1,729,2187)]:
 cubes=[pow(n,3,mod) for n in range(start,end+1)]
 hist=[0]*mod
 for v in cubes:hist[v]+=1
 counts.append(sum(hist[(-a-b)%mod] for a in cubes for b in cubes))
assert counts==[10174168,885735];out['direct_pair_cube_counts']=counts
# Product over roots of unity equals determinant of polynomial in the cyclic shift matrix.
def det(a):
 a=[[F(x) for x in row] for row in a];d=F(1)
 for j in range(len(a)):
  p=next(i for i in range(j,len(a)) if a[i][j])
  if p!=j:a[j],a[p]=a[p],a[j];d=-d
  v=a[j][j];d*=v
  for i in range(j+1,len(a)):
   t=a[i][j]/v
   for k in range(j,len(a)):a[i][k]-=t*a[j][k]
 return d
values=[]
for n,c in [(11,3),(13,2)]:
 a=[[0]*n for _ in range(n)]
 for j in range(n):a[j][j]+=c;a[(j+1)%n][j]-=2;a[(j+2)%n][j]+=1
 values.append(int(det(a)))
assert values==[177542,8321];out['cyclic_determinants']=values
# Since3 invertible mod1000, iterate s'=s^2/3 mod1000 directly.
s=36
for _ in range(2024):s=s*s*667%1000
assert s==248;out['updated_recurrence_sum']=s
# Exact chord expectation, algebraic max square, radii identity, affine areas.
assert 4+62+comb(31,2)*F(3,8)==F(1923,8)
assert 4+25*F(7,3)+comb(25,2)*F(17,36)==204
assert 363**2+331**2==241330 and 324**2+432**2==540**2
assert 6*17*7==714 and 6*13*6==468
out['other_checks']='exact identities passed; written independent proofs cover domain/geometry and exclusions'
print(json.dumps(out,sort_keys=True))
