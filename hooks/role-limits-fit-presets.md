<!-- hook: role-limits-fit-presets -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Every preset a role lists in allowed_presets fits that role's limits caps for each _INT_CAPS field — no role offers a preset its own caps would clamp

regular.yaml:34-41 states the invariant as hand-maintained parity ('Iteration
caps — mirror the "max" preset's values so regular users can apply Max on
terminal') and the numbers agree only by discipline today: max.yaml 7/10/7 ==
limits 7/10/7, lite 1/2/3 and pro 3/5/5 under, ultra 10/20/7 correctly
excluded from allowed_presets. The dotted-path-to-cap mapping already exists
as _INT_CAPS (run_config/_validation.py:146-151), so the check re-types
nothing. If max.yaml's iterations rise without regular.yaml tracking, regular
users see a preset the validator then clamps — a confusing apply-then-differ
experience rule-server-run-config-api's tests (which pin the allowed_presets
LIST, not numeric fit) would not catch.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: config-yaml)

Mechanism (implemented 2026-08-26, `scripts/check_role_limits_fit_presets.py`):

    .venv/bin/python $RULE_DIR/scripts/check_role_limits_fit_presets.py

Arrives green: 2 roles, 4 presets, 9 (preset, cap) pairs all within their
caps, with `max` sitting exactly on `regular`'s caps at 7/10/7 — the
hand-maintained parity this rule exists to hold.

The dotted-path-to-cap mapping is READ from `_INT_CAPS` rather than re-typed,
so the check cannot drift from the validator it protects, and a cap added
there is covered here for free.

**An omitted `allowed_presets` means EVERY preset, not none.**
`superuser.yaml` omits the key and says so in a comment. Reading omission as
an empty list makes the check vacuous on exactly the role that offers the
most — it would report clean while checking nothing. A first pass did read it
that way and reported `allowed=[]`. Today that role also has no caps, so it is
trivially fine, but a role omitting the list WITH caps would need every preset
to fit.

A preset silent about a cap is skipped rather than assumed zero: no preset
sets `max_file_size_mb`, and inventing a value would compare against something
never claimed.

Probed seven ways: a preset above its cap, a preset with no file, and an
omitted list where one preset is over all fire; within-cap, exactly-at-cap, an
explicitly empty list, and a role with no caps do not.

Superseded proposal:

    .venv/bin/python $RULE_DIR/scripts/check_role_limits_fit_presets.py  # for each roles/*.yaml with limits: for each allowed preset, resolve the _INT_CAPS dotted paths in presets/<name>.yaml and assert preset value <= cap

Delete-check: Deletion is the better end-state: derive each role's limits as max-over-
allowed-presets (the comment says the values ARE that today), removing the
numeric duplication; the rule then enforces that roles carry no hand-copied
numbers. Until that refactor, the fit check pins the parity the comment
promises.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Numbers agree today only by discipline and the comment admits the
values are hand-mirrored. Keep the parity check now; the derive-limits-from-
presets deletion is the better end-state but changes config semantics, an
owner call.
- KEEP: Numeric parity held only by a comment saying 'mirror the max preset';
a drifted cap silently clamps a preset a role claims to offer. Small yaml
cross-check now; prefer the derive-limits deletion later, which retires the
rule.
- KEEP: Load role + preset yamls, assert per-field caps >= each allowed
preset's values. Pure yaml arithmetic, deterministic, loud. Prefer the derive-
limits-from-presets deletion if the owner agrees, which shrinks the rule.

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**.
A separate agent re-ran every measurement above against the live tree.

What it found:
Read aii_config/roles/regular.yaml with line numbers: 34-37 is the comment
'Iteration caps — mirror the "max" preset's values so regular users can apply
Max on terminal (lower bound is 1) ... (Ultra's deeper 10/20 budget stays
superuser-only.)' and 38-42 is the `limits:` block — the proposal's 34-41 span
is essentially exact (it stops one line short of `file_size_mb: 100`). I
computed the fit directly from the yamls rather than reading the comments:
regular limits are {gen_hypo_loop_iterations:

Corrected statement of fact:
Numbers and the enforcement-gap claim all hold; two details are wrong.
`_INT_CAPS` is at _validation.py:147-152, off by one from the cited 146-151.
And the validator does not clamp — it rejects the save with 'must be between 1
and {cap}' (_validation.py:339-340), so if max.yaml's iterations rose above
regular.yaml's caps the user experience would be apply-then-error-on-save, not
apply-then-silently-differ. No live defect: max 7/10/7 equals the caps exactly
and ultra is correctly excluded from allowed_presets.
