# Compiled exact minimum reference for source276

This implementation preserves the released minimum objective and the existing
proved interval recurrence. It is an offline reference constructor, executed
only inside the pinned Docker construction environment. It does not execute a
model, change a source statement, alter grading inputs, or replace an unresolved
candidate with a later one. The original Python implementation and its evidence
remain available one directory above.

## Interface and arithmetic

Compile with GCC14.3.0 using:

```text
g++ -std=c++17 -O3 -DNDEBUG -Wall -Wextra -Wconversion -Wshadow reference.cpp -o reference
```

The ordinary interface reads a nonnegative length N followed by N signed decimal
integers, and prints one exact nonnegative minimum score. The `--batch` option
instead reads a case count followed by that many ordinary inputs, and prints one
answer line per case. These options affect offline construction only; they do
not alter the candidate program's ordinary stdin format. Missing tokens,
nondecimal integer tokens, extra input, unrepresentable allocation sizes, or an
allocation failure produce a nonzero exit. A partial batch stdout is not a valid
completed result unless the process exits successfully and all answers exist.

Each successful case writes a separate JSON line to stderr containing its index,
N, elapsed seconds, exact number of recurrence partner evaluations when that
number fits uint64, and arithmetic path. It does not disclose the input values.
Seconds include parsing, computation, and formatting that case's output.
`--force-exact` selects the arbitrary-precision arithmetic path even for small
inputs, allowing direct checks against the optimized path.

All decimal input integers are parsed exactly into a sign and little-endian
base10^9 limbs; leading zeros and either explicit sign are supported, and
negative zero is normalized. The custom nonnegative integer type implements
only the operations needed here: comparison, addition, subtraction with a
checked nonnegative precondition, and decimal formatting. Addition's limb sum
is at most2·10^9−1, and subtraction's temporary digit lies between−10^9 and
10^9−1. Their temporaries use64-bit types, so limb operations do not overflow.
The type places no fixed word-width bound on input values or scores.

The faster path is used only when every input fits signed64 bits and

    floor(N/2) * (maximum input − minimum input) <= UINT64_MAX.

This comparison uses division after checking a zero range, so computing the
bound cannot overflow. The distance between two signed64 inputs is calculated
by ordered unsigned subtraction, avoiding signed subtraction and `abs` at
INT64_MIN. That mathematical distance lies in[0,UINT64_MAX], so modular unsigned
subtraction gives its exact value. Every recurrence candidate contains at most
floor(N/2) pair distances, each at most the checked range. Thus every intermediate
sum and stored score is representable in uint64. UINT64_MAX itself is a valid
score: minimum candidates are initialized from an actual pairing rather than an
infinity sentinel. If the bound fails, exact limb arithmetic is used instead.

There is no fixed maximum N in this implementation. Array dimensions and cell
counts are checked before allocation; the externally imposed construction
resource limits still apply. Removing the previous small-instance guard does
not make this cubic algorithm efficient at arbitrary large N.

## Exact recurrence and odd lengths

In any complete adjacent-deletion sequence, paired original indices cannot
cross. If the leftmost index l is paired with j, the indices strictly inside
that pair must have been removed before the pair can become adjacent. Hence
j−l is odd. Conversely, a noncrossing matching can be realized by deleting
innermost pairs first. For every even interval[l,r], define D[l,r] by

    D[l,r] = min over j=l+1,l+3,...,r of
             |A[l]−A[j]| + D[l+1,j−1] + D[j+1,r].

Empty intervals have value zero. The recurrence enumerates every possible
partner, and its two remaining intervals are independent. Induction on interval
length therefore proves that it gives the exact minimum for every integer
sequence. The implementation evaluates intervals in increasing even length, so
both smaller terms have already been computed.

If N is odd, a survivor cannot lie inside any removed pair: it would prevent the
two members from becoming adjacent. The intervals on both sides must therefore
have even lengths, so the survivor's zero-based index s is even. Minimizing
D[0,s−1]+D[s+1,N−1] over all such s gives exactly the odd-length optimum. The
code handles empty sides explicitly; lengths0 and1 both yield zero.

## Packed storage and loop correspondence

Only nonempty even intervals are stored. Their total number is floor(N²/4).
Two copies of each value use different layouts: row l stores increasing right
endpoints l+1,l+3,...; column r stores increasing left endpoints of the opposite
parity to r. Offset sums are checked against the independently calculated cell
count, whose multiplication is checked for overflow.

For an interval of length2p and partner j=l+1+2k, the inside term for k>0 is
row(l+1)[k−1]. The suffix term for k<p−1 is column(r)[floor((l+2)/2)+k]. Thus
both table reads advance contiguously as k increases. The first and last
partners are evaluated separately to handle their empty intervals; all interior
k=1,...,p−2 are evaluated once. The resulting minimum is written into both
copies. This changes storage and locality only; it neither drops partners nor
alters the recurrence.

Time remains O(N³), and memory remains O(N²). The exact number of partner
evaluations is m(m+1)(2m+1)/6 for N=2m, or m(m+1)(m+2)/3 for N=2m+1.
The fast tables use16·floor(N²/4) bytes, plus linear offsets and input storage.
At the largest released input N=4736, this is89,718,784 bytes for both tables
and4,428,930,784 partner evaluations. Fixed arithmetic-path choices depend only
on input bounds, never on experimental outcomes.

## Validation record

Compilation, exact-oracle cross-checks, scaling, and full-suite generation passed
and are recorded with source and image checksums. All205 retained initial inputs
were evaluated, including all43 released tests and all162 existing independent
fixtures; the latter exactly reproduce their earlier expected outputs. A separate
square-table implementation using the split-or-enclose recurrence independently
matches all205 outputs. A literal current-sequence-deletion oracle, which uses no
interval recurrence, supplies12,142 additional exact checks spanning signed and
80-digit values, odd survivors, and machine-word boundaries. The primary source
matches all those cases in both automatic and forced arbitrary-precision modes.

The independent review approves both the recurrence/storage mapping and checked
arithmetic. No compilation or generated reference program ran on the host.
See `INDEPENDENT_REVIEW.md` for the separate review and execution evidence, and
`BENCHMARK.md` for measured execution and unchanged resource limits. The complete
construction and verification campaign used160.689484 seconds of its fixed
1800-second limit; no test reduction or feasibility exclusion was required.
