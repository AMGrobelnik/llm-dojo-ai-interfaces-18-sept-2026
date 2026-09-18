<!-- hook: run-dir-reserved-names-one-door -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-grep
# run_dir's reserved layout names are minted only by their canonical owners: every other site imports WORKFLOW_INPUT_FILENAME or calls user_uploads_path_for_run instead of re-typing the literal

The full statement: `.workflow_input.json` appears in package source only as
`WORKFLOW_INPUT_FILENAME`
(aii_pipeline/src/aii_pipeline/_pipeline/_workflow_input.py:77, re-exported
via `aii_pipeline.pipeline`), and `user_uploads` only inside
`user_uploads_path_for_run` (aii_lib/src/aii_lib/run/fork_setup.py:104-119);
every other site imports the constant or calls the helper, so no re-typed
literal exists in aii_lib, aii_pipeline, aii_server, aii_launcher or
aii_runpod package source.

Why it matters: `files/_run.py` keeps `.workflow_input.json` out of the
share-readable surface by NAME, in two gates (the listing and the download).
A rename through the constant keeps both gates correct and leaves any
hand-typed site reading a file that no longer exists — `side_chat_runner`
would fall through its snapshot chain silently, exactly the access-control
parity split the constant exists to prevent. `user_uploads_path_for_run`'s
own docstring says it exists so a cross-fork policy change has one home.

## LANDED 2026-09-04

Whole-tree hit count under the command above is **0**, which is what earns
the `--tree`. Five re-typed literals were routed through their door:

- `aii_pipeline/.../_pipeline/_prep.py:87` `_stage_user_uploads`
  was `run_dir / "user_uploads"`,
  now `Path(user_uploads_path_for_run(run_dir))`.
  This is the site that CREATES the directory, so the door now owns
  both the read side (fork prompts) and the write side.
- `aii_server/.../api/files/_run.py:602` upload `_store`
  was `run_path / "user_uploads"`,
  now `Path(user_uploads_path_for_run(run_path))`.
- `aii_server/.../api/run_config/_snapshot.py:95`
  was `run_dir / ".workflow_input.json"`,
  now `run_dir / WORKFLOW_INPUT_FILENAME`.
- `aii_server/.../services/side_chat_runner.py:121` `first`
  was `run_dir / ".workflow_input.json"`,
  now `run_dir / WORKFLOW_INPUT_FILENAME`.
- `aii_server/.../services/side_chat_runner.py:127` `snap`
  was `base / current / ".workflow_input.json"`,
  now `base / current / WORKFLOW_INPUT_FILENAME`.

Both server imports are function-local, matching what `files/_run.py`
already does for the same constant at both of its gates; `_prep.py` takes
the helper at module scope, as `hypo_loop.py` and `invention_loop.py`
already do. `fork_setup` imports nothing heavy, so no cycle is added.

### Byte-identity was measured, not asserted

Each rewritten expression was compared against its verbatim predecessor
over 6 run-dir roots (absolute, one with a space, relative, trailing
slash, `.`, `/`) x 4 run ids for the lineage walk: **48 comparisons, 0
differences**. `user_uploads_path_for_run` returns `str(run_dir /
"user_uploads")`, so `Path(...)` of it round-trips to the same `Path`;
`WORKFLOW_INPUT_FILENAME` is the same literal, asserted in the probe.

### The grep was too broad, and the pattern is what changed

The proposed pattern was `'"\.workflow_input\.json"|"user_uploads'` — the
`user_uploads` half UNTERMINATED, so it matched any string merely
*starting* with the segment. It returned 11 hits in 7 files; only 5 were
doors. The other 6 are not sites the helper or the constant can serve, and
none of them is prose that got rewritten to dodge a grep:

- `runpod_pod_entry.py:154` — a log line, `f"user_uploads staging dir
  applied: ..."`. The segment is a WORD in a sentence.
- `_invention_loop_iter.py:327` — the dict key `"user_uploads_path"`, a
  kwargs name for `LoopContext`. A different string.
- `files/_run.py:345` — `rel_str.startswith("user_uploads/")`, a
  run-RELATIVE prefix test. The helper returns an ABSOLUTE path.
- `files/_run.py:640` — `path=f"user_uploads/{filename}"`, the upload
  response's wire path. Same absolute/relative mismatch, and it is a
  response-contract literal the FE and the download route both spell.
- `resume_context.py:105-106` — two `#` comment lines that quote the two
  joins in prose, documenting `parent_run_dir`'s only consumer.

The last two `files/_run.py` sites are the SAME two the 2026-08-22
verification below already dropped from the claim, so the pattern now
matches the claim the rule actually makes rather than a superset of it.

Two narrowings, both structural:

- Require the CLOSING quote — `"user_uploads"`, a whole quoted literal.
  That alone drops the log line, the dict key, the prefix test and the
  wire path. It stays broader than a join-anchored pattern would be, so
  `os.path.join(x, "user_uploads")` or `Path(run_dir, "user_uploads")`
  are still caught.
- Anchor `^[^#]*` — the literal must be reachable from the start of the
  line without crossing a `#`. That drops the two comment lines and
  nothing else. A trailing comment after real code still matches, since
  the `#` comes after the literal.

### The condition carries the `all`-mode escape

`[ "$RULES_MODE" = all ] || …`, as in `rule-user-paths-via-resolver` and
`rule-fe-time-format-single-source`. Without it a whole-tree rule is
skipped during the sweep, since nothing is staged there: the drift audit
the `--tree` exists for would never run, and the rule would be green while
checking nothing.

### Why the command excludes the doors rather than counting to one

Same argument as `rule-deep-merge-single-source`: a count-to-one check
passes only while the answer is exactly one string, so it also fails when
the canonical file MOVES. Naming each legal home as a pathspec exclusion
and banning every other match says the same thing and degrades correctly.
Both exclusions are load-bearing — each door spells its own literal, and
`_workflow_input.py` spells it twice more in the credential-hygiene
comment that explains the two gates.

Tests need no exclusion: they live under
`.claude/skills/amg-hooks/rules/`, outside every pathspec, so the
several that seed a tmp run tree by hand are structurally out of scope.
They SHOULD keep spelling the layout by hand — a guard that resolved the
name through the door could not catch the door resolving it wrongly.

Complements without overlapping: rule-submission-record-once claims
.run_submission.json only; rule-user-paths-via-resolver claims paths ABOVE
run_dir (USERS_DATA_DIR joins).

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: data-contracts)

Delete-check: The deeper delete is a single aii_lib run-dir layout module owning every
reserved name (fork_setup's helper already lives in aii_lib;
WORKFLOW_INPUT_FILENAME could move beside it) — the rule enforces the one-door
end-state either way, and tightens naturally if the constants are
consolidated.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Live drift at three server sites re-typing .workflow_input.json while
a sibling imports the constant. Sibling of pending rule-submission-record-once
(same shape, different reserved name) — house has accepted per-name one-door
rules, and this one has current violations. Note the deeper delete (one
aii_lib run-dir layout module) in the body.
- KEEP: Live drift (three re-typed literals for .workflow_input.json), classic
house one-door shape, trivial grep cost.
- KEEP: Live drift verified in proposal (re-typed literals in
_snapshot.py/side_chat_runner.py beside a correct import in _run.py); grep-
with-canonical-allowlist is the proven house one-door mechanism (#145, #218
precedent).

AUDIT NOTE (2026-08-28): the corpus audit reads this rule,
rule-user-paths-via-resolver and rule-path-gate-one-door as three slices of
one capability — server-side path construction: validation, root-join,
leaf-name — and proposes merging them into a single "server paths have one
door" rule with three clauses. That merge is an owner call at approval; the
same note sits in the other two so the overlap is visible from either side.
As of this landing all three have a built mechanism.

## History — the survey as proposed and as verified

Stock as measured 2026-08-28, before the landing: `.workflow_input.json`
re-typed at run_config/_snapshot.py and services/side_chat_runner.py (twice)
while api/files/_run.py imported the constant at both of its gates;
`user_uploads` hand-joined at _pipeline/_prep.py and api/files/_run.py
despite the helper. Nothing was broken — every spelling agreed — so this
was a drift gate, not a bug report, and it still is.

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**. A separate agent re-measured every factual
claim above against the live tree rather than trusting it. (The line
numbers it quoted for `aii_server/dashboard/api/files/_run.py` have since
drifted — that module grew — and are stripped here; the landing table above
carries the current ones.)

What it found:
Constant is real: `grep -rn WORKFLOW_INPUT_FILENAME` returns the definition
in aii_pipeline/src/aii_pipeline/_pipeline/_workflow_input.py. The two
hand-typed server sites were confirmed by
`grep -rn '\.workflow_input\.json'` — run_config/_snapshot.py and
services/side_chat_runner.py — while files/_run.py imports the constant
twice, once per gate, so the file stays out of the share-readable surface.

Corrected statement of fact (now folded into the lead):
For `user_uploads` the one-door claim covers exactly two filesystem joins —
aii_pipeline/.../_prep.py and aii_server/.../files/_run.py — against
user_uploads_path_for_run (aii_lib/src/aii_lib/run/fork_setup.py). Two
further _run.py sites were DROPPED from the claim: a run-relative prefix
test and a response wire path, which the helper's absolute-path return
value can serve neither of. Nothing is broken today — every spelling
currently agrees; this is a drift gate, not a bug report. That correction
held and drove the mechanism: the two dropped sites are exactly two of the
six the narrowed pattern now excludes.
