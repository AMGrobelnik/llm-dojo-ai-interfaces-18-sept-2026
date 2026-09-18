<!-- hook: pipeline-error-emits-first -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Every `raise PipelineError` is immediately preceded by emit.status_public_error carrying the same message

The convention is documented in run_pipeline's docstring (pipeline.py:209-210,
'Failure paths emit status_public_error then raise PipelineError') and its
callers rely on it — a normal return is the only success signal, and the
dashboard's error surface reads the emitted line. 6 of 7 raises comply
(_pipeline/_prep.py:195-196, 199-200, 208-209, 233-234; pipeline.py:170-171;
hypo_loop.py:169-170; re-measured 2026-08-28); the outlier is
pipeline.py:347-348 (the output_base guard raises bare), so that
failure reaches DBOS with no user-visible error event. AST check: a Raise of
PipelineError must be lexically preceded in its block by an
emit.status_public_error call bound to the same message expression.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: python-pipeline)

Command (checker implemented 2026-08-28):

    python3 $RULE_DIR/scripts/check_error_emit_pairing.py $(git ls-files 'aii_pipeline/src/*.py' | grep -v tests)

AST-walked over every block (body/orelse/finalbody/handlers): the statement
before a `raise PipelineError(...)` must be an `emit.status_public_error(...)`
call, and when both carry a plain name or string literal as their message
the two must agree — literal messages count, as the verification asked.
Measured on implementation: 7 raises, 6 paired, and the one bare raise is
exactly `pipeline.py:348`. **That finding is red BY DESIGN**: the triage above
records why it stays unfixed (a `@DBOS.workflow` body edit re-hashes the app
version and strands in-flight runs across a redeploy), so the pending-mechanism
guard enumerates this rule under `_EXPECTED_FAILING` with that reason, and the
day it is fixed the guard flips to "unexpected pass" and the entry comes out.

Proposed condition: `[ "$RULES_MODE" = all ] || git diff --cached --name-only -- aii_pipeline | grep -q .`

Delete-check: Yes — the paired-call dimension deletes cleanly by making PipelineError's
constructor (or a `fail(msg)` helper) do the emit itself, collapsing 7 two-
line sites to one line each; the rule should enforce that end-state and ban
the manual pair once the helper exists.

Filter verdicts (3-lens adversarial, kept 2/3):
- KILL: Better served by deleting the paired-call dimension now: make
PipelineError's constructor (or a fail(msg) helper) do the emit, collapsing
all 7 two-line sites — the invariant then holds by construction and no rule is
needed.
- KEEP: Do the delete-check first (constructor/fail() helper does the emit),
then the rule is a trivial grep for bare raise PipelineError. One live silent-
error site today; the dashboard error surface depends on the pairing. Cheap
post-collapse.
- KEEP: Prefer its own delete-check: make the constructor/fail() emit, then
grep bans bare `raise PipelineError` not routed through it. Adjacency-AST also
implementable as fallback. Loud either way; one live violation to fix at
adoption.

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**.
A separate agent re-ran every measurement above against the live tree.

What it found:
`grep -rn 'raise PipelineError' --include=*.py .` returned exactly 7 non-test
sites, matching the census. I read each: _prep.py 195/196, 199/200, 208/209,
233/234 all have `emit.status_public_error(...)` on the line immediately
before the raise; pipeline.py 170/171 and hypo_loop.py 169/170 likewise.
pipeline.py:347-348 is `if not wf_input.output_base:` / `raise
PipelineError("run_pipeline_workflow requires output_base")` with no emit and
no comment — the bare outlier is confirmed.

Corrected statement of fact:
6-of-7 compliance and the bare raise at pipeline.py:347-348 are both correct.
The framing 'violates the convention documented at pipeline.py:210-213' is
not: that docstring governs run_pipeline, a different function. The outlier is
a defensive precondition on a handoff blob the server always populates, not a
user-facing failure path, and any rule needs to accept a literal message (not
only a `msg`-bound one). Fixing it edits a @DBOS.workflow body, which changes
the DBOS app-version hash — aii_server/dashboard/services/safety_net.py:448-453
documents that as stranding in-flight workflows across a redeploy — hence
moderate rather than trivial.

TRIAGED 2026-08-24 — deliberately NOT fixed, and this is the reason. The
app-version claim was re-read at source and holds:
aii_server/dashboard/services/safety_net.py:448-453 (re-verified 2026-08-28)
says the hash "covers only registered ``@DBOS.workflow`` sources, so edits here
don't re-hash the app version and strand in-flight safety nets across a
redeploy". It is written as the justification for keeping a neighbouring
helper OUT of a workflow body, which makes it a deliberate design constraint
rather than an incidental note.

There IS a recovery path — `recover_pending_safety_nets` retags rows left
pending across a deploy that did touch a workflow body — so this is a cost,
not a cliff. But the outlier being fixed is a defensive precondition on a
handoff blob the server always populates: not reachable by users, no
user-facing failure path. Paying an in-flight-workflow disruption to add an
emit to an unreachable branch is the wrong trade, and it is the owner's call
whether to bundle it into a redeploy that is already re-hashing anyway.

The right moment is the next deploy that edits a workflow body for other
reasons; the cost is then already sunk. Flagging it here so it can ride
along rather than being rediscovered.
