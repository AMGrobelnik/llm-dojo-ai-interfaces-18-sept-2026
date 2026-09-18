# Every multi-provider failover walk is bounded by one wall-clock budget: a monotonic deadline, each attempt clipped to what remains, and a minimum-attempt floor

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 1s | active |

## Why

A walk that gives each provider its own timeout has a worst case equal to the
SUM of those timeouts, not to any budget anyone declared. `free_web_search`
walked a chain of up to 6 providers at a fixed 10 s each — with `ddgs` alone
walking 3 backends at 10 s — then a paid leg at 10 s, all inside a caller that
gives the ability server 120 s. It fitted only by an accident nobody checked:
one more `chain.append` would have inverted it silently, the caller giving up
while the worker kept walking. `concept_fig_gen` carries the same defect
written down as fixed: "three attempts per model across two models, each
allowed DEFAULT_TIMEOUT (180 s), needs up to 1092 s, while the caller gives the
ability server 180 s in total … the caller saw a bare transport timeout rather
than 'the budget ran out'."

A deadline alone is not enough, which is why there are three markers: a
deadline stops a walk only BETWEEN providers, so a late entry that itself walks
three backends runs ~30 s past it. Each attempt has to be clipped to what
remains, and a doomed final try refused.

The rule that preceded this hook was the most-applied in its batch — 65
applications, 31 blocks — and its one recorded evidence line is an agent
running the rule's own enumerator and eyeballing 13 rows. It never found either
of the two live defects below.

## Mechanism

The rule rejected a command check on a measurement this hook accepts: a
detector keyed on "iterate pairs AND (a `timeout=` keyword OR a mention of
remaining/deadline)" found 1 of 3 carriers and 9 unrelated loops and — the
fatal part — "recognises a walk BY the remedy, so an unbounded walk is not
detected as a walk and passes".

That critique is about the CANDIDATE TEST, not about gating. So the candidate
test here contains none of the remedy. A loop is a walk when it is
structurally one, and only then are the markers demanded:

| step | signal | mechanism |
|---|---|---|
| S1 | iterates providers | the NAMES the iterable is built from |
| S2 | issues an attempt | http client, provider kwarg, unpacked fn |
| S3 | fails over | a failure path continues, success leaves |
| M1 | deadline | a monotonic or injected clock read |
| M2 | clip | `min(...)` narrowing to what remains |
| M3 | floor | remaining vs a MINIMUM, not vs zero |

S1 matches names rather than the unparsed expression, which is what keeps a
keyword argument out of the signal: `iter_events(wid, order='ts')` carries the
token "order" and names no provider collection — that one mistake produced 4 of
the first pass's 7 false positives. S2 excludes a CamelCase tail, so
`PickedEndpoint(base_url=…)` builds a value rather than dialling one. M3
rejects a comparison against literal `0`, because `remaining > 0` is a
positivity check and accepting it would pass a walk that still begins a doomed
10 s attempt with 0.2 s left.

The clip marker is deliberately delivery-agnostic, which answers the rule's
other objection — one carrier assigns into a dict, one passes positionally, one
passes a keyword, and no syntactic signature unites them. It does not have to:
the `min(timeout, remaining)` NARROWING is the same in all three, and the
delivery is never read.

An unbounded walk still satisfies S1-S3, so it is found and it fails. Two tests
are the proof: `UNBOUNDED` and `BOUNDED` are the same loop, differing only in
the remedy, and the checker must return 1 and 0.

Against the rule's own numbers: the rejected detector found 1 of 3 carriers in
10 candidates; the rule's shipped enumerator 3 of 3 in 13; this checker 4 of 4
in 6, and all 6 are genuine failover walks. Content is read from the index, and
a `for `+`continue` pre-filter skips parsing modules that cannot hold a walk.

## Stock

**2 findings**, measured against `/home/<user>/projects/research-monorepo` at HEAD
`3f1060fa7` (re-confirmed unchanged at `eaf82761c`) in 0.73 s whole-tree (0.03 s scoped to one file). Six candidate
walks, four carrying all three markers, two carrying none — and both of those
are real, in modules the rule's manual enumeration never reached.

`aii_lib/src/aii_lib/workflows/guided_questions.py:104` `_call_structured()`
walks `enumerate(chain)` into `requests.post(_OPENROUTER_URL, …,
timeout=timeout)` with `timeout: float = 25.0` and a `DEFAULT_QUESTION_CHAIN`
of **2 tiers**: 2 x 25 s = **50 s** worst case, and the module reads no clock
anywhere.

`aii_lib/src/aii_lib/workflows/summarize.py:608` `summarize()` walks
`enumerate(chain)` into `session.post(…, timeout=timeout)` with `timeout:
float = 3.0`, a `DEFAULT_FALLBACK_CHAIN` of **7 tiers** and an inner `for
attempt in range(2)`: 7 x 2 x 3 s = **42 s**. It is the sharper case because it
DOES own a budget — `free_deadline_s: float = 5.0` — but that bounds only the
free-router leg; the paid chain underneath it has no walk-level clock at all.

Both figures can double: `requests`' scalar `timeout` applies separately to
connect and to read.

The hook is file-scoped and passes `{staged_files}`, so this stock blocks only
a commit that touches one of those two modules. There is **no debt list**: a
debt entry for a live 50 s overrun would be the gate agreeing to its own
defect. The fix is the same ~6 lines `free_web_search` already carries.

## Fragility

| refactor | effect | guard |
|---|---|---|
| walks become `while` loops | not seen | "skipped: zero candidate" whole-tree |
| a walk moves into a library | not seen | "skipped: zero candidate" whole-tree |
| a provider noun is unlisted | that walk missed | the noun set |
| a marker satisfied by accident | reads as bounded | none |
| the marker becomes routine | silent waivers | greppable, 0 today |

The vacuity guard is what matters most for a structural detector, but zero
candidates is not automatically a broken selector: a consumer with no
multi-provider failover code (measured: notes-repo, 198 non-test `.py` files, zero
S1+S2+S3 matches anywhere in the tree) legitimately has nothing for this check
to guard. The whole-tree run prints "skipped: zero candidate failover walks"
and exits 0 rather than failing the commit — loud enough that a REAL
regression (the shape moved in a consumer that used to have candidates) is
still visible on stdout/the dispatcher's note line, just not blocking. An
empty python population (no `.py` files at all) is still `cannot run` (exit
2), since that means the check never got a chance to look. Per-file runs
cannot fire either signal, so the sweep has to run periodically or in CI.

The three markers are heuristic by nature — a `min(x, remaining)` present for
an unrelated reason marks the walk clipped. The candidate test is not
heuristic, and that is where the self-confirmation risk actually lived.

## Residue

`while`-loop and recursive walks: only `ast.For` is examined. Adding `while`
costs precision (a `while True` retry loop is not a walk) and no carrier uses
one today.

Walks delegated to a library — litellm `fallbacks`, tenacity, an SDK's own
retry chain. The budget then belongs to the library's configuration, which is a
different question.

Whether the budget is the RIGHT SIZE. This proves one budget bounds the walk;
it cannot prove that budget fits inside the caller's. That needs a call graph,
not a walk detector.

The judgment "is this really a failover walk?" is not dropped, it is inverted:
instead of an agent judging 13 rows every commit, the author of a
matching-but-exempt loop writes one `# walk-budget-exempt: <why>` line at the
site. At 6/6 precision the expected number of such lines is currently zero, and
the tree carries zero.
