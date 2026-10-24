# Independent proof and contract review

Reviewer: root agent, separate from source/reference authors. Source problems and
corrections are preserved; reference code ran only in the pinned Docker sandbox.
No experimental provider response or paid call informed this review.

## Additional algorithm review

- **218, Flip Edge:** the pair (current vertex, reversal parity) is a sufficient
  state. Each move and reversal is exactly one edge of this doubled graph.
  Nonnegative costs on the released benchmark input domain justify Dijkstra.
  The literal Bellman–Ford oracle separately enumerates all transitions. The
  factor2 applies to traversal only, not reversals; scaling the final answer
  would be invalid and is not used.
- **233, ABCBA:** an appended palindrome must retain a palindromic suffix of the
  existing string. The longest such suffix uniquely minimizes the added prefix's
  reverse. The KMP sentinel is a distinct non-string object, so cannot collide
  with input characters. Reverse input and output bijectively maps the prefix
  task to the suffix task, preserving minimum length. The independent oracle
  enumerates added strings, not prefix-function values.
- **268, Reverse Brackets:** parse a valid word as an ordered forest, with an
  artificial root. A permitted reversal mirrors a consecutive list of sibling
  subtrees, including their interiors. Interior mirrors are independently
  reversible, so adjacent sibling swaps are attainable. Every permutation of
  each sibling multiset is attainable, and unordered rooted shape is invariant.
  Canonical sorted tuples exactly identify subtree types. The recursive count
  is childCount! / product(multiplicity!) times child counts; factorial inverses
  are valid for the released bound below either prime. The literal substring
  closure oracle independently checks the orbit; factorial families distinguish
  the two moduli beyond the small-case range.
- **269, Random Tree Distance:** condition on the larger vertex's uniformly
  chosen parent. For fixed u and v>u, E[d(u,v)]=A_v+S_(v−1)(u)/(v−1).
  Summing gives S_v(u)/v=S_(v−1)(u)/(v−1)+A_v/v. At u, summing over smaller
  endpoints gives (u−1)A_u+2T_(u−1)/(u−1), where T is the total expected pair
  distance. These identities justify every recurrence and prefix term in the
  implementation. Multiplication by (N−1)! changes expectation to required sum.
  Literal enumeration of every recursive parent sequence through N7 and DFS
  distances is independent of this recurrence.
- **191, K:** on nonnegative arrays sorted decreasingly, every edge in the
  unique-parent three-dimensional enumeration is nonincreasing; the priority
  frontier therefore emits exact order statistics with multiplicity. For the
  initial statement's broader integer wording, the signed fallback is necessary.
  A multiaffine polynomial attains a box maximum at a corner, even with negative
  values. Removing that corner and partitioning the remainder into three disjoint
  slabs preserves a covering by disjoint boxes. Heap maxima thus emit every
  required rank without duplicates or omissions. The initial +1 adds exactly1
  to every order statistic, justifying the upstream output transformation.
- **250, Patisserie ABC3:** maximizing pairwise max-coordinate sums is equivalent
  to choosing2K items, assigning each a coordinate, and requiring even counts
  in all three coordinate classes. Pair within each class for the forward
  direction; label each pair by a maximizing coordinate for the reverse.
  Begin with the top2K item maxima. If parity is wrong, exactly two classes are
  odd. Any alternative assignment decomposes into nonnegative-loss category
  transfers: a relabel, or an exchange of one selected and one unselected item.
  These transfers form a multigraph with exactly those two odd-degree vertices.
  Keep a simple path between them (at most two edges among three vertices);
  discard all remaining nonnegative losses. At most four item changes suffice.
  Keeping the four cheapest items for each old/new label action is exact: at
  most three other changed items can occupy those representatives, so an unused
  no-more-expensive replacement exists. The bounded DP enumerates all assignments
  of those representatives with final cardinality and parity constraints. Initial
  +1 per pair adds exactlyK; it does not alter the optimizer.

The independent root checker exhausts **5,832 signed order statistics** for191
and **80 complete category-assignment cases** for250. This uses a distinct oracle
from the author's literal-pairing check. Docker exit0 and outputs are recorded in
`root-independent-191-250.json`; the exact executed code embeds the reviewed
reference source in `root_independent_191_250.py`. Reference review is grounded in
these proofs and computations, not agreement between answer strings.

## Exclusion audit

I independently reread all excluded candidates in the reviewed coding prefix
from the pinned parquet release. For unchanged-statement exclusions I also
checked byte equality of both the problem and starter fields. Adding examples or
constraints to an unchanged core task alone supplies no changed required behavior.

The omitted-I/O candidates have no stdin serialization anywhere in their initial
statement and an empty starter. Their correction introduces the input grammar;
borrowing it for the initial turn would repair the released task. The exact
review records identify each such ID; none is excluded merely for difficulty.

Special cases:306 leaves the alphabet for a lexicographic maximum unspecified;
115 supplies a definition and method name without the requested objective or
modulus;320 permits infeasible required subarray counts without an impossible-case
return convention. Candidate270 is behavior-equivalent: permuting A or B spans
exactly the same bipartite pairings, including wildcard assignments, so existence
of a constant pair sum is unchanged.

**276 is pending, not excluded.** Its initial minimization is well-defined. The
known exact interval DP does not support the full published input sizes within
the required bounds. Failed greedy/transport shortcuts are counterexamples, not
references. Later candidates cannot replace this unresolved earlier candidate
in an order-preserving completed selection.
