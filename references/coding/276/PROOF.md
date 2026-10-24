# Source276: pending initial reference, verified corrected reference

The actual initial task minimizes the sum of adjacent-deletion scores; the
correction maximizes it. No statement is rewritten and neither objective is
treated as a constant transformation of the other. This candidate remains
**pending**, not excluded for difficulty. Later qualified candidates cannot
replace it when freezing the first eligible deterministic prefix.

Every complete deletion sequence gives a noncrossing matching of original
indices: if i pairs with j, all indices strictly between them must disappear
before that operation. Crossing pairs cannot both become adjacent. Conversely,
every noncrossing perfect matching is realizable by deleting innermost pairs
first. For an even interval[l,r], its leftmost index can pair with any
j=l+1,l+3,...,r. The minimum score is therefore exactly

    D[l,r] = min_j (abs(A[l]-A[j]) + D[l+1,j-1] + D[j+1,r]),

where empty intervals have score0. This enumerates all possible partners and
independent inside/right submatchings. For odd N the survivor has an even number
of indices on both sides, hence an even zero-based index s. The answer is
min_s(D[0,s-1]+D[s+1,N-1]). These recurrences prove the small-instance reference.

However, this exact DP takes O(N³) time and O(N²) memory. For even N=2m the
number of partner transitions is m(m+1)(2m+1)/6. The released suite includes
N=4736, requiring4,428,930,784 such transitions for that case alone. The stated
corrected limit N=300000 would require1,125,011,250,025,000 transitions. The
initial implementation explicitly rejects N>240; this resource guard is a
qualification blocker, not a change to eligible problem inputs. It has not
verified the full initial released suite, so this pair cannot be qualified.

Two tempting faster replacements are disproved by exact exhaustive deletion:

- For[0,4,5,9], deleting the cheapest adjacent pair first scores1+9=10, but
  deleting(0,4) and(5,9) scores8, the true minimum.
- For[0,50,100,1,50,101], unconstrained sorted odd/even-index transport costs2,
  but those pair arcs cross. The true legal minimum is100. Thus an unconstrained
  bipartite assignment does not solve adjacent deletion.

For the corrected maximum on an even interval, the sum of the largest half
minus the smallest half is an upper bound. Label the two halves with opposite
signs; any sequence containing both signs has an adjacent opposite-sign pair.
Delete such a pair repeatedly to achieve the bound. For odd N, consider every
permitted survivor and add the bounds for its left and right even intervals.
Two median heaps maintain each prefix's half sums; repeating on the reversed
array yields suffix sums. This gives the exact maximum in O(N log N) time and
O(N) space, including ties. This standard corrected-objective argument is also
given in the [official editorial](https://atcoder.jp/contests/arc196/editorial/12638).

`../verify_276.py` checks9999 small sequences using a literal recursive oracle
that tries every currently adjacent pair, independently of either reference DP
or median algorithm. This includes complete ternary sequences through length8,
signed random sequences, and the two counterexamples. All43 released corrected
files pass, as do corrected constant-array size299999 and300000 checks. Positive
translations of any signed/zero fixtures are stored for the corrected domain;
translation leaves all absolute differences unchanged. `validation.json` records
the complete evidence and explicitly marks the initial full-suite validation
unavailable. All executions occurred only in pinned Docker; no experimental
model outputs were used to select or assess this candidate.
