<!-- hook: submission-record-once -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# The .run_submission.json record and the flat shared-volume run path are written, located, and parsed only via one canonical helper

The literal '.run_submission.json' plus the AII_DATA_DIR/'runs'/run_id path
build plus the record's field names are re-typed at four+ independent sites:
writer runs_helpers.py:497-507, readers api/__init__.py:435-440
(_runpod_submission_owner), runs_list_poll.py:267-272
(_provisional_meta_from_submission), run_start_failures.py (~line 171), name
literal files/_run.py:167, and signals.py:96. Each reader independently re-
implements the parse and the falsy-vs-missing distinction — defect class 2
(b76d73f9c, bdc2f7b49) and class 1 (584f91167: same rule re-implemented n
times, one drifts). A field rename or record extension must currently land in
4+ files to stay coherent.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: python-server)

Command (BUILT — the mechanism exists and the frontmatter carries it):

    python3 $RULE_DIR/scripts/submission_single_source.py  # AST string-literal scan, docstrings excluded: '.run_submission.json' appears only in dashboard/api/_submission.py

TWO CORRECTIONS TO THIS PROPOSAL, both made against the tree.

**The home is `dashboard/api/_submission.py`, not
`dashboard/services/run_submission.py`.** The record's four consumers all live
under `dashboard/api/`, and one of them is the file browser, which needs the
FILENAME but has no run id to build a path from — so the constant is exported
beside the helpers rather than hidden behind them.

**The gate pins the NAME, not the flat run path.** The proposal wanted both.
Measured, there are four executable `AII_DATA_DIR / "runs"` joins and two of
them plausibly SHOULD differ: `runs.py` builds a listing ROOT with no run id,
and `runs_helpers.py` builds the directory at admission rather than resolving
an existing one — a different job from `run_dir_for`'s local-vs-RunPod
resolution. Pinning all four would push two correct call sites through a helper
that answers a question they are not asking. That half stays prose.

ADOPTION (2026-08-25): the record is consolidated. `SUBMISSION_FILENAME`,
`submission_path` and a best-effort `read_submission` live in one module, and
the four sites import them. Equivalence was proven against the pre-change
reader across missing, corrupt and valid records — identical in every case.

Verified against history: on the tree before the consolidation the gate exits 1
and names all four sites; today it exits 0.

A first draft treated a MISSING `_submission.py` as "could not run" and exited
2 — going silent on precisely the pre-consolidation state it exists to catch.
That is the second gate this session with that shape (the query-key checker had
it too), which suggests it is the default mistake when a gate and its remedy
are written together.

Delete-check: The record itself cannot be deleted — api/__init__.py:414-430 documents it as
the ONLY ownership signal during the RunPod provisioning window. The deletable
dimension is the duplication: collapse writer+readers into one accessor module
(write_submission / read_submission / SUBMISSION_FILENAME), then the rule
enforces that end-state.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Four independent re-typings of the record literal, path build, and
field names; record cannot be deleted (only ownership signal during
provisioning). Collapse to one helper then enforce.
- KEEP: Four re-typed sites of a load-bearing literal+path+schema (the only
ownership signal during provisioning). Collapse to one helper then grep for
the literal — cheap, low FP, classic single-source rule.
- KEEP: Literal-grep for '.run_submission.json' outside the canonical helper
module (8 sites confirmed today). Trivially implementable, fails loudly on any
new re-typing.

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**.
A separate agent re-ran every measurement above against the live tree.

What it found:
`grep -rn "run_submission" --include=*.py .` returns 13 non-test hits. Sorting
them into code vs prose: WRITER runs_helpers.py:497 (`run_dir =
settings.AII_DATA_DIR / "runs" / ctx.run_id`) through 507 (`(run_dir /
".run_submission.json").write_text(...)`) — cite 497-507 is EXACT. READER
__init__.py:435 path build, 437 `json.loads(...).get("username")`, 442 `return
owner or None` (cite 435-440, close). READER runs_list_poll.py:267 path build,
269 parse (cite 267-272, close). NAME LITERAL files/_r

Corrected statement of fact:
There are 3 code sites that build the record path (1 writer + 2 readers) plus
1 name-literal site, not 'four+ independent' readers. Two of the six cited
sites — run_start_failures.py:171 and signals.py:96 — are docstring prose, not
re-implementations, so they cannot drift. The two readers do share an
identical `try: json.loads(p.read_text()) except (OSError, ValueError)` shape
but implement genuinely DIFFERENT contracts (__init__.py returns `owner or
None` for an ownership signal; runs_list_poll.py returns None unless
`rec.get("username") == owner` and then projects a provisional RunListItem),
so collapsing them is a real but modest dedup, not the removal of a live
coherence bug. files/_run.py's literal is at 171.
