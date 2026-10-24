# Source250: exact optimal cake pairing

Each initial pair receives a bonus1; exactly K pairs are chosen. Thus every
feasible total increases by K, the optimizer is unchanged, and the complete
released corrected suite transforms exactly by adding K to each case's output.
The reference keeps the source's nonnegative integer domain and exact arithmetic.

Assign each selected cake one of its three categories, requiring an even number
in each category and2K cakes total. This has the same optimum as pairing. Any
pairing assigns both cakes the category attaining that pair's maximum, preserving
the sum. Conversely, pair cakes within each even category; actual pair prices
are at least the assigned sums. These two inequalities prove equality of optima.
The baseline chooses the2K largest individual maxima and assigns each its
deterministic first maximizing category. It is the best assignment without the
parity constraint. When its three counts are even, it already solves the problem.
Published explanations discuss this parity reformulation and baseline:
[AtCoder explanation by toam](https://atcoder.jp/contests/abc400/editorial/12621)
and [its expanded justification](https://atcoder.jp/contests/abc400/editorial/12627).
The bounded-candidate algorithm below is implemented and proved directly here.

If baseline parity is not already even, exactly two category counts are odd.
Compare any feasible optimal assignment with the baseline. Each selected cake
that changes category is a direct transfer between category nodes. Pair each
removed selected cake with a newly selected cake; their equal total counts allow
such a pairing. Each pair is another transfer from the removed cake's baseline
category to the new cake's chosen category. Every transfer has nonnegative loss:
a direct transfer cannot exceed that cake's maximum, and an exchange cannot
improve the baseline because every selected maximum is at least every unselected
maximum. These transfers use disjoint cakes.

Ignore edge directions to view the transfers as a multigraph on three category
nodes. Exactly the two originally odd nodes have odd degree; all other degrees
are even. Their common component contains a simple path between them, of length
at most2. Keep just that path's transfers and discard the rest. Selection count
is still2K, category parities are now even, all retained transfers are feasible
because they use disjoint cakes, and discarding nonnegative losses cannot worsen
the objective. Therefore some optimum consists of at most two transfers, changing
at most four cakes. Loops are unnecessary and the argument covers all edge
directions, ties, zero-valued cakes, and cases with no unselected cakes.

Give every cake one of four baseline labels: X,Y,Z, or unused. For each of the
12 ordered changes of label, retain four cakes with minimum change loss. Some
optimum changes at most four cakes. If one changed cake is outside its change
type's retained four, at least one of those four is unused by the other at most
three changes. Substituting that unused cake preserves the label-count change
and parity, and cannot increase loss. Repeating yields an optimum entirely in
the retained union of at most48 cakes. The code then performs an exact DP over
these candidates, recording number changed≤4, selected-count difference, and
parity toggles; each candidate is processed once and can keep its label or take
one new label. The terminal state has selected-count difference0 and the
required parity correction. This exhausts every needed assignment without any
randomized or approximate pruning. Sorting and scanning cost O(N log N); the
remaining DP has a constant number of candidates and states.

`../verify_191_250.py` uses a separate literal pairing oracle: it chooses the
first remaining cake, tries skipping it, or pairs it with each other remaining
cake, and recursively enumerates all legal partial matchings. It exhausts small
binary/category-basis cases and fixed-seed general cases, giving1338 checks.
All6 released files pass both versions with exact K output shifts. Root's
independent oracle instead exhausts all four-label assignments on80 small cases,
checking both category parity and selected count; its separate proof review
approves the bounded-candidate argument. Execution evidence is in
`../191_250_validation.json` and `../root-independent-191-250.json`; all reference
and oracle execution took place only in pinned Docker.
