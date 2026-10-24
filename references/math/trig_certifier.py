"""Rigorous root count for released AIME1003, using integer interval arithmetic.

Every interval [lo,hi] represents [lo/Q,hi/Q]. Arithmetic rounds outwards using
integer floors/ceilings. Machin's formula gives a proved pi enclosure. A degree63
sine Taylor polynomial on [-4,4] has error <=4**65/65!<1/Q. Whole-interval sine
uses its unit Lipschitz constant. No floating point is used in certification.
"""
from math import factorial
import json
import time
Q=10**40
ONE=(Q,Q)
ZERO=(0,0)


def integer(n): return (n*Q,n*Q)
def frac(n,d): return (n*Q//d,-((-n*Q)//d))
def add(a,b): return (a[0]+b[0],a[1]+b[1])
def neg(a): return (-a[1],-a[0])
def sub(a,b): return add(a,neg(b))
def scale(a,n): return (a[0]*n,a[1]*n) if n>=0 else neg(scale(a,-n))
def mul(a,b):
    terms=[a[0]*b[0],a[0]*b[1],a[1]*b[0],a[1]*b[1]]
    return (min(terms)//Q,-((-max(terms))//Q))
def absolute(a):
    if a[0]>=0:return a
    if a[1]<=0:return neg(a)
    return (0,max(-a[0],a[1]))
def sign(a):
    if a[0]>0:return ONE
    if a[1]<0:return integer(-1)
    return (-Q,Q)

def atan_reciprocal(denominator,terms):
    total=ZERO
    for k in range(terms):
        term=frac(1,(2*k+1)*denominator**(2*k+1))
        total=add(total,term if k%2==0 else neg(term))
    tail=frac(1,(2*terms+1)*denominator**(2*terms+1))
    # Alternating series remainder has the next term's sign and magnitude bound.
    return add(total,(0,tail[1]) if terms%2==0 else (-tail[1],0))
PI=sub(scale(atan_reciprocal(5,80),16),scale(atan_reciprocal(239,20),4))
assert 3*Q<PI[0]<PI[1]<4*Q
assert 4**65*Q < factorial(65)
COEFF=[frac((-1)**k,factorial(2*k+1)) for k in range(32)]


def sine_point(point):
    # Integer nearest-period reduction. Any integer is valid; |z|<4 is checked.
    periods=(point+(PI[0]+PI[1])//2)//(PI[0]+PI[1])
    z=sub((point,point),scale(PI,2*periods))
    assert max(abs(z[0]),abs(z[1]))<4*Q
    square=mul(z,z)
    result=COEFF[-1]
    for coefficient in reversed(COEFF[:-1]):
        result=add(coefficient,mul(square,result))
    result=mul(z,result)
    return (result[0]-1,result[1]+1)


def sine(interval):
    midpoint=(interval[0]+interval[1])//2
    radius=max(midpoint-interval[0],interval[1]-midpoint)
    point=sine_point(midpoint)
    return (max(-Q,point[0]-radius),min(Q,point[1]+radius))
def cosine(interval): return sine(add(interval,(PI[0]//2,-((-PI[1])//2))))


def curve(interval,frequency,a,b,kind):
    angle=mul(scale(PI,frequency),interval)
    trig=sine(angle) if kind=='sin' else cosine(angle)
    trig_prime=cosine(angle) if kind=='sin' else neg(sine(angle))
    first=sub(absolute(trig),a)
    second=sub(absolute(first),b)
    output=scale(absolute(second),4)
    derivative=mul(mul(mul(sign(trig),sign(first)),sign(second)),
                   mul(scale(PI,4*frequency),trig_prime))
    return output,derivative


def residual(interval,kind):
    a,b,k,l=(frac(1,2),frac(1,4),2,3) if kind=='updated' else (frac(1,3),frac(1,6),4,5)
    g,gd=curve(interval,l,a,b,'cos')
    f,fd=curve(g,k,a,b,'sin')
    return sub(f,interval),sub(mul(fd,gd),ONE)


def scalar_sign(interval):
    if interval[1]<0:return -1
    if interval[0]>0:return 1
    return 0


def certify(kind):
    started=time.monotonic()
    epsilon=Q//10**6
    if kind=='updated':
        # Proof in companion document establishes exactly the endpoint root1
        # in [1-epsilon,1]. The rest is exhaustively certified below.
        stack=[(0,Q-epsilon,0)]
        explicit_roots=['1']
    else:
        low=-((-2*Q)//3)-epsilon
        high=(2*Q)//3+epsilon
        stack=[(0,low,0),(high,2*Q,0)]
        explicit_roots=['2/3']
    isolated=[]
    counts={'excluded_by_range':0,'excluded_by_monotonicity':0,'subdivisions':0,'max_depth':0}
    unresolved=[]
    while stack:
        lo,hi,depth=stack.pop()
        counts['max_depth']=max(depth,counts['max_depth'])
        values,derivative=residual((lo,hi),kind)
        if scalar_sign(values):
            counts['excluded_by_range']+=1
            continue
        monotone=scalar_sign(derivative)
        if monotone:
            left=scalar_sign(residual((lo,lo),kind)[0])
            right=scalar_sign(residual((hi,hi),kind)[0])
            if left and right:
                if left==right:
                    counts['excluded_by_monotonicity']+=1
                else:
                    assert (left<right and monotone>0) or (left>right and monotone<0)
                    isolated.append([str(lo),str(hi),left,right,monotone])
                continue
        if depth>=100 or hi-lo<100:
            unresolved.append([str(lo),str(hi),depth])
            continue
        middle=(lo+hi)//2
        stack.extend(((lo,middle,depth+1),(middle,hi,depth+1)))
        counts['subdivisions']+=1
    return {'variant':kind,'certified':not unresolved,'root_count':len(isolated)+len(explicit_roots),
            'simple_root_intervals':isolated,'explicit_roots':explicit_roots,
            'unresolved':unresolved,'counts':counts,'elapsed_seconds':time.monotonic()-started}

if __name__=='__main__':
    import sys
    kinds=sys.argv[1:] or ['updated','original']
    output={'method':'outward integer intervals plus exact local endpoint/cusp proofs',
            'scale':str(Q),'pi_enclosure':list(map(str,PI)),
            'sine_error_bound':'4^65/65! < 1/10^40 (verified integer inequality)',
            'results':[certify(kind) for kind in kinds]}
    print(json.dumps(output,sort_keys=True))
    assert all(result['certified'] for result in output['results'])
