# Source191: exact kth order statistic

The source text and correction are unchanged. The pilot initial version adds1 to
each expression; the corrected version removes it. Because adding a common
constant preserves all ranks, including multiplicities, every original-version
reference output is the corrected output plus1. This transforms the complete
released suite without guessing missing expected outputs.

The initial statement says integer arrays without a positivity restriction.
The reference therefore supports signed values, even though the correction's
released constraints require positive values. It counts index triples rather
than distinct numeric values, preserving ties correctly.

For nonnegative arrays, sort each array in descending order. The expression
ab+bc+ca is nondecreasing in each coordinate value because its coefficient is
the sum of the other two nonnegative values. Define the unique parent of an
index triple by decreasing its third index if positive, else its second if
positive, else its first. The root is(0,0,0). Every edge has nonincreasing value.
A max heap traverses this tree, emitting the largest remaining value at each
step: the first unvisited ancestor of any unvisited triple lies in the heap and
has at least that triple's value. The explicit child rules implement this unique
parent relation, so no visited set or duplicate elimination changes multiplicity.

For signed arrays, sort in ascending order and partition the remaining index
triples into disjoint boxes. The expression is affine separately in each variable.
On any box its maximum is therefore attained at one of its eight corners: fix
two variables and move the third to a maximizing endpoint, and repeat. This
argument applies to the discrete sorted values as well as their containing
continuous intervals. Heap entries hold the true maximum and its chosen corner.
Popping a box emits that corner's value, which is the maximum across all
remaining triples. Remove the corner by three disjoint slabs: the first allows
every first index except the corner's endpoint; the second fixes that first
index and allows every second index except its endpoint; the third fixes the
first two and excludes the third endpoint. Each other triple belongs to exactly
one slab according to its first differing coordinate. Empty slabs are discarded.
This preserves a complete disjoint partition after each pop, proving the order
statistic algorithm for all signs. Equal values remain separate index triples.

Both methods use O(N log N+K log K) time and O(N+K) space; the signed method
has a larger constant for corner evaluations. Integer arithmetic is exact.

`../verify_191_250.py` exhausts all ranks for length2 arrays over{-1,0,1},
exhausts length2 arrays over{1,2}, and checks fixed-seed larger small arrays
against literal enumeration of all N³ expressions. It checks7123 initial and915
valid-positive corrected cases. All43 released input/output files pass the
corrected reference and the exact plus1 transformation. The separate root
review also exhausts5832 signed rank cases, with its own implementation and
record in `../root-independent-191-250.json`. Full evidence and fixed fixtures
are retained in `../191_250_validation.json` and
`../191_250_independent_cases.json`. All executions occurred in pinned Docker.
