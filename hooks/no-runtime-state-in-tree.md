<!-- hook: no-runtime-state-in-tree -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Every writable path declared in aii_server settings anchors under AII_DATA_DIR

The gate arrives GREEN (re-run 2026-08-28, rc=0): BASE_DIR anchors exactly
two paths, `templates` (settings.py:279) and `staticfiles` (:520), both in
the assets allowlist, and the mkdirs the proposal found were removed in
`94fe89cf1`. The mechanism checks the settings layer only — which is where
the name exists: `BASE_DIR` appears in no other module in the package
(ADOPTION note below) — so the rule is a regression guard over the paths
settings DECLARES, not a scan of the working tree, and the H1 claims no
more than that.

## History — the defect as found

settings.py:124-129 anchored CACHE_DIR = BASE_DIR/'.cache' and mkdir'd it
inside the package tree, while every sibling runtime path had already moved
out: LOG_DIR = AII_DATA_DIR/'logs'/'server' (then settings.py:597), DATABASES
NAME = AII_DATA_DIR/'db'/'aii_server.sqlite3' (then :341). The residue was
visible in the working tree: aii_server/db.sqlite3 (stale — nothing in
settings pointed there anymore), .cache/, temp/, data/, image-gen/,
fig1_all..fig5_all, fig_failure_distribution_all — all untracked clutter
inside package source. (The proposal also claimed the write "silently
vanishes on pod swap"; the INDEPENDENT VERIFICATION below measured that
claim and it does not hold, so it is retired from the statement of fact.)

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: python-server)

Command (BUILT — the mechanism exists and the frontmatter carries it):

    python3 $RULE_DIR/scripts/no_pkg_runtime_state.py  # AST of config/settings*.py: every path anchored under BASE_DIR, including via a derived name, has a first segment in {templates, staticfiles}

Condition: `git diff --cached --name-only -- 'aii_server/config/settings*.py' | grep -q .`

Delete-check: The fix WAS deletion — the package-source mkdirs are gone
(`94fe89cf1`) and the debris cleared; the rule enforces the clean end-state
so the clutter cannot re-accrete.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Keep as the code-level pin (CACHE_DIR is the last writable path
anchored in the package tree); the fix is a repoint plus one-time rm. Absorbs
rule-no-runtime-debris-in-packages, whose residue is the same file list.
- KEEP: Keep the code-shaped half: settings paths anchor under AII_DATA_DIR
(CACHE_DIR is the live offender). That is a cheap settings.py check with no
machine-state dependence. Absorbs rule-no-runtime-debris-in-packages; the on-
disk debris is a one-time rm, not a per-commit disk scan.
- KEEP: Source-level check on settings.py writable-path anchors (no BASE_DIR-
anchored mkdir/cache paths) is deterministic commit-content — keep that half.
The on-disk debris half belongs to a one-time rm, not the gate (absorbs rule-
no-runtime-debris-in-packages). My grep incidentally hit .cache/logs debris,
confirming the live violation.

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**.
A separate agent re-ran every measurement above against the live tree.

What it found:
Line cites all check out: settings.py:124 `CACHE_DIR = BASE_DIR / ".cache"`,
125 `DISP_MESSAGES_DIR = CACHE_DIR / "messages"`, 128-129 the two mkdirs; 341
`"NAME": AII_DATA_DIR / "db" / "aii_server.sqlite3"`; 597 `LOG_DIR =
AII_DATA_DIR / "logs" / "server"`. `ls -la aii_server` shows every named
residue present (.cache/, data/, temp/, image-gen/, db.sqlite3 253952 B,
fig1_all..fig5_all, fig_failure_distribution_all — plus
fig_hallucination_reduction_all and aii_data/, which the why does not name

Corrected statement of fact:
"on the deployed image a write into the container overlay instead of the
shared volume, so it silently vanishes on pod swap" does not hold: no live
code writes into CACHE_DIR/DISP_MESSAGES_DIR, and its sole consumer wipes it
at every startup by design (apps.py:18). The real, smaller finding is a
vestigial pair of mkdirs into package source at settings import plus ~720 MB
of stale untracked debris in the checkout. Deleting the debris is trivial;
repointing CACHE_DIR touches settings + the boot path and one test that
monkeypatches DISP_MESSAGES_DIR, hence moderate.

RE-MEASURED 2026-08-24 — both halves of that "real, smaller finding" are
now closed, so this proposal has no live defect left behind it:

- The vestigial mkdirs are gone. `94fe89cf1` ("settings stops creating cache
  dirs in package source") removed them, and settings.py:126-131 now carries
  the reasoning verbatim — settings import runs on every boot including the
  throwaway offline ones, which is exactly why creating them at import was
  wrong. `dashboard/apps.py:29` still mkdirs defensively before reading, so
  nothing regressed.
- The debris does not reproduce at anything like that size. `aii_server/.cache`
  is **8.0K**, and the checkout has **0** untracked-and-not-ignored files
  totalling 0.0 MB. The ~720 MB figure was counting GITIGNORED build caches
  (`aii_frontend/node_modules/.cache` alone is 247 MB) — ordinary build
  artifacts, not runtime state written into package source, which is what
  this rule is about.

The rule may still be worth having as a regression guard; what it no longer
has is a defect to point at. Judge it on the invariant, not on this evidence.

ADOPTION (2026-08-25): BUILT as a regression guard, and only the source half —
the on-disk half is deliberately absent, which is what all three filter verdicts
asked for ("the on-disk debris half belongs to a one-time rm, not the gate").
A per-commit scan of an untracked working tree would also make the verdict
depend on machine state, so two checkouts of the same commit could disagree.

Measured 2026-08-25: `BASE_DIR` anchors exactly two paths, `templates` (:279)
and `staticfiles` (:520), both in the assets allowlist — so the gate arrives
green. It is confined to the settings layer, which is where the name exists:
`BASE_DIR` appears in no other module in the package, and `settings_light` and
`settings_models_only` republish it (each copies the base module's UPPERCASE
names into its own globals), so all three are scanned.

**Taint follows derived names, because the original defect was two lines, not
one.** It was `CACHE_DIR = BASE_DIR / ".cache"` followed by `DISP_MESSAGES_DIR =
CACHE_DIR / "messages"`. A check for the literal token `BASE_DIR` sees the first
and is blind to the second — half of the very defect it was written for. The
checker resolves the chain through the AST.

`.parent` ENDS the chain rather than extending it. `REPO_ROOT = BASE_DIR.parent`
points out of the package at the project root, so paths under it are not
package-source writes. Treating an escape as a descent would have flagged the
one line in the file that gets this right, which is the same failure the
user-dir gate hit when it punished the fix it had asked for.

Proven to bite in a throwaway tree: both lines of the original defect are named,
while a `REPO_ROOT`-derived config path, `templates`, `staticfiles` and an
`AII_DATA_DIR` path all stay silent. Real tree: 0.
