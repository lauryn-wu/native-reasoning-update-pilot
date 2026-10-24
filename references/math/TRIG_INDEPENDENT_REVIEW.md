# Independent review of the trigonometric reference certificate

Reviewer: `provider`, separate from the primary certificate author, `root`.
The review concerns exact mathematical bounds, source correspondence, and complete
domain coverage. Agreement of approximate model answers is not evidence here.
All reference programs ran only in the pinned Docker sandbox; no paid API call
or experimental model outcome was used.

The reviewed primary source is `trig_certifier.py`, SHA256
`b51bf740869a2a976b9b1cb5fd46a8455eea9d882ab7939dc7f3d1b22cfdb235`.
The primary execution is recorded in `trig-verification-run.json` and completed
with exit0 and empty stderr. The independent source is
`trig_independent_check.py`, SHA256
`ab6d30f5e541da280a459a3dec343c0b2d1267b0bc1bab5a9119b5f42825e69f`.
Its execution is recorded in `trig-independent-run.json`, completed with exit0
and empty stderr, using image
`python@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704`.

## Source correspondence and domain

The code's variant named `original` denotes the pilot initial/source revised
problem: a=1/3, b=1/6, k=4, l=5. The code's `updated` variant denotes the
source original problem: a=1/2, b=1/4, k=2, l=3. The mapping is checked against
the unchanged source pair. With F(x)=h(sin(kπx)) and G(y)=h(cos(lπy)), where
h(u)=4||u|−a|−b|, a solution corresponds uniquely to a residual root
F(G(y))−y=0. The nonnegative ranges of h restrict the complete y domains to
[0,2] and [0,1], respectively. No intersection outside these domains is possible.

## Outward enclosure audit

- Integer interval endpoints represent rational numbers with denominator Q.
  Addition, negation, multiplication, and rational construction all use exact
  integer arithmetic and directed floor/ceiling bounds. Multiplication considers
  all four endpoint products. Absolute value and sign intervals include zero and
  every possible branch when an interval meets a kink.
- Machin's identity π=16atan(1/5)−4atan(1/239), evaluated by alternating series,
  includes a next-term remainder with the correct sign. Every rational term is
  enclosed before summation. The fixed term counts give strict enclosing bounds.
- Sine range reduction subtracts an integer multiple of the enclosed2π; any
  integer multiple is valid, and the resulting argument is checked inside[−4,4].
  The degree63 odd Taylor polynomial is also the degree64 Taylor polynomial,
  since its even coefficient is zero. Thus its Lagrange remainder is bounded by
  4^65/65!. The checked integer inequality makes this less than1/Q. Horner
  evaluation uses interval arithmetic, including all rounding errors; one final
  unit on each side adds the analytic remainder. The interval sine wrapper uses
  the exact bound |sin(u)−sin(v)|≤|u−v|. Clamping to[−1,1] preserves inclusion.
  Cosine uses an outward enclosure for the π/2 phase shift.
- The derivative intervals include every classical derivative wherever it
  exists. At the finitely many absolute-value kinks they include both branch
  slopes. These functions are locally Lipschitz, so a strictly positive or
  negative derivative enclosure implies strict monotonicity throughout an
  interval, including across kinks. Composition uses the correct chain rule and
  subtracts1 for the residual derivative.

## Exhaustion and root uniqueness

Each interval is accepted only by a strictly signed residual range, or a strictly
signed derivative with strictly signed endpoint residuals. The latter proves no
root for equal endpoint signs and exactly one for opposite signs. The direction
of the sign change is checked against the derivative. Otherwise the interval is
split into two closed intervals with the same shared endpoint and no gap. Root
brackets have nonzero endpoints, so a shared endpoint cannot be double counted.
The explicit depth and minimum-width limits produce unresolved entries rather
than silently assuming there are no tangent roots. Both runs have no such entries.

The two analytic guards are fully proved in the rank3 section of `proofs.md`.
I independently checked their local branches and constants. Initially,
50|δ|≤G(2/3+δ)≤60|δ| and −F'(x)>40 imply a strict negative residual off the
exact cusp root. The final guard uses ceil at the lower rational center and floor
at the upper center, so it stays within the proved radius10^−6; this avoids the
one-quantum extension in an earlier draft. After correction,
R(1−δ)≥δ−5000δ²>0 on0<δ≤10^−6 proves the sole endpoint root. The guard
boundaries themselves have strict signs, and the interval search covers all
remaining points, including the opposite domain endpoint.

## Perturbed certificate and conclusion

The second checker uses Q=10^45 and an asymmetric one-third split instead of the
primary scale10^40 and midpoint split. These changes alter every subsequent
partition and the rounding error bound. This is a second exact execution of the
audited method, not a claim of a separate mathematical algorithm.

| Version | Primary count | Independent count | Unresolved intervals |
| --- | ---: | ---: | ---: |
| Pilot initial / source revised |1244|1244|0 in both runs|
| Pilot updated / source original |385|385|0 in both runs|

The complete root brackets, π enclosures, scales, and partition statistics are
saved in the execution artifacts. The reviewed proof and complete certificates
approve exact references **1244 initially and385 after correction**.
