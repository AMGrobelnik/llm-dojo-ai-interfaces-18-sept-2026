<!-- hook: rotate-helper-uniform -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# The `_rotate_if_large` helper's rotation mechanism is byte-identical across its four carrier scripts (only the final notice line may differ)

Four hand-synced copies whose comments each claim 'Same helper, same
32MB/3-generation policy' (aii-image-watcher.sh:42, aii-ci-watcher.sh:60, aii-
builder-keepalive.sh:53, run_server.sh): measured md5s show three variants,
differing today only in the last notice line — deliberate per context (log()
vs direct append vs [boot] prefix). The mv-generation shuffle above that line
is subtle (an off-by-one in the keep chain silently drops a generation) and a
fix to one copy will not propagate: exactly defect class #1. The existing
test_watcher_logs_are_bounded pins policy numbers and call PLACEMENT but never
compares the function bodies, and does not cover run_server.sh's copy at all
(its own docstring notes the volume-log test 'is written against one file').

Proposed type: **cmd-check** · scope: **whole-tree** · value: **low** (proposer: shell-watchers)

Command (checker implemented 2026-08-28):

    bash $RULE_DIR/scripts/check_rotate_uniform.sh

Carriers are enumerated through git (`git grep -l '^_rotate_if_large()'`),
not listed: the proposal counted four and there were FIVE on implementation
day — `aii-site-watcher.sh` had joined. The notice line is dropped
positionally (the line before the closing brace), exactly as the verification
above recommends after its own pattern-matching attempt produced a false
drift. Measured: five carriers, one body; a `mv`→`cp` mutation in one copy is
reported with the diff. FOUR since 2026-09-05, when `aii-site-watcher.sh` was
deleted (publishing the rules page moved into `aii-ci-watcher.sh`) — the
checker now prints `4 carriers, one helper body`, which is the count the
statement above has always named.

    bash $RULE_DIR/scripts/check_rotate_uniform.sh  # awk-extract the function from each carrier, drop the final notice line, diff every copy against the first

Delete-check: Collapsing to one sourced file is infeasible cheaply: the copies run in three
unrelated contexts (standalone from ~/.local/bin, from cron before any repo
cd, baked into the server image), so a shared source would need its own
install/sync machinery — more moving parts than the 17 lines it removes. Pin
identity of the mechanism instead.

Filter verdicts (3-lens adversarial, kept 2/3):
- KEEP: Four hand-synced copies whose comments claim identity; collapse is
infeasible across their three execution contexts, so md5-modulo-last-line
parity is the honest cheap pin against silent policy drift.
- KILL: Low-severity defect class (worst case: a log rotates differently) and
the check needs brittle normalization of the allowed last-line variation
across three execution contexts. Cost/value inverts here; the in-file comments
carry the convention adequately.
- KEEP: awk-extract the _rotate_if_large body from each of the four scripts,
strip the final notice line, compare digests. Extraction is uniform (function-
to-brace), normalization rule is pinned. Implementable; drift fails loudly.

INDEPENDENT VERIFICATION (2026-08-24) — verdict: **every load-bearing claim
is exact.** Two comment line references had drifted and are corrected above.

Extracted the function from each carrier (`^_rotate_if_large()` to the first
line that is just `}`) and compared:

| claim | measured |
|---|---|
| four carrier scripts | 4 |
| three full-body variants | 3 |
| differ only in the notice line | yes |

All four bodies are **18 lines**, and the ONLY line that differs between any
pair is line 17:

    keepalive    echo "[$(date '+%F %T')] rotated …" >>"$_f"
    ci / image   log "rotated …"
    run_server   echo "[boot] rotated …"

`ci` and `image` are byte-identical to each other; the other two each differ
from them at that one line and nowhere else. So "three variants, differing
today only in the last notice line" is precisely right, and the mv-generation
shuffle the rule cares about is currently uniform across all four. The
delete-check's "the 17 lines it removes" also checks out — an 18-line body is
17 lines plus the closing brace.

**A caution for whoever builds the checker, learned by getting it wrong
here.** My first attempt normalized by digesting the body with notice-looking
lines filtered out, and reported TWO variants instead of one — a false drift
finding. The predicate was wrong (`"rotated" not in l or "echo" not in l and
"log(" not in l` mixes `and`/`or` precedence and removed the `echo` forms
while keeping the `log` form), so two scripts were normalized and two were
not. A plain line-by-line diff showed the truth immediately. Normalize by
dropping the LAST line of the body positionally, not by pattern-matching
what a notice looks like — the three notices share no common token.

**The coverage gap in `test_watcher_logs_are_bounded` is real, both halves.**
It enumerates `WATCHERS.glob("*.sh")` where `WATCHERS` is
`scripts/local/watchers`, so `scripts/runpod/run_server.sh` is outside it
entirely. And its `_DEFINE` regex only asserts the function is defined, and
defined before its call site — it never compares bodies. Worth noting it does
carry a population floor ("An empty glob would make every check below
vacuous"), so it is not itself at risk of passing on nothing.
