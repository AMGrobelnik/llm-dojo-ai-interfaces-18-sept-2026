<!-- hook: shared-dep-floors-agree -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# A dependency named in more than one pyproject carries one identical specifier, and requires-python agrees repo-wide

(Superseded 2026-08-26: all five named drifts are FIXED. What remains is
claude_cred_manager, which is deliberately not a workspace member. See
IMPLEMENTED at the end.)

Measured drift across the seven manifests: psutil >=5.9.0
(aii_pipeline/pyproject.toml:55) vs >=7.0.0 (aii_server/pyproject.toml:15);
google-genai >=1.0.0 (aii_lib/pyproject.toml:107) vs >=1.55.0
(aii_pipeline/pyproject.toml:22); httpx >=0.27 (aii_server:14) vs >=0.28.0
(aii_lib:21, aii_pipeline:42); python-dotenv >=1.0.0 (aii_lib:24) vs >=1.1.0
(aii_pipeline:48); pydantic >=2.0 (aii_lib:66) vs >=2.11.0 (aii_lib:130,
aii_pipeline:45); claude_cred_manager declares five fully-unpinned deps
(claude_cred_manager/pyproject.toml:10-16) and requires-python >=3.11 while
everything else pins >=3.12 and CI runs it against the 3.12 lock. One
resolver, one lock: only the max floor is real — the drifted lower floors
document minimums nothing ever tests. Same shape as recurring defect class #1
(twin declarations drift); also keeps the two claude-agent-sdk git specs
(aii_lib:108, aii_pipeline:15) from diverging.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: dependency-hygiene)

Proposed command (implemented at approval):

    python $RULE_DIR/scripts/check_floor_parity.py  # parse all pyprojects with tomllib+packaging, group by canonical name, fail on specifier mismatch

Delete-check: Partially — the duplication itself is inherent to per-package manifests (uv
has no shared-floor mechanism that removes per-member declarations), so parity
is pinned rather than the dimension deleted. Fixing to parity does delete the
misleading-lower-floor documentation.

Filter verdicts (3-lens adversarial, kept 2/3):
- KEEP: Measured drift across three shared deps plus requires-python; uv
offers no shared-floor mechanism so parity must be pinned. Cheap TOML cross-
check.
- KILL: uv.lock resolves one version workspace-wide for dev/CI, and with rule-
image-installs-lock-constrained landed the images stop reading floors too —
floor drift becomes inert documentation. A parity gate would police cosmetics.
- KEEP: tomllib parse of all manifests, group by dep name, assert single
specifier + uniform requires-python. Pure set math, deterministic, real
measured drift (psutil >=5.9 vs >=7.0). Loud.

## IMPLEMENTED (2026-08-26) — the five named drifts are all fixed

`scripts/check_floor_parity.py` judges **17** dependencies shared by more than
one workspace member, plus `requires-python`. Zero disagree, so this arrives
green and guards the class.

Every drift this body names has since been repaired:

| dependency | body claimed | today |
|---|---|---|
| psutil | >=5.9.0 vs >=7.0.0 | agrees |
| google-genai | >=1.0.0 vs >=1.55.0 | agrees |
| httpx | >=0.27 vs >=0.28.0 | agrees |
| python-dotenv | >=1.0.0 vs >=1.1.0 | agrees |
| pydantic | >=2.0 vs >=2.11.0 | agrees |

**Scope is the workspace, read from the root manifest rather than hardcoded.**
`tool.uv.workspace.members` lists aii_lib, aii_pipeline, aii_server and
aii_launcher. A member added later is covered without touching this rule; a
baked-in list would quietly stop covering the tree.

### `claude_cred_manager` is out of scope, and that is stated not hidden

It is not a workspace member by design — a separate service with its own deploy
unit, absent from `uv.lock`, pruned by `uv sync` and reinstalled by CI with
`--no-deps` against THIS lock. CLAUDE.md documents that at length.

Its two real findings are therefore **owner decisions, not parity repairs**:
five fully unpinned dependencies (fastapi, httpx, pydantic, pyyaml, uvicorn)
and `requires-python >=3.11` where every member pins `>=3.12`. Adding floors to
a separately-deployed service changes what ITS environment resolves. Recorded
here so the exclusion is visible rather than silent.

The one other apparent mismatch is an artifact: `aii_lib` appears as a
dependency of its siblings under different extras (`[ability-client]` vs
`[ability-server]`). Those are different dependency EDGES, not two floors on
one package, so intra-workspace edges are skipped.

### Repos with no uv workspace (e.g. notes-repo) skip cleanly

This check is shared across repos via `general/`. A repo with no
`pyproject.toml` at its root — notes-repo, which has no uv workspace at all — has
no workspace manifest to read members from, so there is nothing to compare
floors across. `check_floor_parity.py` detects the missing root manifest
before scanning and exits 0 with a one-line skip note, instead of failing the
commit for a workspace that was never there.

### A workspace below the 3-member floor skips cleanly too

Floor parity needs more than one manifest to compare — `scan()` itself
treats fewer than 3 actual member manifests as a "layout moved" failure
(rc 2), the real signal for a workspace that used to have more members than
it does now. That code used to be the ONLY gate: `main()` checked merely
whether a root `pyproject.toml` existed, so a repo whose workspace legitimately
has 0, 1 or 2 declared members — via a missing `[tool.uv.workspace]` table or
a short `members` list — fell through into `scan()` and hit that same rc-2
bail, misreporting "the workspace layout moved" for a workspace that simply
had not grown that far yet.

`main()` now reads `tool.uv.workspace.members` from the root manifest itself
(a missing table counts as 0 members) before calling `scan()`. Below the
3-member floor it prints a one-line skip note and exits 0. At or above the
floor, `scan()` runs exactly as before, so a workspace that DOES declare 3+
members but is missing a manifest for one of them still bails at rc 2 — that
case is unchanged.
