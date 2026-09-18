<!-- hook: owner-widening-explicit -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: RULES_REPO
# Owner-scope widening is always explicit and never the default

Owner-scope widening is always explicit and never the default: no parameter
whose effect is "drop the owner predicate" carries a wide default value, and
the widening decision is spelled one way and taken once, from is_staff, at
the API boundary.

MEASURED. `git grep -nE "(any_owner|see_all_users)\s*:\s*bool\s*=\s*False" --
'aii_server/**/*.py' 'aii_lib/**/*.py' | wc -l` -> `7`, spanning TWO packages:
aii_lib/src/aii_lib/run/runpod_orch_pods.py:201,
aii_server/dashboard/api/runs_list_poll.py:144, services/run_jobs.py:119,
services/run_start_failures.py:115, services/runs_sidebar.py:418, :482, :553.
A THIRD spelling of the same decision exists: run_cost.py:468
`_owned_statuses(run_ids, username)` and :586 `resolve_run_costs(run_ids,
*, username: str | None)` where `username=None` means any owner, and
runs_sidebar.py:647 `user=None if see_all_users else username`. THE LIVE
ASYMMETRY: those seven all default NARROW, but `git grep -n
"reap_stale_zombie_runs("` -> 3 sites, and zombie_reaper.py:207 (re-pointed 2026-08-28; was :203) is `def
reap_stale_zombie_runs(username: str | None = None)` — the ONE lever with a
WIDE default, and the only one attached to a MUTATION (it calls
`cancel_descendant_workflows` on each candidate). Its own docstring: "``None``
sweeps every user (server startup)". The request-path caller
runs_helpers.py:83 passes `request.user.username` correctly and apps.py:252 /
zombie_reaper.py:350 omit it deliberately — so the invariant holds today
purely by every caller remembering, on a code path that cancels other
accounts' live runs. Widening origin, AST-measured (`ast.walk` for
`Attribute(attr='is_staff')` over aii_server, migrations/tests excluded): 6
READ sites — api/__init__.py:275,585,638 and runs_list_poll.py:133,140,410 —
plus one `getattr` read in auth_adapters.py:153; each independently re-decides
what staff widening means. runs_list_poll.py:130 asserts "This is the only
place the fleet-wide listing is turned on" while :140 turns on the same
listing's provisioning overlay four lines below.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: tenant-data-scoping)

Proposed command (implemented at approval):

    python $RULE_DIR/scripts/owner_widening_explicit.py  # AST over aii_server + aii_lib: (a) no parameter in the widening vocabulary (any_owner / see_all_users / a username|user parameter that is optional in an owner-filtered query) has a wide default — bool defaults must be False, str|None must be keyword-only with NO default; (b) the wide value is passed only from the pinned boundary module; post-collapse the check degenerates to `rules-grep --tree '(any_owner|see_all_users)'` returning nothing

Proposed condition: `none — AST scan over aii_server + aii_lib, sub-second`

Delete-check: Yes, and the rule should enforce the collapsed end-state. Three spellings
express one decision; collapse them to a single `owner: str | None` threaded
down (None == fleet-wide), resolved ONCE at the API boundary from is_staff —
that deletes six boolean parameters, the any_owner/see_all_users vocabulary,
and the second convention in run_cost, leaving one value whose wide form is
visibly None at every call site. Separately and immediately: make
reap_stale_zombie_runs take a keyword-only `username` with no default so the
two boot callers pass `username=None` explicitly. After both, the rule is a
grep for a vocabulary that no longer exists.

INDEPENDENT VERIFICATION (in-pipeline, 2026-08-24) — verdict: **partly-wrong**.
A different agent re-ran every measurement before this reached the owner.

What it found:
`git grep -nE "(any_owner|see_all_users)\s*:\s*bool\s*=\s*False" --
'aii_server/**/*.py' 'aii_lib/**/*.py'` -> exactly 7 lines at the stated
locations (runpod_orch_pods.py:201, runs_list_poll.py:144, run_jobs.py:119,
run_start_failures.py:115, runs_sidebar.py:418/482/553). Third spelling
confirmed: run_cost.py:351 `def _owned_statuses(run_ids: list[str], username:
str | None)` and :469-470 `def resolve_run_costs(run_ids: list[str], *,
username: str | None)` with docstring ":469-474 ``username=None`` widens to
any owner"; runs_sidebar.py:647 `user=None if see_all_users else username`.
Wide-default lever confirmed: `git grep -n "reap_stale_zombie_runs(" --
':!*.claude*'` -> 4 lines = 3 call sites (runs_helpers.py:83 passes
`request.user.username`, apps.py:252 and zombie_reaper.py:346 omit it) plus
the def at zombie_reaper.py:203 `def reap_stale_zombie_runs(username: str |
None = None) -> int:`, docstring "``None`` sweeps every user (server
startup)"; it reaches `cancel_descendant_workflows` at zombie_reaper.py:229. I
searched for other wide owner defaults: `git grep -nE
"(username|user)\s*:\s*str \| None\s*=\s*None" -- 'aii_server/**/*.py'
'aii_lib/**/*.py' ':!*/tests/*'` -> 2 hits, the reaper and
runpod_orch_pods.py:158 `set_pod_id(*, run_id, pod_id, username: str | None =
None)` — the latter stamps a value rather than dropping a predicate, so "the
ONE lever" survives. is_staff AST scan reproduced with my own script (ast.walk
over aii_server, migrations/tests excluded): 8 Attribute/getattr sites —
api/__init__.py:249,555,608; runs_list_poll.py:133,140,414;
auth_adapters.py:153 (getattr); plus aii_server/aii_server.py:163, which is a
Store-context WRITE (`user.is_staff = False`), so the proposal's "6 READ sites
+ 1 getattr" is right. Dedupe: no owner-scope/widening rule among the 383;
nearest are rule-server-api-auth-surface (route auth), rule-server-share-read-
only (share semantics), rule-pod-env-payload-least-scope (env keys) — all
different dimensions.

Corrected statement of fact:
One sub-claim is overstated and lands in the known "a comment declares it
deliberate" failure mode. The proposal reads runs_list_poll.py:130 ("This is
the only place the fleet-wide listing is turned on") as contradicted by :140.
Re-read in full, :129-132 scopes that sentence to `list_runs_for_user(...,
see_all_users=...)` at :133, and the immediately preceding comment at :136-139
documents the second site on purpose: "Provisioning runs widen with the
listing. A booting run is invisible to the journal query BY DEFINITION ... so
leaving it caller-scoped would blind the fleet view." So it is not a comment
falsified four lines later; it is two deliberately-coupled widenings. The
real, unrhetorical evidence for the rule is that the same is_staff decision is
independently re-spelled at :133, :140 and :414 (`username = None if
request.user.is_staff else request.user.username`) in one module, plus a
fourth spelling in run_cost.py. Everything else measured true.

RE-MEASURED 2026-08-28 while finishing the corpus audit: the reaper def now
sits at zombie_reaper.py:207, its cancel_descendant_workflows import at :233
and boot caller at :350; run_cost.py's pair moved to :468 (`_owned_statuses`)
and :586 (`resolve_run_costs`); the is_staff reads sit at
api/__init__.py:275/:585/:638 and runs_list_poll.py:133/:140/:410;
runs_helpers.py:83 and apps.py:252 are unchanged. The opening paragraph is
repointed to these current lines; only the dated verification block above
keeps the pre-drift numbers it measured (:203/:229/:346, :351/:469-470,
:249,:555,:608, :414). All 7 any_owner/see_all_users sites still default
narrow, and the wide default on reap_stale_zombie_runs is still live. The keyword-only fix the Delete-check
names remains outstanding, as does `scripts/owner_widening_explicit.py`
(proposed, implemented at approval — nothing exists to run yet).

Filter verdicts (3-lens adversarial, kept 2/3):
- KEEP: Data-scoping default-narrowness is a distinct mechanism from rule-
server-run-access-gate (gate is called) and rule-endpoint-admission-parity
(gate exists): it pins that no drop-the-owner-predicate parameter can acquire
a wide default. Cheap grep over 7 confirmed sites, severe failure mode.
- KEEP: The enforceable half is a ban-grep on any owner-widening parameter
defaulting wide, over seven located sites — deterministic and probe-testable.
rule-server-run-access-gate and rule-endpoint-admission-parity govern route
gating, not the default value of the predicate-drop knob.
- KILL: Verification found all 7 `any_owner: bool = False` sites already
defaulting narrow — the rule guards a hypothetical. Delete-check agrees the
deliverable is the collapse: three spellings expressing one decision become a
single `owner:` param, after which a wide default is unrepresentable. Dedupe
pressure from ENFORCED rule-server-run-access-gate and …

## Mechanism (built 2026-09-03)

`scripts/owner_widening_explicit.py` — AST over the tracked `*.py` that
`git ls-files -- 'aii_server/*.py' 'aii_lib/src/*.py'` returns, with any path
carrying a `tests/` or `migrations/` segment dropped (313 files today). Two
checks over one vocabulary, plus a floor:

- **(a)** — subject: a param named `any_owner` / `see_all_users`;
  verdict: no default, or `False`
- **(b)** — subject: `username` / `user` annotated optional-str;
  verdict: NO default at all
- **floor** — subject: zero (a)-sites found; verdict: exit 2, never 0

(a) is the boolean spelling of "drop the owner predicate" and (b) is the value
spelling, where the wide value is `None`. Optional-str is recognised as
`str | None`, `None | str` or `Optional[str]`, whitespace-normalised and with a
stringised annotation unwrapped, so `from __future__ import annotations` does
not hide a site. Parameters are read off the full signature — positional-only,
positional, and keyword-only with `kw_defaults` — so making a parameter
keyword-only does not smuggle a default past the scan, and functions are walked
with their owning class, so a method reports as `Class.method`.

(a) has NO allowlist by design: `False` is always writable, so an exemption
would only ever be a wide default someone argued for. (b) has
`allowlist.txt` in the rule directory, `<repo-relative path>::<function>`
with the reason after `#`, and entries must be LIVE — an entry whose function
no longer carries such a defaulted parameter is itself reported at its own
allowlist line, so an exemption cannot outlive the code it was written for.
One entry exists: `runpod_orch_pods.py::set_pod_id`, on the ground the 2026-08-24
verification already established — its `None` stamps a value rather than
dropping a predicate, and the upsert coalesces on `username`, so passing `None`
leaves whatever owner was already recorded instead of widening a query.

The floor is the vacuous-pass guard. A `git ls-files` that returns nothing and a
tree with no wide defaults print the same thing, so finding zero `any_owner` /
`see_all_users` parameters exits 2 rather than 0 — as does a git that refuses to
list files, or a source file that will not parse. Only 0 and 1 say anything
about the tree. `GIT_*` is scrubbed from the `git ls-files` child, because
lefthook exports `GIT_DIR` / `GIT_INDEX_FILE` into hook children and a git that
inherits them reads THIS repo whatever `-C` says, which would make `--root`
silently mean something else.

Stock fix, landed as `2b9d319bc` (2026-08-28) before this checker was built:
`reap_stale_zombie_runs` is now `def reap_stale_zombie_runs(*, username: str |
None) -> int:` at zombie_reaper.py:207 — keyword-only, no default — with the
docstring keeping the line that `username=None` sweeps every user and adding
why the default is gone. All three callers spell their scope:
`runs_helpers.py:83` passes `username=request.user.username` as a keyword,
`dashboard/apps.py:252` and the periodic sweep at `zombie_reaper.py:354` pass
`username=None`. So the Delete-check's "separately and immediately" half is
done; the collapse of the three spellings into one `owner:` threaded from the
API boundary is not, and remains the owner call. Note the gap that leaves: the
statement's second clause — "spelled one way and taken once, from is_staff, at
the API boundary" — is NOT what this checker measures. It enforces the
first clause only. The is_staff re-spelling at runs_list_poll.py:133/:140/:410
plus run_cost.py's fourth spelling are untouched by it.

Probe results (each exit driven for real, 2026-09-03):

- **this repo, allowlist as committed** — exit: **0**
- **this repo, empty allowlist** — exit: 1 — `set_pod_id` only
- **planted `def f(username: str \** — exit: None = None)`
- **planted `any_owner: bool = True`** — exit: 1 — `defaults wide
  (True)`
- **allowlist entry naming a gone function** — exit: 1 — `stale
  allowlist entry`
- **tracked tree with no widening vocabulary** — exit: 2
- **`--root` at a non-repo** — exit: 2

`test_an_owner_widening_parameter_cannot_default_wide.py` beside this file
carries seven behaviour tests against the real checker: rows 1 and 3-6 of that
table, a live allowlist entry passing (0) so the stale test above it proves
something, and an AST pin that the reaper's `username` stays keyword-only and
undefaulted. Each probe tree is a real `git init` + `git add` scratch repo, so
discovery runs the same way it runs for real rather than through a second code
path. Rows 2 and 7 were driven by hand, not pinned. 7 passed.
