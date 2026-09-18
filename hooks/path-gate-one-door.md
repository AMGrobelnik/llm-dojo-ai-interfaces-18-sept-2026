<!-- hook: path-gate-one-door -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Untrusted path components in aii_server pass through the shared validation/containment helpers — zero inline '..'-membership checks or resolve().relative_to copies in handler code.

The doors are `_is_unsafe_path_segment` (dashboard/api/__init__.py),
`_safe_upload_filename` (dashboard/api/files/_staging.py) and
`contained_relative()` (dashboard/api/files/_shared.py); the abilities slug
gate (agent_abilities/api.py:163) is deliberately exempt, with the argument
at the site. The collapse happened at adoption (2026-08-25, below); the AST
check in the frontmatter pins the end-state, and the real tree reports 0
(re-run 2026-08-28, rc=0).

AUDIT NOTE (2026-08-28): the corpus audit reads this rule,
rule-user-paths-via-resolver and rule-run-dir-reserved-names-one-door as
three slices of one capability — server-side path construction: validation,
root-join, leaf-name — each spending prose deconflicting itself from the
other two, and proposes merging them into a single "server paths have one
door" rule with three clauses, of which only this one has a built mechanism.
That merge is an owner call at approval; recorded here so the overlap is
visible.

## History — the five hand-copies as found

The gate existed in five hand-copies. Canonical: _is_unsafe_path_segment
(dashboard/api/__init__.py:381-410) whose docstring warns 'A name that claimed
only the first caller invited a second copy for the second'. Extracted-for-
testability: _safe_upload_filename (dashboard/api/files/_staging.py:89-109)
whose docstring records the incident — removing BOTH inline lines passed the
whole server suite. Yet the extraction missed its twin: files/_run.py:549-550
still carried the inline 'not filename or ".." in filename or "/" in filename'
copy. Containment was inlined three times (files/_run.py:443, _run.py:619,
_staging.py:254), and agent_abilities/api.py:163 was a fourth ad-hoc variant
('/' in slug or '..' in slug or '\x00' in slug). Distinct from rule-server-
run-access-gate (behavior of the run-id gate) and pending rule-user-paths-via-
resolver (which ROOT gets joined) — this pins single-sourcing of the
validation/containment step itself, structurally, so a new file endpoint
cannot ship a sixth divergent copy the suite never holds.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: access-parity)

Command (BUILT — the mechanism exists and the frontmatter carries it):

    python3 $RULE_DIR/scripts/check_path_gate_one_door.py  # AST over aii_server: '..'-membership outside the two segment doors, and resolve().relative_to outside contained_relative

Condition: `git diff --cached --name-only -- 'aii_server/**/*.py' | grep -q .`

The condition matches the scan rather than naming the known sites. A narrow
condition on a cmd-check is not an optimisation — nothing else ever runs the
gate, so it is the whole of when the rule exists, and a sixth copy added in a
module the condition did not name would not fire it at all.

Delete-check: Yes — the rule IS the deletion: collapse the five inline copies into the
existing two helpers plus one shared contained_resolve() (files/_run.py
delete, delete_staged_file, and the abilities slug gate all call it), then the
check pins that zero inline copies remain. Approval implies doing the
collapse; the rule enforces the collapsed end-state.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Five hand-copies of the containment gate, and the canonical helper's
docstring predicts exactly this drift. One-door collapse is the accepted house
shape; enforced rule-server-staging-uploads gates one call path, not the
helper-vs-inline-copy dimension. The rule IS the deletion (collapse to two
helpers + one contained_resolve).
- KEEP: Five hand-copies of the containment gate, with the canonical helper's
own docstring predicting the copy-drift; access-control parity via one-door
collapse, then a trivial ban on inline '..' checks.
- KEEP: Five verified hand-copies with the canonical helper's own docstring
predicting the drift; grep for inline '..'-membership and
resolve().relative_to outside the helpers is the proven one-door mechanism.
Behavioral siblings (#100) don't cover implementation single-door.

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**. A separate agent re-measured every factual
claim above against the live tree rather than trusting it.

What it found:
Every copy exists; both docstring quotes are verbatim; the line numbers drift.
Canonical _is_unsafe_path_segment is at
aii_server/dashboard/api/__init__.py:382-411 (claimed 381-410), and its
docstring ends exactly "A name that claimed only the first caller invited a
second copy for the second." Extraction _safe_upload_filename is at
files/_staging.py:89-110 (claimed 89-109), docstring verbatim inc

Corrected statement of fact:
Repoint every citation: __init__.py:382-411, _staging.py:89-110, the inline
filename copy at _run.py:558 (not 549-550), containment at _run.py:451 and
_run.py:627 (not 443/619), _staging.py:254 unchanged, and the fourth variant
at aii_server/agent_abilities/api.py:163 — a separate Django app, not under
dashboard/. Two substantive qualifications the body should absorb. (1) The
strongest evidence for the rule is one the proposal missed: _staging.py's
extracted gate is pinned by test_staging_id_validation.py:113/128/134 while
its byte-identical _run.py:558 copy has zero test coverage — exactly the state
the _staging docstring says caused the original incident, reproduced one file
over. That is the live defect, and deduping it (import _safe_upload_filename,
or hoist it beside the two callers) is a small change the existing server
suite covers. (2) agent_abilities/api.py:163 should be described as a related-
but-separate item, not a sixth copy to fold in: it carries its own "Defense-
in-depth: reject path traversal attempts even though the slug is composed from
the cwd by the SDK convention" comment, it guards an SDK-derived slug rather
than a client path, it lives in a different app, and its check is strictly
WEAKER than _is_unsafe_path_segment (no lone-`.` rejection, no 255-byte
NAME_MAX bound). Routing it through the canonical gate is a behavior change,
not a pure dedup — hence moderate for the _run.py:558 fix, risky if the rule
is written to force the agent_abilities consolidation too.

ADOPTION (2026-08-25): collapsed and gated. Both qualifications the verification
raised were followed rather than argued with.

Re-measured first, and one finding had already closed: the inline filename copy
at `_run.py:558` is **gone**, and `_run.py` now imports `_safe_upload_filename`
from `_staging`. The only two `".."`-membership checks left in the package sit
inside the two canonical helpers. That half needed no work.

What remained was containment, still inlined three times — and the copies had
NOT stayed identical, which is the rule's argument arriving on schedule:

| site | ValueError | OSError |
|---|---|---|
| `_run.py` read | denied | no_file |
| `_staging.py` delete | denied | no_file |
| `_run.py` delete | denied | **absent** |

Two caught `OSError` and each carried a comment explaining why — a component
past `NAME_MAX` cannot name a real artifact, so it is a 404. The third let
`ENAMETOOLONG` surface as a 500. Same operation, same package, one arm missing,
and nothing compared them: copies do not drift together, one drifts, and the
tests covering the other two stay green. Fixing the divergence and removing the
duplication are the same edit.

`contained_relative()` now lives in `files/_shared.py` — the module both routers
already import from — and returns `("ok", rel) | ("denied", None) | ("no_file",
None)`. All three sites call it. The delete path gains the missing arm, which is
a deliberate behaviour change: an over-long component there now answers 404 like
its siblings instead of 500. Verified by running the three test groups that
cover these endpoints: **129 passed**. `ruff` and `ty` clean.

The abilities slug gate is exempted, as the verification asked, with the
argument at the site rather than in a list here: it guards an SDK-composed slug
rather than a client path, and it lives in a different Django app.

One correction to that verification while adopting it. It called the abilities
check "strictly WEAKER than `_is_unsafe_path_segment` (no lone-`.` rejection,
no 255-byte NAME_MAX bound)". Both of those are real — confirmed at
`__init__.py:423-451` — but the relation is not one-directional: the abilities
gate rejects `\x00` and the canonical one does not. Neither is a superset, so a
swap would tighten and loosen the same endpoint at once. That makes the case for
leaving it alone STRONGER than "weaker, so fold it in later" suggests, and it is
why the exemption is argued rather than deferred.

`runpod_provision.py:144` needed no exclusion at all. It is
`item.relative_to(config_dir)`, building a tar member name with no `.resolve()`
and no containment claim, and the check matches containment as a call on the
result of a `resolve()` call. The proposed grep would have had to name it; the
AST shape simply does not see it.

Proven to bite in a throwaway tree: an inline segment check and an inline
containment check in the same handler are both named, while the two doors, an
exempt site and the tar-arcname `relative_to` stay silent. Real tree: 0.
