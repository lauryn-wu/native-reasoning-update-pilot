"""Exact reference calculations. Execute ONLY through the Docker sandbox.

The finite loops enumerate the complete mathematical domains claimed below;
these are derivations/checks, not experimental model outputs.
"""
import json
from collections import Counter
from fractions import Fraction as F
from itertools import combinations, permutations, product
from math import gcd, isqrt

result = {}

def record(tid, initial, updated, evidence):
    result[tid] = {"original_answer": str(initial), "updated_answer": str(updated), "evidence": evidence}

roots2 = [m for m in range(1,17**2) if (m**4+1) % (17**2) == 0]
roots3 = [m for m in range(1,17**3) if (m**4+1) % (17**3) == 0]
record('aime2024:1004', min(roots3), min(roots2), {'roots_mod_17_squared':roots2,'roots_mod_17_cubed':roots3})

def digit_solutions(digits, replacement, divisor):
    return [n for n in range(10**(digits-1), 10**digits)
            if all((n+(replacement-int(v))*10**i)%divisor==0
                   for i,v in enumerate(str(n)[::-1]))]
old_digits=digit_solutions(5,2,9)
new_digits=digit_solutions(4,1,7)
qrsum=lambda n: n//1000+n%1000
record('aime2024:1027',qrsum(min(old_digits)),qrsum(max(new_digits)),
       {'initial_solutions':old_digits,'updated_solutions':new_digits})

def log_answer(rhs, exponents):
    a,b,c=rhs
    logs=[-(b+c)/2,-(a+c)/2,-(a+b)/2]
    assert [logs[0]-logs[1]-logs[2],logs[1]-logs[0]-logs[2],logs[2]-logs[0]-logs[1]]==rhs
    answer=abs(sum(t*e for t,e in zip(logs,exponents)))
    return answer.numerator+answer.denominator,str(answer)
x=log_answer([F(1,5),F(1,6),F(1,8)],[4,5,2]);y=log_answer([F(1,2),F(1,3),F(1,4)],[4,3,2])
record('aime2024:1024',x[0],y[0],{'initial_log_value':x[1],'updated_log_value':y[1]})
# 251_b = b*(25_b)+1. No qualifying b>12, so the product is 1.
# For the updated problem (b+7)|(9b+7) iff (b+7)|56.
bases=[d-7 for d in range(1,57) if 56%d==0 and d-7>9]
record('aime2025:1030',1,sum(bases),{'initial_bases':[],'updated_bases':bases})

def cube_count(bound, modulus, include_zero):
    frequencies=Counter(pow(a,3,modulus) for a in range(0 if include_zero else 1,bound+1))
    return sum(ca*cb*frequencies.get((-a-b)%modulus,0)
               for a,ca in frequencies.items() for b,cb in frequencies.items())
for bound in range(1,9):
    assert cube_count(bound,27,True)==sum((a**3+b**3+c**3)%27==0 for a in range(bound+1) for b in range(bound+1) for c in range(bound+1))
a=cube_count(3**7,3**8,True);b=cube_count(3**6,3**7,False)
record('aime2025:1044',a%729,b%1000,{'initial_ordered_triples':a,'updated_ordered_triples':b})

def crossing_probability(pairs):
    probability=F(0)
    for p,q in product(pairs,repeat=2):
        quadrants=[[] for _ in range(4)]
        for label,ends in [('A',p),('B',q)]:
            for j,quad in enumerate(ends):quadrants[quad].append(label+str(j))
        orders=list(product(*(list(permutations(items)) for items in quadrants)))
        crossings=0
        for order in orders:
            labels=[x[0] for group in order for x in group]
            crossings+=all(labels[i]!=labels[(i+1)%4] for i in range(4))
        probability+=F(crossings,len(orders)*len(pairs)**2)
    return probability
adjacent=[(0,1),(1,2),(2,3),(0,3)]
all_pairs=list(combinations(range(4),2))
padj=crossing_probability(adjacent);pall=crossing_probability(all_pairs)
initial=4+31*2+F(31*30,2)*padj
updated=4+25*F(7,3)+F(25*24,2)*pall
record('aime2025:1042',initial,updated,{'adjacent_crossing_probability':str(padj),'different_crossing_probability':str(pall)})
# z=4 exp(it), so the real part is (4a+c/4)cos(t)+(-4b+d/4)sin(t).
squares=[]
for a,b,c,d in [(84,91,108,132),(75,117,96,144)]:
    u,v=4*F(a)+F(c,4),-4*F(b)+F(d,4)
    squares.append(u*u+v*v)
assert squares==[F(241330),F(291600)] and isqrt(291600)==540
record('aime2024:1012','sqrt(241330)',540,{'squared_maxima':[str(x) for x in squares]})
record('aime2024:1016',6*17*7,6*13*6,{'proved_formula':'adjacent_side_product=6*R*r'})
# Six full periods in u=4x; five in u=5x. Endpoints u=0,2pi*periods excluded.
def nested_sine(outer, periods):
    tangent=2*periods
    zeros=(2*outer-1)*2*periods-1+tangent
    return zeros,tangent
n,t=nested_sine(9,6);nn,tt=nested_sine(7,5)
record('aime2025:1053',n-t,nn+tt,{'initial_n':n,'initial_t':t,'updated_n':nn,'updated_t':tt})

def unity_product(c,n):
    s0,s1=2,2
    for _ in range(2,n+1):s0,s1=s1,2*s1-c*s0
    return c**n-s1+1
u,v=unity_product(3,11),unity_product(2,13)
record('aime2024:1019',u%625,v%1000,{'initial_exact_product':u,'updated_exact_product':v})
# Initial recurrence stays reduced: numerator m²+mn+n² is coprime to 2mn.
m,n=26,11
for _ in range(2025):m,n=(m*m+m*n+n*n)%1000,(2*m*n)%1000
initial=(m+n)%1000
# Updated reduced sum obeys s' = s²/3, s1=36, by the 3-adic argument in the proof.
updated=(3*pow(12,1<<2024,1000))%1000
# Independently verify the reduction invariant for the first eight exact terms.
m,n=25,11
s=36
for _ in range(8):
    a,b=m*m-m*n+n*n,3*m*n
    assert gcd(a,b)==3
    m,n=a//3,b//3
    s=s*s//3
    assert m+n==s and m%3 and n%3 and s%9==0
record('aime2025:1057',initial,updated,{'updated_sum_formula':'3*12^(2^2024)','initial_steps':2025})

def area(points):
    return abs(sum(x*v-y*u for (x,y),(u,v) in zip(points,points[1:]+points[:1])))/F(2)
quad=[(1,0),(5,0),(0,5),(0,1)]
hept=[(0,0),(0,1),(10,-5),(7,0),(0,7),(5,0),(-1,2)]
ratio=area(hept)/area(quad)
record('aime2025:1031',360*ratio,288*ratio,{'affine_area_ratio':str(ratio)})
# Optional next candidate; normal-play DP cross-checks the residue proof.
winning=[False]*2025
for n in range(1,2025):winning[n]=any(n>=move and not winning[n-move] for move in (1,4))
assert all((not winning[n])==(n%5 in (0,2)) for n in range(2025))
record('aime2024:1008',2025//2,sum(not winning[n] for n in range(1,2025)),{'initial_strategy':'Every permitted move odd; even total gives Bob win in misere play.'})
print(json.dumps(result,sort_keys=True,indent=2))
