<!-- hook: gate-steps-resolve -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-grep
# Every single-line lefthook.yml run command resolves its first executable token and is never a bare no-op (:/true) — a retired step is deleted outright, never stubbed.

**Retired 2026-09-16 with the CI watcher itself:** this rule used to check two
surfaces, lefthook.yml's single-line `run:` entries and `aii-ci-watcher.sh`'s
`run_in` steps. The author retired the watcher (the commit gate replaced it), so
the checker no longer looks for that file, and `_MIN_STEPS` was recalibrated
down from the two-surface floor of 20 to 2 — the watcher used to supply 19 of
the old 23-step count. Everything below dated 2026-08-28 or earlier describes
the two-surface design as it stood before that; left as written rather than
rewritten, per this repo's own precedent for measured historical readings.

Scope (2026-08-28 audit): the rule-frontmatter `command:`/`condition:`
first-token surface is CEDED to pending
general/rule-engine/rule-frontmatter-values-parse-alike — the rule shaped for
it — exactly as two of this rule's own filter verdicts below argue. This rule
kept the lefthook.yml and ci-watcher halves at the time; the checker no longer
scans rule frontmatter, or (since 2026-09-16) the watcher.

Coverage (2026-08-28): lefthook.yml holds 7 `run:` keys. The checker's regex
(`^\s+run:\s*(?!\|)`) scans the 4 single-line ones — :56, :92, :112, :205 —
and the 3 `run: |` block scalars are OUT OF SCOPE: :70 gitleaks-push, and the
post-checkout/post-merge deps-stale-warn hooks at :155/:173, which are
documented warn-only and legitimately `exit 0`. A multi-line shell body has no
single first token the heuristic can judge — gitleaks-push opens with
`base=$(git rev-parse '@{upstream}' 2>/dev/null) \`, which the tokenizer would
misread as a bare `rev-parse`. That is the one place a stub could still be
introduced unseen; extending the no-op check to block bodies is the obvious
next increment, and an owner call.

Commit 7f3db571f: the retired cred-manager step left `timeout :` behind in the
ci-watcher's python job group and failed EVERY CI run with rc=127 until
someone diagnosed it — the incident was memorialized as a comment in
scripts/local/watchers/aii-ci-watcher.sh (the 'a placeholder step here once
ran `timeout :`' block) until that file was itself retired on 2026-09-16; the
memorial now lives only in the commit itself. The surfaces were enumerable and
unchecked: ~20 run_in steps at aii-ci-watcher.sh:264-366 (before the watcher's
retirement) and the lefthook.yml single-line run: entries (:56-205). The
louder failure mode self-announces; the silent sibling — a stub that resolves
to `:` or `true` and PASSES forever — is what this gate exists for.
rule-lefthook-validate (schema only; `run: "timeout :"` is schema-valid) and
rule-rules-md-current's test_every_condition_pathspec_matches_something.py
(pathspec liveness in rule conditions, not executable resolution across all
gates — it inherited that obligation when rule-group-condition-paths-live was
withdrawn on 2026-09-07) don't see it either. (The third once-distinct rule,
rule-ci-watcher-honesty, retired along with the watcher itself.)

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: incident-derived)

Proposed command (implemented at approval):

    scripts/check_gate_steps_executable.py  # superseded wording; parse lefthook.yml runs + aii-ci-watcher.sh run_in lines + rule frontmatter; strip VAR=val prefixes; command -v / path-exists the first token; fail on :/true steps


## IMPLEMENTED 2026-08-26 — `scripts/check_gate_steps_executable.py`

    .venv/bin/python $RULE_DIR/scripts/check_gate_steps_executable.py

Arrived green over **23 steps** at the time: the 4 single-line `run:` entries
in `lefthook.yml` (of its 7 `run:` keys — the 3 block scalars are out of
scope, see Coverage above) and 19 `run_in` steps in the CI watcher, measured
2026-08-28. (The ~260 rule-frontmatter one-liners it previously scanned are
ceded — see the scope note above.) The CI-watcher half retired with the
watcher on 2026-09-16 — see the note at the top of this file; the surviving
lefthook.yml-only surface measures 3 steps today, and `_MIN_STEPS` was
recalibrated down with it.

**The loud failure is not the one worth gating.** A step naming a missing
command announces itself next run. Its silent sibling — a step resolving to `:`
or `true` — passes forever and checks nothing. No existing gate sees it:
`rule-lefthook-validate` is schema-only and `run: "timeout :"` is schema-valid.
(`rule-ci-watcher-honesty`, which used to compare the watcher against
`ci.yml`, retired along with the watcher.)

**Resolution is deliberately generous, because a false alarm costs more than a
missed stub — and the first version produced two.** Both were mine, both against
working steps, and both are now handled:

| false alarm | cause |
|---|---|
| `node_modules/.bin/vitest` | its job sets `root: aii_frontend/` |
| `rule-bun-lock-fe` leads with `\|\|` | after an assignment |

So a token passes if it is a shell builtin, an assignment, an operator, a PATH
executable, or a path that exists relative to the step's own root. The engine's
`scripts/` goes on PATH first, the way the runner does it, so resolution
happens in the environment the steps actually run in.

Probed seven ways: the incident's own `timeout :`, a bare `true`, and an
unresolvable binary all fire; resolvable steps, a `root:`-relative path, an
assignment followed by `||`, and `timeout N cmd` do not.

**A no-op could wear a pair of quotes and walk through — fixed 2026-09-14.**
The bodies come from a line-oriented read, never a YAML parse, so `run: ":"`
reached the checker as the three characters `":"`. `_lead_token` handed that to
`_resolves`, whose generous branch passes any token starting with a quote, and
the step scanned clean. Measured against the live consumer before the fix, all
of `run: ":"`, `run: 'true'`, `run: "timeout :"` and `run: ""` were reported as
valid steps: two characters were the whole cost of disabling a gate command
forever, in the one gate whose reason for existing is the silent stub. The
no-op check now reads the body with a single wrapping pair of quotes removed
(a body wrapped whole, so `"a" && "b"` is left alone), and an empty body is the
same finding — the pattern is `^\s+run:\s*(?![|>])(.*)$`, which collects a
`run:` key carrying no value at all instead of letting the line match nothing
and the step vanish from the scan. Generosity stays where a false alarm names a
working step, on the RESOLUTION side; it never belonged on this side.
`test_gate_steps_resolve_bites.py` holds the eight spellings, the valueless
key, and two controls: a `run: |` block is still out of scope, and a quoted
real command still passes. Re-measured the same day, the consumer scans **35**
steps (2 single-line `run:` keys in its root `lefthook.yml`, 33 `run_in` steps
in the CI watcher) with zero findings, unchanged by the fix — the counts
earlier in this file are the 2026-08-28 reading and are left as written.

Delete-check: The incident's own fix WAS deletion — 7f3db571f removed the stub outright and
left a comment. This rule enforces that deleted end-state as the invariant:
retirement means removal, and whatever remains must resolve and do work.

Filter verdicts (3-lens adversarial, kept 2/3):
- KILL: 'Gate tooling is live, not decorative' is rule-lint-gates-actually-
bite's enforced dimension; first-token-resolves and no-bare-noop (the 'timeout
:' rc=127 incident) are new assertions for that rule's group across
lefthook/ci-watcher/frontmatter surfaces. Extending the enforced liveness rule
beats a second gate-liveness rule beside it. [merge->rule-lint-gates-actually-
bite]
- KEEP: Pins tonight's 'timeout :' rc=127 every-CI-run incident; first-token
resolution plus a no-op-stub ban across lefthook/watcher/frontmatter is cheap
and catches a class nothing else does. Killed gate-scopes-live was pathspec
liveness — different mechanism (executability, not path matching). Cede the
frontmatter-token clause to frontmatter-values-parse-alike if both land, to
avoid double …
- KEEP: Pins the rc=127 'timeout :' incident with a resolvable-first-token
check across lefthook + ci-watcher; keep, but cede the rule-frontmatter
surface to frontmatter-values-parse-alike so first-token resolution isn't
implemented twice. Distinct from killed rule-gate-scopes-live (pathspec
liveness — different dimension and mechanism).

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**. A separate agent re-measured every factual
claim above against the live tree rather than trusting it.

What it found:
The incident is exact. `git log -1 7f3db571f` body: 'the retired cred-manager
step left `timeout :` behind (rc=127 on every run) and is now deleted
outright'. The memorial comment is live at scripts/local/watchers/aii-ci-
watcher.sh:318-321: 'cred-manager tests migrated into rule-cred-manager-
service ... no separate step anymore (a placeholder step here once ran
`timeout :` and failed every python

Corrected statement of fact:
Corrected statement: the `timeout :` incident is real and memorialized at aii-
ci-watcher.sh:318-321, and the executable surfaces are enumerable — 19 run_in
call sites at aii-ci-watcher.sh:264-366 and 264 command:/condition: one-liners
across 162 rule SKILL.md files. But lefthook.yml holds only 7 `run:` keys plus
one `scripts:` runner (it deliberately has no pre-commit section,
lefthook.yml:38-48), and two of those seven are the post-checkout/post-merge
deps-stale-warn hooks that are documented WARN-ONLY and always exit 0 — the
rule must exempt them or it will fail on intended behavior. As of now there is
no live no-op stub in any of the three surfaces (measured: zero matches in
each). The rule is preventive only.
