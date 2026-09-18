<!-- hook: docker-context-no-big-ignored-dirs -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: RULE_DIR
# Every gitignored directory over 100 MB on disk is excluded from both role images' build contexts, evaluated with dockerignore (root-anchored) semantics, and both role dockerignore files exist

Stock today: **green** — `scripts/check_context_bloat.py` sizes every
gitignored directory (13 over 100 MB, ~118 GB) and both role contexts
exclude every one; the recurrence recorded below was fixed the same day
the checker landed (see IMPLEMENTED at the end).

**H1 narrowed to the mechanism (audit, 2026-08-28):** the old tail said
"every Dockerfile.* has a sibling dockerignore", which the script does
not check — it hard-requires the two ROLE files
(`Dockerfile.server.dockerignore`, `Dockerfile.pipeline.dockerignore`)
and bails when either is missing, and `Dockerfile.base` needs no
patterns (six lines of `*` plus negations; it copies three files). That
existence check was the checkable core of
`rule-dockerfile-sibling-dockerignore`, which the same audit killed in
favour of this rule — it exists in neither tree now, so this script is the
only place the check lives.

## History — four fixes in one day, then a recurrence (both closed)

Four commits in one day fixed exactly this defect (be3c1f33c aii_data/ 20 GB,
0e9288a2a four more ~70 GB, b3e5782c4 the too-narrow temp/ rule, 06209d955 the
role files again — all 'gitignore matches at every depth, dockerignore is
root-anchored').

It then went live AGAIN: .claude/skills/aii-owid-datasets/_index/
measures 708 MB, is gitignored (.gitignore:194), is excluded by the global
.dockerignore:140 — but had NO line in Dockerfile.server.dockerignore, and
BuildKit uses the per-Dockerfile file INSTEAD of the global one
(Dockerfile.server.dockerignore:4-7), so every published aii_server image —
watcher builds included, not only a manual --rebuild — carried those bytes
(29.3 MB of _index reaching the image after the table_metadata excludes;
see the verification below) until the pattern was added on 2026-08-26.
Measured on this machine: aii_pipeline/data 64 GB, aii_data 20 GB,
aii_server/temp 14 GB sit one missed pattern away from a 3.9 GB image.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: docker-deploy)

Proposed command (implemented at approval):

    .venv/bin/python $RULE_DIR/scripts/check_context_bloat.py --floor-mb 100  # git check-ignore'd dirs, du floor, evaluated against each Dockerfile.*.dockerignore matcher

Proposed condition: `[ "$RULES_MODE" = all ] || git diff --cached --name-only | grep -qE '(^Dockerfile|dockerignore$|gitignore$)'`

Delete-check: The three hand-mirrored ignore files cannot be collapsed — BuildKit's per-
Dockerfile ignore selection is fixed behavior. The semantic sweep is itself
the collapse: it makes verbatim pattern-mirroring between the files
unnecessary by checking the outcome instead. The sibling-file existence
assertion also closes the fallback trap for any future Dockerfile.newrole. The
matcher already exists to reuse: rule-docker-image-
guards/test_docker_context_reachability.py implements dockerignore pattern-to-
regex with last-match-wins.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Four same-day commits fixed this class and it is live AGAIN — the
gitignore-vs-dockerignore semantics mismatch is a standing trap. Semantic
sweep with dockerignore evaluation is the only check that matches reality.
- KEEP: Four fix-commits in one day and live again — the gitignore-vs-
dockerignore anchoring mismatch is a proven recurring trap on a repo with 60+
GB local dirs. Keep, but run the disk-size sweep in all-mode and a cheaper
dockerignore-presence/semantics check at commit; a full du per commit is too
heavy.
- KEEP: Reimplement dockerignore root-anchored matching (~50 lines, well-
specified) and sweep gitignored dirs >100MB; the dockerignore-sibling-exists
half is pure commit content. Four same-day fix commits plus a live re-
occurrence prove recurrence; run the disk half in all-mode on the build host.
Implementable and loud.

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**.
A separate agent re-ran every measurement above against the live tree.

What it found:
The GAP is real, the MAGNITUDE is off by 24x. Verified: `du -sh
.claude/skills/aii-owid-datasets/_index/` -> 708M; .gitignore:194 and
.dockerignore:140 both carry `.claude/skills/aii-owid-datasets/_index/`;
Dockerfile.pipeline.dockerignore:228 carries it too;
Dockerfile.server.dockerignore has only `_setup/` (:175) and no `_index/`
line. Dockerfile.server.dockerignore:4-7 states the BuildKit replacement rule
verbatim, and Dockerfile.server:424-428 is the catch-all `COPY --exclude=... .
/research-monorepo

Corrected statement of fact:
Not 708 MB — 29.3 MB. The two ~340 MB JSONs are already caught by the
`**/table_metadata*.json` rules; only 29.3 MB of _index reaches the server
image. Also 'a manual aii_launcher --rebuild --local' is too narrow: the same
dockerignore governs the aii-image-watcher's builds, so every published
aii_server image carries those bytes, not just manual ones. Two things the
proposal understates in its favour: _index is not the only leak — sweeping
every gitignored path through the moby matcher shows 105.4 MB across 110
entries reaching the server context (aii_server/image-gen 15.5 MB,
.claude/plugins 6.0 MB, aii_server/fig*_all ~30 MB combined,
.claude/skills/aii-semscholar-bib/.local_venv 9.6 MB — .venv is excluded,
.local_venv is not); and Dockerfile.pipeline.dockerignore already excludes all
of it, so this is one-sided drift between two hand-mirrored files, fixable
with one line.

## RE-MEASURED 2026-08-26 — the live defect is FIXED; the gate is environment-bound

**The defect was real and is closed.** `.claude/skills/aii-owid-datasets/_index`
measures **708 MB**, is gitignored, and was listed in the global
`.dockerignore` — but BuildKit uses the per-Dockerfile file INSTEAD of the
global one when it exists, so that line never applied to a server build.
`Dockerfile.pipeline.dockerignore` already carried its own copy; the server file
did not. The pattern is added, and verified to match a file beneath the
directory rather than merely being present.

**Every other big gitignored directory was already excluded**, which narrows
what the gate is for. Sweeping the whole tree for gitignored directories over
100 MB and evaluating each against the server file's patterns:

| directory | size | excluded before this |
|---|---|---|
| `aii_pipeline/data/seed_hypo_v2` | 64 GB | yes |
| `aii_data` | 19 GB | yes |
| `aii_server/temp` | 13 GB | yes |
| `resources` | 6.3 GB | yes |
| `.claude/skills/.ability_client_venv` | 5.8 GB | yes |
| `.claude/skills/aii-owid-datasets/temp` | 5.5 GB | yes |
| `.claude/skills/aii-owid-datasets/_index` | 708 MB | **NO** |

Two things that nearly became wrong findings, both caught by checking:

- The owid `temp` directory looked unexcluded to an anchored grep. It is
  covered by `**/temp` on line 118, whose own comment explains the
  root-anchoring difference between dockerignore and gitignore. The grep was
  wrong, not the file.
- `Dockerfile.base.dockerignore` has no owid patterns at all — and needs none.
  It is six lines of `*` plus three negations, because `Dockerfile.base` copies
  only three files from the repo. Adding patterns there would have been noise.

**The mechanism is deferred for an environment reason, not an effort one.**
This check must walk the FILESYSTEM — a build context is the filesystem, not
what git tracks — and a CI worktree is a fresh checkout containing none of these
directories. It would therefore report cannot-run in CI exactly as
`rule-docker-context-no-credentials` does, and that rule is already carried in
the pending-mechanism runner's permission list for the same reason. Building a
second checker with the same blind spot buys little; the honest options are to
gate it locally only, or to derive expected exclusions from `.gitignore` so the
check works on a tracked-file basis. That choice is the owner's.
## IMPLEMENTED (2026-08-26) — the named instance is already fixed

`scripts/check_context_bloat.py` sizes every gitignored directory and asks both
role contexts whether they admit it. Measured: **13 directories over 100 MB,
~118 GB total, 0 admitted by either.** The instance this body reports as "live
AGAIN", `.claude/skills/aii-owid-datasets/_index/` (708 MB), was excluded from
`Dockerfile.server.dockerignore` earlier the same day, so this arrives green.

The threshold is on DISK SIZE, not a name list. A list needs editing every time
a skill starts caching something — which is how the four incidents in one day
happened. Anything big enough to matter is found by measuring.

**In CI it reports cannot-run, and that is correct.** A worktree is a fresh
checkout carrying none of these directories, so the floor refuses to certify a
sweep it cannot back up. Verified in a `git archive HEAD` tree: 0 directories,
exits with the marker rather than a vacuous pass. Recorded in `_MAY_NOT_RUN`
alongside `rule-docker-context-no-credentials`, which is the same shape for the
same reason.

**The dockerignore evaluator is a second copy on purpose.** Its sibling asks the
same question of credential-shaped files, but a rule script runs standalone, so
the repo root is not on `sys.path` and the shared `tests/` package cannot be
imported — verified, `ModuleNotFoundError`. A `sys.path` bootstrap is the hack
the house rules forbid, and importing across rule directories breaks when either
rule is approved and `git mv`-ed. The three semantics that are easy to get wrong
are restated at the copy: last match wins, `**` spans zero or more directories,
and a directory pattern covers everything beneath it.
