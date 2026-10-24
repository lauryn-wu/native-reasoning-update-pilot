# Exact math reference derivations

The initial problem is the release's `revised_problem`; the subsequent correction
restores its `original_problem`. No problem or correction text is edited. Rank is
within the frozen mathematical review order, not difficulty inferred from outputs.
`verify_exact.py` was executed only in the pinned Docker sandbox; its full result
is in `verification-run.json`. These calculations use no experimental model calls.

## Rank 1 — aime2024:1004

For an odd prime p, if n⁴ ≡ −1 (mod p), the multiplicative order of n modulo p
is exactly 8. Thus 8 divides p−1, so the smallest possible odd prime is 17.
The prime 2 cannot satisfy divisibility by 4, since n⁴+1 is 1 or 2 modulo 4.
The verifier exhausts one complete residue system: the roots modulo 17² are
110,134,155,179; those modulo 17³ are 399,1022,3891,4514. Thus p=17 really
works in both versions. Requiring an even witness n changes nothing: adding the
odd modulus to any root changes its parity. The minimum positive m is therefore
**399 initially and 110 after the correction**. Enumeration of a complete
residue system proves minimality without a heuristic search cutoff.

## Rank 2 — aime2024:1027

Initially, writing the digit sum as S, replacing digit d by 2 requires
S+2−d ≡ 0 (mod 9). All digits have the same residue modulo 9. If that residue is
1,...,8, every digit equals d and 4d+2 ≡0 (mod 9) forces d=4. A mixture of 0 and 9
cannot work because S+2 is 2 modulo 9. Hence N=44444 and Q+R=44+444=**488**.
For the corrected version the verifier exhausts all 9000 four-digit integers,
checking all four replacements using exact place-value arithmetic. The only
solutions are 5624 and 5694, so the greatest is 5694 and Q+R=5+694=**699**.
Every digit position is tested by the stated substitution, including positions
already carrying the target digit; this is the usual universal digit-replacement
condition.

## Rank 3 — aime2024:1003

Write h(u)=4||u|−a|−b|, F(x)=h(sin(kπx)), and G(y)=h(cos(lπy)).
Initially (a,b,k,l)=(1/3,1/6,4,5); after correction they are (1/2,1/4,2,3).
Every intersection corresponds bijectively to a zero of R(y)=F(G(y))−y,
with x=G(y). The entire possible y domain is [0,2] initially and [0,1]
after correction, from the exact ranges of h on [−1,1].

`trig_certifier.py` exhausts these domains using outward-rounded integer interval
arithmetic at scale 10^40. A proved Machin enclosure bounds π. Sine is enclosed
using its degree63 Taylor polynomial, the explicit remainder bound 4^65/65!,
and its unit Lipschitz constant; no floating-point evaluation decides a sign.
Each completed interval either has a residual range excluding zero, or has a
strictly signed derivative enclosure and strict endpoint signs, proving zero or
one root by monotonicity and the intermediate value theorem. Intervals not
certified are subdivided without gaps. Any unresolved interval fails certification.
The two special nonsmooth/endpoint roots use the following explicit local proofs.

Initially let δ=y−2/3, |δ|≤10^−6. In this neighborhood cos(5πy)<0 and
|cos(5πy)|>1/3, so G(y)=4||cos(5πy)|−1/2|. The smooth inner function has
derivative of absolute value 20π|sin(5πy)|. Since 0.86<sqrt(3)/2<0.87 and
the sine perturbation is at most 5π·10^−6<0.000016, its derivative has constant
sign and magnitude strictly between50 and60. Thus
50|δ|≤G(y)≤60|δ|. On 0≤x≤60·10^−6 the branches give
F(x)=2/3−4sin(4πx), and −F'(x)=16πcos(4πx)>40. Consequently
R(y)≤−2000|δ|−δ<0 when δ≠0, whereas R(2/3)=0 exactly.
The excluded guard endpoints are ceil(2Q/3)−Q/10^6 and
floor(2Q/3)+Q/10^6, divided by Q, so the entire guard lies inside this proved
neighborhood and contains precisely that root. Its boundary signs are strict.

After correction let δ=1−y∈[0,10^−6]. The branches give
G(y)=1−4(1−cos(3πδ)); put ε=1−G(y). Then
F(G(y))=1−4sin(2πε). Using 1−cos(t)≤t²/2 and sin(t)≤t for t≥0,
1−F(G(y))≤8πε≤144π³δ²<5000δ². Hence R(y)≥δ−5000δ²>0
for δ>0, and R(1)=0 exactly. This proves the unique root in the final guard.

The complete primary certificate has no unresolved intervals and records
**1243 simple roots plus the exact cusp root, for1244 initially**, and
**384 simple roots plus the exact endpoint root, for385 after correction**.
`TRIG_INDEPENDENT_REVIEW.md` audits all enclosures and coverage. A second Docker
certificate raises the scale to10^45 and changes the split from one-half to
one-third; it independently exhausts both domains and gives the same counts with
no unresolved intervals. The two full root-bracket outputs are retained.

## Rank 4 — aime2024:1025: excluded, no revised configuration

A convex equiangular hexagon has each interior angle 120 degrees: their sum is
720 degrees. Successive side directions rotate by 60 degrees. The three lines
containing AB, CD, EF therefore have directions differing by 120 degrees, and
the triangle they bound is equilateral (each interior angle is 60 degrees).
Its stated side lengths 180,216,270 are unequal. No such initial configuration
exists. The missing reference is not repaired by changing equiangular to equilateral.

## Rank 5 — aime2024:1024

Let A=log₂x, B=log₂y, C=log₂z, and let right-hand sides be a,b,c. The nonsingular
linear system gives A=−(b+c)/2, B=−(a+c)/2, C=−(a+b)/2. Every real A,B,C gives
unique positive x,y,z, so no existence or branch issue remains. Substitution gives
initial |4A+5B+2C|=141/80 and corrected |4A+3B+2C|=25/8, each already reduced.
The answers are **221 and 33**. The verifier checks the original linear equations
with exact Fractions before calculating the target.

## Rank 6 — aime2025:1058: excluded, triangle inequality

Initially ∠B=90 degrees and BC=40, so the hypotenuse AC is strictly greater than
40. But AL=CL=18 implies AC≤AL+LC=36, even without requiring L to be interior.
This is an immediate contradiction. No approximate geometry or assumption about
the requested radical form is needed to exclude the initial problem.

## Rank 7 — aime2024:1013: excluded, missing positioning condition

Neither supplied text says that every circle is tangent to a common third side.
That missing condition cannot be inferred or added. Here are two explicit families
satisfying the actual words. Take a right-isosceles triangle with designated rays
on the positive axes and leg length L, with L=5000 or 6000. For any n,r use circle
centers ((2j+1)r,r), j=0,...,n−1, radius r. Adjacent circles are tangent. Every
circle is tangent to the horizontal ray and the first is tangent to the vertical
ray, so two distinct designated circles can satisfy the stated endpoint tangencies.
All circles lie strictly below the hypotenuse when L>2nr+sqrt(2)r.
Both n=7,r=51 and n=2048,r=1 fit at either L. The corrected n=8,r=34 and n=2024,r=1
also fit at either L. Name the right-angle vertex A for AB/AC in the revised text,
or B for AB/BC in the corrected text. The inradius is L/(2+sqrt(2)), which differs
for 5000 and 6000. Thus the source wording does not determine an inradius in either
version. The circles need only be arranged separately, as the problem states.

## Rank 8 — aime2025:1030

Initially 251_b=2b²+5b+1=b(2b+5)+1=b·25_b+1. Since b>12 gives 25_b>1,
no base qualifies. The product over the empty set is the standard multiplicative
identity **1**; the question does not assert a nonempty solution set. This is a
valid empty product, not a guessed reference. In the updated version
97_b=9(b+7)−56, so b+7 divides 56 and exceeds 16. The possibilities are 28 and56,
namely b=21,49, whose sum is **70**.

## Rank 9 — aime2024:1006: excluded, false rationality premise

For fixed ab+bc+ca=48 and abc=24, the maximum squared box diagonal occurs with
two equal sides x,x,z. Existence of a maximum follows from positivity and the
fixed positive volume and bounded pair-sum; Lagrange subtraction gives
(a−b)(2+λ+μc)=0 cyclically, so a stationary point has two equal sides unless all
three are equal. All three equal is incompatible with the two constants.
Then z=24/x² and x³−48x+48=0. The cubic has no integer root among the divisors
of48, so is irreducible over the rationals. Setting s=x² also gives degree3:
x=48/(48−s), and s³−96s²+2304s−2304=0. The squared diagonal is
D=2s+576/s²=(s²−87s+2208)/4, using the cubic relation. If D were rational,
s would satisfy a nonzero quadratic with rational coefficients, contradicting
its degree3. Thus the squared minimum enclosing sphere diameter is irrational,
whereas the initial question asserts it is p/q for positive integers. This
exclusion is about a false premise, not the grader's former rational limitation.
(The identity for D is checked separately in `verify_exclusions.py`.)

## Rank 10 — aime2025:1059: excluded, unbounded function

For positive k, the numerator is monic quartic and the denominator is x, so
f(x)→+infinity as x→+infinity. It has no global maximum as required initially.
Moreover, with the literal real domain x≠0, f(x)→−infinity as x→−infinity, so
there is no global minimum in the corrected text either. The supplied answer240
cannot validate this literal version. A positive-x domain or a different denominator
would be an unauthorized modification. No such repair is made.

## Rank 11 — aime2025:1044

For each variant set M to its divisibility modulus and let c(r) count the allowed
integers whose cube is r modulo M. There are exactly
Σ_{r=0}^{M−1} Σ_{s=0}^{M−1} c(r)c(s)c(−r−s mod M) ordered triples. This formula
is a partition by the first two cube residues and independently counts all choices
of the third integer, including repeated coordinates and all ordering multiplicities.
The checker exhausts every allowed integer, then every pair of nonzero residue
frequencies using integer arithmetic. Initially it counts 10,174,168 triples,
whose remainder modulo729 is **244**. After correction it counts 885,735 triples,
whose remainder modulo1000 is **735**. Direct triple enumeration for eight smaller
bounds additionally cross-checks the counting implementation; the reference itself
uses the complete stated domains, not the smaller tests.

## Rank 12 — aime2024:1028: excluded, contradictory tangencies

Initially the torus has major radius8 and tube radius4, so its maximum distance
from the axis is12. It cannot rest inside the sphere of radius11 with internal
tangency as claimed. In an axial cross section, internal tangency would require
√(8²+h²)=11−4=7, impossible for real h. In the corrected release text both r_i and
r_o describe precisely the same outside/external tangency configuration. For
major radius6,tube radius3,sphere radius11, either external contact has radius
11·6/(11+3)=33/7, so their difference is0, inconsistent with positive m,n and the
published127. The correction explicitly repeats this external/external wording;
we preserve it and do not import a different intended contest statement.

## Rank 13 — aime2025:1049: excluded pending independent ambiguity review

The initial prose changes B,C to54,42 degrees and J's defining segment to CF,
but includes the unchanged executable Asymptote diagram: A=(Cos(60),Sin(60)),
C=(Cos(60)+Sin(60)/Tan(36),0), and J=intersectionpoints(A--F,circ)[0]. Thus the
statement's explicit diagram and its 'as shown' arc specification instead describe
angles60,36 and J on AF. The two definitions of J are distinct: AF and CF intersect
only at F, while the statement enumerates J and F as separate points. If J were
simultaneously on both segments it would equal F, contradicting six distinct minor
arcs. Resolving this requires deleting/replacing supplied geometric information.
This is a concrete conflicting-specification exclusion, not a hard-case exclusion.

## Rank 14 — aime2025:1042

Uniform independent perimeter choices conditioned on the allowed quadrant pairs
make the four adjacent unordered pairs equiprobable initially, and the six different
unordered pairs equiprobable after correction. Probability-zero coincidences and
multiple crossings need not affect the expectation. Each extra chord adds one
region plus its intersections with existing segments. An adjacent-quadrant chord
crosses exactly one of the fixed diameters; a different-quadrant chord crosses
one for four pairs and two for two pairs, giving mean4/3.
For two adjacent-quadrant chords, their quadrant pairs agree with probability1/4
or share one quadrant with probability1/2; conditional crossing probability is1/2
in either case, hence3/8. For different-quadrant chords: equal pair contributes1/12;
sharing one quadrant contributes1/3; disjoint pairs cross only for the alternating
opposite-quadrant pairing, contributing1/18. Total17/36. The verifier independently
enumerates all quadrant pairs and all within-quadrant endpoint orderings, using
exact Fractions and cyclic alternation as the crossing criterion.
Initial expectation=4+31·2+C(31,2)·3/8=**1923/8**. Updated expectation=
4+25·7/3+C(25,2)·17/36=**204**.

## Rank 15 — aime2024:1012

Put z=4(cosθ+i sinθ). For coefficients a+bi,c+di the real part is
(4a+c/4)cosθ+(−4b+d/4)sinθ, whose maximum is the Euclidean norm of its two
coefficients, attained by the unit vector parallel to them. Initially these are
363 and−331, so the maximum is **sqrt(241330)**. After correction they are324
and−432, giving **540**. This is a valid irrational initial answer; it requires
exact radical grading, not exclusion or rounding.

## Rank 16 — aime2024:1016

Write A for the vertex where AI⊥OI (relabel the initial B as A), and use opposite
side a, adjacent sides b,c, semiperimeter s, circumradius R and inradius r.
Euler's identity OI²=R(R−2r), together with OA²=OI²+IA², gives IA²=2Rr.
Since IA=r/sin(A/2), sin²(A/2)=r/(2R). Standard area and half-angle identities give
bc=4Rrs/a and bc=2Rrs/(s−a), respectively. Equating these yields a=2s/3 and
bc=**6Rr**. Both radii admit such a triangle: choose A with sin²(A/2)=r/(2R),
and choose B,C with B+C=π−A and cos((B−C)/2)=2sin(A/2). Here 0<r<R/2,
so these equations give positive B,C; their difference is smaller than their sum.
The half-angle product then gives the specified r and R. Thus the product is
**714 initially and468 after correction**, not merely a necessary value for an
empty geometric constraint set.

## Rank 17 — aime2025:1053

For sin(qπ sin u)=0, sin u=k/q for integers −q≤k≤q. Over P full periods with
both outer interval endpoints omitted, each of the2q−2 nonzero nonextreme levels
has2P solutions; level0 has2P−1; the two extreme levels together have2P. Thus
n=(2q−1)2P−1+2P. Exactly the2P extreme-level solutions have zero first derivative
and nonzero second derivative, hence are tangencies; all other zero crossings
have nonzero derivative. Initially q=9,P=6 gives n=215,t=12 and **n−t=203**.
Updated q=7,P=5 gives n=139,t=10 and **n+t=149**.

## Rank 18 — aime2024:1019

Because11 and13 are prime, every nontrivial root of unity in each question is
primitive, so the product covers all roots of z^n−1 exactly once. Let α,β be
roots of z²−2z+c. The product is (α^n−1)(β^n−1)=c^n−S_n+1, where
S_n=α^n+β^n, S_0=S_1=2, and S_n=2S_{n−1}−cS_{n−2}. This integer recurrence is
an exact resultant evaluation. Initially c=3,n=11 gives177542, hence **42 mod625**.
Updated c=2,n=13 gives8321, hence **321 mod1000**.

## Rank 19 — aime2025:1037: excluded, positive-fraction premise false

Initially write z=x+iy. The distance equality simplifies to x−3y−k+8=0.
Its distance from the center(25,20) is |k+27|/sqrt(10). Tangency to the radius10
circle requires k=−27±10sqrt(10), two distinct real possibilities. Their product
is729−1000=−271, which cannot be m/n for positive integers m,n as requested.
This is a false positivity premise, not a numerical approximation issue.
For comparison the updated equality is8x−6y−8k−7=0; tangency to radius5 gives
k=23/8,123/8, sum73/4 and the published answer77. The initial contradiction
alone excludes the pair; no sign change is silently introduced.

## Rank 20 — aime2025:1057

Initially if x=m/n is reduced, the next numerator m²+mn+n² is coprime to mn
and is odd whenever m,n are coprime. Thus (m²+mn+n²)/(2mn) is reduced at every
step. Exact numerator/denominator arithmetic may therefore be reduced modulo1000
at each step without a later cancellation changing the residue. Starting26,11,
2025 transitions give **809** for x_2026's numerator+denominator modulo1000.

For the corrected recurrence start m=25,n=11,s=m+n=36. With m,n coprime,
nonzero modulo3 and s divisible9, gcd(m²−mn+n²,3mn)=3: the numerator is s²−3mn,
so after dividing by3 its residue is−mn≠0 (mod3). The reduced next pair is
((m²−mn+n²)/3,mn), remains coprime and nonzero modulo3, and has new sum s²/3,
still divisible9. Induction proves these facts forever. Consequently
s_k=3·12^(2^(k−1)); at k=2025 its residue modulo1000 is **248**. The checker uses
modular exponentiation of this proved exact integer formula and separately checks
the cancellation invariant over the first eight exact terms.

## Rank 21 — aime2025:1031

Both versions have D,E at1/7,5/7 along AB and F,G at1/7,5/7 along AC. Use an
invertible affine map to put A=(0,0),B=(7,0),C=(0,7), so D=(1,0),E=(5,0),
F=(0,1),G=(0,5). Reflections through a point give M=2F−D=(−1,2),N=2E−G=(10,−5).
Shoelace areas are12 for DEGF and49/2 for AFNBCEM; ratio49/24 is preserved by
every affine map. The specified side lengths and areas are consistent: sin A
is less than1 in each case (quadrilateral area=(12/49)AB·AC·sin A).
Thus the desired areas are360·49/24=**735** initially and288·49/24=**588** updated.

## Rank 22 — aime2024:1008 (extra candidate only)

Initially every legal move is odd, so the parity of the number of moves equals
the parity of n, whatever choices the players make. With last-mover losing and
Bob first, Bob wins exactly for even n. There are **1012** such positive integers
through2025. After correction normal-play losing positions are n≡0,2 (mod5):
from either residue every move reaches a winning residue, and from every other
residue a legal move1 or4 reaches a losing residue. Induction from n=0 proves
the pattern. Through2024 there are404 complete blocks of5 and one further residue2,
so **809** losing first-player positions, precisely Bob's guaranteed wins.
The checker cross-checks all2025 normal-play states by independent dynamic programming.
This extra reference does not authorize selecting it past unresolved earlier cases.
