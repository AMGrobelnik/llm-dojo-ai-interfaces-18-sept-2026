<!-- hook: hey-api-client-regen-clean -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# lib/api/_hey-api/** is byte-identical to a fresh openapi-ts generation from the committed openapi.json

The existing gates cover only the first hop:
scripts/lint/check_openapi_drift.py and rule-openapi-snapshot-integrity both
verify BE source vs the committed openapi.json — neither regenerates the TS
client. The second hop is manual and forgettable: commits 92958849e
('regenerate the typed client for the viz image-model field'), b6c970ff5, and
84fc6199b are each a separate 'regenerate the client' chore. openapi-
ts.config.ts:30 sets clean:true, so any hand edit inside _hey-api/ is silently
destroyed on the next codegen — a byte-diff gate catches both a stale client
and a doomed hand edit.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: frontend-config)

Mechanism (implemented 2026-08-26, `scripts/regen_and_diff.sh`):

    bash $RULE_DIR/scripts/regen_and_diff.sh

Arrives green: the committed client is **byte-identical** to a fresh
generation — 17 files, `diff -r` exit 0, whole check in 0.5 s.

**THE PROPOSAL'S `output.path=$TMPDIR` DOES NOT WORK, and the reason is worth
recording because it fails as false drift rather than as an error.** The
generated `client.gen.ts` imports the runtime config by a path relative to the
OUTPUT directory — `../hey-api-client.ts`. Generate into `/tmp` and it emits
`../../../home/<user>/.../hey-api-client.ts` instead, so the trees differ by
exactly one line, every run, forever. The output therefore went to a SIBLING of
`_hey-api` (`lib/api/.regen-check`), where the relative path resolves the same.
Measured both ways: same parent, byte-identical; different parent, one-line diff.

**That SIBLING is what "Out-of-tree since 2026-09-03" below retired** — the
depth constraint is real and still holds, but it is satisfied by mirroring
`lib/api/` in a scratch tree rather than by writing inside the checkout. Read
the two together: this paragraph is the constraint, that section is how it is
met today.

Two more shapes that fail, both measured while building it:

| attempt | result |
|---|---|
| spread the real config | loses `input` — "missing input" |
| config outside `aii_frontend` | `openapi-ts` unresolvable |

The config was therefore derived from the real one by rewriting ONLY the output
path, in place. Both of those failures are gone too — the shadow tree below
carries a symlinked `node_modules`, which makes `@hey-api/openapi-ts`
resolvable from outside `aii_frontend`, so the config is now a plain COPY with
no rewrite at all and stays in lockstep by construction rather than by `sed`.

**`clean: true` makes a mis-scoped config destructive**, so the script refuses
to run unless the output slot is provably its own — a config still pointing at
`_hey-api` would delete the committed client instead of comparing to it. (The
guard used to confirm a `sed` rewrite of the config; today there is no rewrite
and it confirms the output path directly. See the section below.) A trap removes
the scratch tree on every exit path; verified no strays.

Probed four ways: a pristine tree passes; a hand edit inside `_hey-api/` fires
(the case `clean: true` would silently destroy); a spec change with no
regeneration fires and names the new field in the diff; and an uninstalled
checkout reports cannot-run rather than a comfortable pass. CI's python group
runs before frontend deps install, so the rule is in the runner's permission list.

Superseded proposal (prefix dropped so `ready.py` does not read it as a script
still owed):

    scripts/regen_and_diff.sh  # temp config with output.path=$TMPDIR

Proposed condition: `[ "$RULES_MODE" = all ] || git diff --cached --name-only -- aii_frontend/lib/api aii_frontend/openapi-ts.config.ts aii_frontend/package.json | grep -q .`

Delete-check: Could delete the committed-artifact dimension by generating at build time only
(never committing _hey-api/) — but the image build deliberately runs codegen
from the COMMITTED snapshot when no venv exists (package.json
codegen:openapi:refresh fallback), and oxlint/tsgo/vitest all need the client
present in-tree, so the committed copy stays and must be provably fresh.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: The second hop (openapi.json → committed TS client) is manual and
evidenced as forgettable by its own regen commits; existing gates verify only
BE-source-vs-snapshot. Byte-identity regen check closes the seam.
- KEEP: The second hop (openapi.json → TS client) is manual and forgettable
with commit evidence of hand-regeneration. Regenerate-and-diff, condition-
gated on openapi.json/_hey-api changes, closes a real parity gap the existing
snapshot rule stops short of.
- KEEP: Regenerate into a temp dir with the lockfile-pinned openapi-ts and
diff against committed _hey-api/. Deterministic given pinned generator
version; the second-hop drift (92958849e was a manual catch-up) is real. Fails
loudly on any drift.

## Out-of-tree since 2026-09-03

**The sibling output was the one thing keeping this rule parked.** It works
perfectly in isolation and is unsafe in a sweep: `RULES_MODE=all` runs every
rule CONCURRENTLY, and the frontend gates — oxlint, fallow — walk
`aii_frontend/` while this rule has `lib/api/.regen-check/` and
`.regen-check.config.ts` sitting in it. Those gates then lint and reachability-
scan 17 files that exist for about a second, and report on them. Nothing is
corrupted and nothing is lost; the failure is a NEIGHBOURING rule going red for
a reason that has nothing to do with its own subject, which is the worst kind
of red because the evidence has deleted itself by the time anyone looks. Two
concurrent runs of this rule alone had the same problem from the other
direction: one fixed path, two writers, and the loser's `clean: true` deletes
the winner's output mid-diff.

The scratch tree now lives under `$TMPDIR` (`mktemp -d`, so every invocation
gets its own), and **nothing whatsoever is written inside the checkout.**

Getting there needed the depth constraint above satisfied without an in-tree
path, and the shape that does it is a SHADOW of `aii_frontend`: every entry
symlinked in, three levels deep, with `lib/api/_hey-api` left out and replaced
by a real empty directory. `lib/api/hey-api-client.ts` is then exactly one
level above the output again, so `client.gen.ts` emits `../hey-api-client.ts`
and the trees match. Symlinks, not copies — the shadow costs milliseconds and
duplicates no file, `.env.local` included.

Four details, each measured while building it:

| detail | why |
|---|---|
| `-o <abs temp path>` | CLI wins over the config outright |
| config COPIED, not linked | its paths resolve beside it |
| output slot asserted absent | a symlink there would be deleted |
| `--no-log-file` | no log lands in the working directory |

The `-o` override was verified to win rather than merely to be accepted:
passing it produced nothing at the config's own output path. That is what
removes the old `sed` rewrite and its confirmation grep — with an absolute
temp path forced on the command line, there is no config edit to get wrong.
The remaining guard is aimed at the thing that is actually destructive: if the
output slot exists at all — a symlink into the checkout, say, because the
shadow stopped skipping `_hey-api` — the run refuses. Probed by breaking that
skip deliberately against a throwaway copy of the client: `cannot run: …
already exists — refusing a clean:true codegen onto it`, 17 files before and
17 after.

**Concurrency proof.** Two runs launched together while
`git status --porcelain -- aii_frontend` was sampled in a tight loop — 203
samples across the window, both runs exit 0. The set of status lines never
moved off the baseline except for one line, `features/run-config/use-api-
keys.ts`, which is another agent's edit made at 20:43:57 during the window and
still present afterwards. No transient entry, and no sample anywhere mentions
`.regen-check`, `_hey-api` or any scratch name. No `hey-api-regen.*` directory
survives in `$TMPDIR`.

Re-probed after the move, all four still behave as when the rule was written:

| probe | result |
|---|---|
| pristine tree | exit 0, 17 files, ~0.9 s |
| hand edit inside `_hey-api/` | exit 1, names the added line |
| spec change, no regeneration | exit 1, names the new field |
| no `node_modules` | exit 1, `cannot run:` marker |

The cannot-run contract is unchanged and deliberately so: exit **1** with a
`cannot run:` line, which is what `test_every_pending_mechanism_still_passes.py`
detects and what every Python mechanism in this tree already does. A checker
that cannot run stays loud rather than green.

## The drift report does not pipe into its own truncation

**`sed … | head -40` under `pipefail` reports 141 on any diff long enough to
truncate.** `head` exits at its fortieth line and closes the read end while
`sed` still has bytes to write, so `sed` dies of SIGPIPE and `pipefail`
promotes 141 to the pipeline's status — the same shape that cost
`private-config-never-tracked` two ci-local reds. Here it was latent rather
than wrong: nothing reads that status, the script exits 1 on its own line
below, and the 40 printed lines are correct.

Measured in a throwaway clone by checking an older client out of history and
running the script against it:

| committed client | report | pipeline status |
|---|---|---|
| current | none, exit 0 | n/a |
| 1 revision behind | 11 lines | 0 |
| 7 revisions behind | 45 lines | **141** |
| 13 revisions behind | 45 lines | **141** |

The threshold is the pipe buffer, not the diff: in an isolated copy of the
pattern the producer survived 159 lines and died from 160 on.

The order is now `head -40 "$TMP/regen.diff" | sed …`. Both substitutions are
line-local, so the printed output is byte-identical — verified at 5, 40, 41,
200 and 5000 diff lines — and `head` reading a regular file leaves no producer
for the truncation to kill. The `sed`-first form is what a later `set -e`, or
any caller that reads the pipeline's status, would turn into a false red.
