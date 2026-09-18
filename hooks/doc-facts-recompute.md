<!-- hook: doc-facts-recompute -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Registered numeric/structural claims in CLAUDE.md and README recompute to what the prose says

Live drift found: CLAUDE.md's split-layout section claims 'used in 26 places
(19 Python, 7 frontend)'; recomputing (tracked _<stem>/ dirs with a sibling
<stem>.py/.ts/.tsx) gives 27 (20 Python, 7 frontend). README.md's repo-layout
table says tests are 'the testpaths in pytest.ini (tests/, aii_lib/tests/,
...)' while omitting .claude/skills/amg-hooks/rules — where 487 test
files actually live and which pytest.ini line 2 lists; aii_lib/tests holds
only __pycache__. CLAUDE.md itself records five separate incidents of stale
claims discovered manually ('This said multi-arch, which was wrong in both
halves'; 'This section used to say the frontend had no equivalent... no longer
true'; ability count 29→30; the keepalive cache-writer note 'corrected
2026-08-15'; the magic-link 'broken at oauth_flow.py' claim disproved). Each
correction cost an investigation; a manifest makes registered claims self-
verifying.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: docs-comments)

Proposed command (implemented at approval):

    python3 scripts/recompute_facts.py facts.yaml   # superseded; the $RULE_DIR
                                                   # prefix is dropped so ready.py
                                                   # does not read these as owed.
                                                   # Built as one script with the
                                                   # registry in code: a fact needs
                                                   # its recomputation written
                                                   # anyway, so a separate yaml
                                                   # would be a second place to drift.  # each fact: {doc, extract_regex, recompute: shell, comparator}; fail prints prose value vs recomputed value per fact; start with ~5 opt-in facts (split-dir count, pytest testpaths list, ability count floor, launcher flag count)


## IMPLEMENTED 2026-08-26 — `scripts/check_doc_facts.py`

    .venv/bin/python $RULE_DIR/scripts/check_doc_facts.py

Arrives green: 4 registered claims, all agreeing with the tree.

**NO CONDITION — this runs on every commit, and the deleted one was the
defect.** It used to fire only when the diff touched `CLAUDE.md`, `README.md`,
`pytest.ini`, the pipeline `steps/` tree or `scripts/local/watchers/`. But
three of the four registered claims are recomputed from the SHAPE of the tree,
not from those files: a commit that adds a `_<stem>/` split package anywhere
makes CLAUDE.md's split-layout sentence false without touching one of those
paths. `b4bc3ca3c` did exactly that — the count went stale, the condition
skipped the rule, the commit landed, and the whole-tree sweep in CI found it
minutes later. A condition that names the DOCUMENT cannot cover a claim about
the TREE.

Nothing is bought by keeping it: the whole check is 4 regex searches and two
`git ls-files` passes, measured **0.059 s** — below the noise of the condition
process it replaced, and three orders of magnitude under the gate's slowest
rule. Conditions exist to keep verification effort near zero; there is no
effort here to spare.

The four documents are read from the INDEX (`git show :<path>`), like the
`git ls-files` the recomputations already used. Now that the rule runs on
every commit, a disk read would let a peer's modified-but-unstaged CLAUDE.md
fail a commit that does not contain it — the same shape that failed two
unrelated commits on 2026-09-05 and moved the whole-tree rules onto the index.

**Both drifts this rule cites are already fixed**, which is why the registry
starts where it does. The split-layout claim now reads 27 (20 Python, 7
frontend) and recomputes to exactly that. README's testpaths sentence was
rewritten this session — it had named five paths of which three hold no tracked
file, while omitting the rules tree that holds every suite.

**ONLY STRUCTURAL CLAIMS ARE REGISTRABLE, and that boundary is the design.**
A count that moves with ordinary work is a census, and this corpus already
knows a census in prose "is a snapshot that dates itself". Registering one makes
the gate fail on honest commits. Measured evidence for the exclusion: CLAUDE.md
says oxlint runs over 687 files and it is now 693 — six days' drift with nothing
wrong. That claim is deliberately not registered, nor is README's "~529 test
modules", whose own tilde says it is approximate.

Registered instead: how many step modules the pipeline has, how many paths
pytest collects, how many split packages exist, how many architectures publish.
Those move on purpose.

**Two bugs in the checker were caught BY the checker, because the docs were
right.** Counting `steps/_*` matched `__init__.py` and reported a fourth phase
against a correct sentence; and the ARCHES pattern demanded its words on one
line, where the real sentence wraps, so it reported "no longer matches" against
unchanged prose. Both are recorded in the code — a recompute rule fails toward
false alarms, and each one spends someone's attention on nothing.

An unmatched pattern is itself reported rather than skipped: a reworded claim
must either have its pattern repointed or its registry entry deleted, because a
registration matching nothing checks nothing.

Probed six ways: a wrong split total (the very 26/19/7 this rule was written
about), a wrong phase count, a wrong testpaths count, a wrong arch count, and a
reworded claim all fire; the untouched documents do not.

Delete-check: Partial deletion is real and should shape the manifest: prose COULD stop
quoting recomputable numbers and point at a command instead. But this repo's
style uses measured counts as the argument ('measured, not claimed'), so the
owner opts claims IN; anything not worth a recompute line gets rewritten to
drop the number. The rule only polices what the manifest registers, so the
maintenance cost is bounded by choice.

Filter verdicts (3-lens adversarial, kept 2/3):
- KEEP: Live drift in numeric claims and this repo deliberately quotes
recomputable numbers in prose — the register approach (claim + command) is the
honest closure. comment-drift is adjacent-code only and cannot cover doc-level
facts.
- KILL: The claim manifest is itself a hand-maintained twin that rots, and
CLAUDE.md's own philosophy cuts against it ('that 29 is the figure from THAT
measurement, not a constant to assert') — measured figures are dated
observations, not invariants. The found drift (26 vs 27) is harmless;
maintenance cost exceeds the harm.
- KEEP: Manifest of (claim-anchor, recompute command) pairs — vacuous for
unregistered claims by design, but registered ones fail loudly and live drift
exists ('26 places' vs 27 recomputed). Honest scope; implementable. Keep the
manifest small and load-bearing.

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**.
A separate agent re-ran every measurement above against the live tree.

What it found:
Split count: I enumerated tracked `_<stem>/` dirs having a sibling
`<stem>.py|.ts|.tsx` — result 20 Python + 7 frontend = 27, against
CLAUDE.md:186 which reads "Splitting follows one layout, used in 26 places (19
Python, 7 frontend)." So the recomputation holds exactly. testpaths:
`pytest.ini` line 2 is `testpaths = tests aii_server/tests .claude/skills/amg-
rule-engine/rules`, while README.md:26 reads "the `testpaths` in `pytest.ini`
(`tests/`, `aii_lib/tests/`, `aii_launcher/tests/`, `aii_serve

Corrected statement of fact:
Everything holds except the test-file count: 497, not 487 (the number moves as
rules land, which is itself an argument for computing rather than asserting
it). Two live doc-fact defects worth fixing on their own: CLAUDE.md:186 says
26 (19 Python) where the tree has 27 (20 Python) — the uncounted split is one
of the 20 Python entries; and README.md:26 + README.md:315 both describe a
five-entry testpaths list that pytest.ini has not had since the rule-engine
migration, naming three directories with zero tracked files while omitting
`.claude/skills/amg-hooks/rules` where all 497 test modules live.
README.md is in `PUBLIC_DOCS=(README.md CONTRIBUTING.md .env.example)` in
aii_public/sync.sh, so that one ships to the public export.
