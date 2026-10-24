# Grading and analysis contract

The released source graders are audited as source text, never imported or
executed on the host. The source Python evaluator uses host execution and its
`reliability_guard` is not an isolation boundary. Compressed upstream tests are decoded only inside Docker with a restricted
unpickler that rejects class/global lookup and persistent IDs; JSON leaves the
container. No pickle payload is deserialized on the host. The source math
grader's last-number extraction is too permissive for exact scoring.

The released initial problem is the **revised** problem; the correction changes
it back to the source **original** problem. The release omits the initial revised
math answers and omits the coding test assets needed for both variants. Verified reference construction now supplies separately reviewed initial answers
and tests; the baseline audit remains historical evidence. Candidate276 still
prevents completing the ordered coding sample. Software fixtures never replace
pilot cases. The explicit user policy blocks all paid execution, independently
of whether source qualification eventually passes.

## Exact mathematical answers

`exact_answer` accepts the final `\\boxed{...}` or `\\fbox{...}`, an explicit final
answer line, or a standalone exact expression. It does not search prose for a
matching number. Safe bounded AST traversal supports rational arithmetic,
decimal/scientific notation, simple LaTeX fractions, and integer powers. Numeric
source tokens are converted to exact `Fraction` values, avoiding float rounding.
Bounded nonnegative rational square roots are also supported. Trusted SymPy
constructors build each AST node; exact equality is tested in an algebraic number
field. No string `sympify`, `parse_expr`, Python `eval`, imported benchmark
evaluator, arbitrary user function call, or floating tolerance is used. Unsupported expressions are invalid output and unsuccessful in
operational accuracy. The admissible grammar must be included in the frozen
task instructions before any paid run; future extensions require a new freeze.

Original and updated authoritative answers must differ. Qualification accepts
the answer and an equivalent doubled numerator/denominator representation,
rejects wrong answers, and rejects/classifies the old answer after an update.
An old-answer match is descriptive and is not evidence of a reasoning mechanism.

## Coding programs and isolation

The implemented coding formats are Python stdin/stdout and the released
class/method interface with positional JSON arguments. It accepts one Python
fence or a bare Python program, checked with parse-only `ast.parse`. Function submissions receive a released-evaluator-compatible standard-library
prelude inside Docker. Their returned JSON values are compared exactly on the
host; tuple/list serialization is equivalent, while booleans are distinguished
from numbers. Multiple files, alternate languages, floating tolerance, and
interactive tasks remain unsupported.

Docker is mandatory. The image is pinned to the official local Python 3.12-slim
digest recorded in `sandbox/runner.py`; qualification records the resolved image
ID, architecture, and Docker version. Images are never pulled during grading.
Each bounded test batch runs in a fresh container with network disabled, user 65534, read-only
root filesystem, all capabilities dropped, no-new-privileges, one CPU, task-bound memory/swap (256–768 MiB for current references), 32
processes, 64 file descriptors, a 16 MiB temporary filesystem, a bounded
wall-clock limit (at most60 seconds), and at most4 MB per output stream.
Published and independent tests are all retained; batches bound input/output
size without dropping cases. stdin cases run in fresh Python subprocesses;
function cases initialize a fresh module namespace and class instance.
The only bind mount contains the submitted `main.py`, mounted read-only.
No host credentials, grader, expected outputs, test archive, Docker socket,
checkpoint, or provider environment is mounted or forwarded. Only invocation inputs are piped into the container; expected outputs stay outside. Host-side code performs authoritative stdout
comparison after execution, with inter-token whitespace normalized and no numeric tolerance. Candidate258
explicitly requests case-insensitive winner names, so that task alone enables
case folding. The checked test-asset hash fixes this setting. A program cannot declare itself passed.

Timeout/output limits force-remove the named container as well as terminating
the Docker client. A separate container-side PID1 timeout bounds execution even
if the host runner dies. No host execution fallback exists. `qualify_docker()` tests
correct, equivalent, wrong, and stale software examples; network/filesystem/user
restrictions; missing credentials; cgroup CPU/memory/process ceilings; and wall
time/output bounds. These checks are `software_sandbox_only`, explicitly distinct
from source/reference qualification. Containers are a practical isolation
boundary, not a proof against all runtime/kernel vulnerabilities.

`qualify_references(tasks)` requires both variants' authoritative assets and,
for coding, both reference programs. It executes them only inside Docker,
cross-checks the update, rejects deliberately failing code, and confirms an
equivalent whitespace variant. An empty task set fails. This validates supplied
assets; provenance, independent derivations, and update ambiguity are independent
source-audit gates. `qualify-reviewed` can validate every completed candidate
reference while recording that the ordered campaign selection remains blocked.
It cannot authorize payment or invent a complete manifest.

## Response classifications

The grader returns `correct`, `incorrect`, `old_answer_match`,
`truncated_no_answer`, or `invalid_output`. Coding stale matching means that code
fails updated tests but passes original tests. A returned truncation is
unsuccessful even if it contains a plausible answer. Provider failures, protocol
failures, budget stops, and unassigned calls are scheduler/availability states,
not semantic grading outcomes. All returned valid grades except `correct` count
as zero operational accuracy. Missing or invalid manipulation does not become
an incorrect mathematical or coding response.

## Frozen statistical analysis

Each problem has exactly one initial response and two independent responses in
each continuation condition. Eligibility depends only on the original grader
passing that single initial response. No retained, dropped, fresh, or unchanged
outcome selects cases. Every eligible problem contributes its dropped mean
minus retained mean, in half-unit increments. The mean of those problem-level
differences is the primary effect; individual repeated responses are never
treated as independent experimental units. All 24 assigned cases are reported
as a secondary population.

The one-sided paired sign-flip test uses an exact dynamic-programming count of
all `2^n` problem-level sign assignments, includes ties in the upper tail, and
keeps both repeats together. It assumes independent problem units and, under the
null, exchangeable retained/dropped labels within each problem. Interleaving
mitigates order effects but does not establish exchangeability or a mechanism.
Zero differences retain their sign multiplicity. There is no Monte Carlo error
in the p-value. A fixed-seed (`20261024`) 10,000-replicate percentile bootstrap
resamples whole problems for a descriptive 95% interval. With a small selected
sample, this is exploratory uncertainty, not a generalization guarantee.

The continuation gate requires at least 18 initially correct problems; fresh
updated accuracy at least 0.75 on that population; dropped-minus-retained mean
at least 0.10; one-sided p at most 0.10; qualified source data; the exact frozen
24-problem/200-response design; and every required outcome returned with valid
manipulation. Passing justifies a confirmation attempt on **new held-out cases**.
It is not publication evidence. Fewer than 18 eligible cases, an incomplete
campaign, or a failed qualification/manipulation gate yields `inconclusive`.

The eight preselected unchanged controls are reported descriptively, including
the update-minus-unchanged gap computed within the same control problems. Both
all-preselected and initially-correct control summaries are supplied. Eight
controls cannot establish absence of a general retention effect.

When a fixed population lacks any required paired outcome, its paired effect,
p-value, and interval are null rather than silently restricting to complete
cases. Per-problem observations and separate availability counts remain visible.
Returned truncations/invalid output still count as unsuccessful operational
responses; they must not be labeled semantic stale-reasoning errors.
