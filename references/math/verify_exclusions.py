"""Exact arithmetic supplement for exclusion proofs; Docker execution only."""
import json
from fractions import Fraction as F
# Cubic x^3-48x+48 has no rational root: monic rational roots divide48.
divisors=[i for i in range(1,49) if 48%i==0]
assert all(x**3-48*x+48 for d in divisors for x in (d,-d))
# s^3-96s^2+2304s-2304=0 gives the squared diagonal identity.
# Multiplying D=2s+576/s^2 by 4s^2 yields 8s^3+2304.
# Subtract (s^2-87s+2208)s^2; the difference is exactly
# -(s+1)(s^3-96s^2+2304s-2304).
# Derive the correct quadratic representative by exact reduction in Q[s].
P=[-2304,2304,-96,1]
def reduce_poly(poly):
    poly=list(map(F,poly))
    while len(poly)>3:
        coeff=poly[-1];shift=len(poly)-len(P)
        for i,p in enumerate(P):poly[i+shift]-=coeff*p
        poly.pop()
    return poly
# Check (2s + 576/s²) == (s² - 87s + 2208)/4 by multiplying through by4s².
difference=[2304,0,-2208,95,-1]
assert reduce_poly(difference)==[0,0,0]
print(json.dumps({'aime2024:1006':{'monic_cubic_rational_roots':[], 'squared_diagonal_quadratic_identity_verified':True}},indent=2))
