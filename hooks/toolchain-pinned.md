# Every host binary a hook command can invoke is pinned in the consumer's installer

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 1s | debt |

## Why

Local hooks are bypassable — `--no-verify`, a web-UI edit, an un-installed
clone — so CI re-runs every gate whole-tree. `COMMIT_CHECKLIST.md` item 10 is
the parity clause that keeps that possible: *if this commit adds or changes a
rule whose command shells out to a host binary, that binary must ALSO be added
— pinned — to `scripts/ci/install-hook-tools.sh`, or the CI job fails on the
missing tool.*

Nothing checked it. A former sibling, `hook-toolchain-lists-agree` (retired
2026-09-16 with the CI watcher whose assert list it mirrored), kept that
14-binary assert list and the installer's provision list in parity with
**each other** — two hand-written literals compared to one another. Neither
was derived from what the gates actually invoke, so a command that started
shelling out to a new binary would drift away from both lists without either
noticing. This hook supplies the derivation.

Item 10 was one of two clauses the agent-verified checklist ack never covered
across 828 applications and 321 blocks. Of the eight verdict lines the ledger
kept, five are the same roll-call string repeated over one diff-sha family, and
only one is a genuine long-form ten-item review — so the gate that was supposed
to hold this clause was mostly not holding anything.

## Mechanism

`check.py` reads every `run:` line in every `<set>/lefthook.yml` under the
hooks repo, resolves each to the files it delegates to, tokenizes those, and
compares the binaries against the installer's own pinned set.

**Following the delegation is the whole job.** A migrated run line reads

    {amg_hooks}/lib/amg_hooks/amg-hooks-env {amg_hooks}/<set>/hooks/<x> commit -- bash .../<x>/run.sh

so a checker that tokenizes only the run string finds `amg-hooks-env` and `bash` and
nothing else. Measured 2026-09-14: 244 commands resolve to 487 delegate scripts.

| failure mode | mechanism |
|---|---|
| binary named in the run line | shlex, command position |
| binary inside `run.sh` | `{amg_hooks}` / `$AMG_HOOKS` / `$RULE_DIR` |
| binary inside a Python script | AST over subprocess argv[0] |
| a nested `scripts/*.sh` | transitive delegate queue |
| quoted ERE `'a\|b'` split in two | shlex respects the quotes |
| prose in a docstring read as shell | Python gets the AST pass |
| a heredoc body read as commands | dropped between tag and tag |
| a `case` label read as a command | label stripped inside `case` |
| `.venv/bin/x`, `node_modules/.bin/x` | path-shaped words dropped |
| a shell function or variable | defined-name scan of the script |

Four carve-outs, each named in the run summary and listed by `--explain`, never
a silent allowlist:

- **out-of-band gate** — a command whose text tests `RULES_APP_URL`,
  `RULES_HEAVY` or `AMG_HOOKS_APP_URL` and branches on it cannot run in any lane the
  consumer drives, so a binary past that guard is not a parity gap. This keeps
  `node` off the list for the two `flow-*` commands. The pattern requires the
  gate SHAPE, not the name: matching the name alone carved out 84 of 208
  commands, because nearly every run line delegates through `lib/amg_hooks/amg-hooks-env`,
  whose body mentions the variable while assigning it.
- **`command -v` guard** — item 10's own escape hatch. A gate that cannot run
  headless exits 2 rather than certify a sweep it could not make, so a guarded
  binary is provisioned or skipped by design. Clears `systemd-analyze`.
- **sentinel-provided** — the installer pins one console script per multi-script
  package as a presence sentinel, and `uv tool install` exposes the siblings.
- **set selection** — the consumer names its sets with `extends:` in its own
  `lefthook.yml`; a set it does not extend is another repo's installer's
  problem. This replaces the rule engine's `.amg-rules.yaml` `sets:` list.

One deliberate host dependency, and it is the last filter: shell is not soundly
parseable at this level (a script can embed an awk program whose shell quoting
opens and closes mid-body), so a candidate is reported only when
`shutil.which` resolves it to a real program on the host running the gate —
which is where the check has to work at all. It fails in the safe direction: on
a host missing the tool the check under-reports rather than blocking a commit
over a word that was never a command. Ten words are dropped that way today, six
of them awk locals from one script.

The installer is read from the **consumer's index** (`git show :<path>`) using
regexes originally matched to the now-retired `hook-toolchain-lists-agree`'s
own two extraction regexes, so the two checks would not disagree about what
"pinned" means. The hook-set files are read from
**disk**: they live in a submodule of the consumer, whose outer index holds a
gitlink and not their blobs, so `git show :` cannot reach them. That is the one
working-tree read here and it is unavoidable, not an oversight.

`--explain` lists every carve-out with its reason. `--emit-debt` prints today's
findings in the CONFIG `debt` key's form.

## Stock

Re-measured 2026-09-14 against `/home/<user>/projects/research-monorepo`:
**244 commands over 2 sets, 487 delegate scripts followed, 5 not scanned,
748 embedded lines skipped, 16 candidates carved out, 0 findings.** Whole-tree
runtime **0.88–1.05 s** over three runs.

**Two sets, not four, and that is the fix landing.** The consumer's
`lefthook.yml` now names its sets with `extends:` (its lines 6-8, `general` and
`research-monorepo`), so the set-selection carve-out drops `notes-repo` and `self` and the
one finding this section used to record is gone:

    notes-repo/lefthook.yml:14: one-background-process invokes 'crontab'

`crontab` is the notes-repo installer's problem now, exactly as predicted. Two
leftovers the owner still owns, both deliberately untouched by this docs pass:
the `notes-repo/one-background-process/crontab` entry in the CONFIG `debt` key is
now vacuous — it excludes a finding that can no longer be produced — and the
header table above still reads `status: debt`, which a run of `--emit-debt` no
longer supports. Emptying the debt set and flipping the status cell (with the
`fail_text` in `general/lefthook.yml` that points here) is a code change, not a
documentation one.

An earlier measurement read **260 commands over 4 sets, 449 delegate scripts,
771 embedded lines skipped, 15 carved out, 1 finding**, at `e51e1f85a` with the
hook sets at the migration snapshot. It moved three times during that session
(205 → 218 → 260 commands) because the hooks repo is regenerated with each batch's fragments
spliced in. The shape of the answer did not: one finding, in the set the
consumer will not extend. Re-measure after the last batch lands; what must not
change is that the count never DROPS between two runs over the same tree, which
would mean the run-line parser stopped seeing commands.

## Fragility

| refactor | effect | guard |
|---|---|---|
| run lines stop delegating | reads run lines only | scripts floor |
| lefthook.yml indent moves | no commands parsed | commands floor |
| installer changes shape | nothing looks pinned | min-tools floor |
| the hook folder changes depth | wrong root | `AMG_HOOKS_ROOT` override |
| a set folder is added | scanned automatically | discovery, no list |
| installer path moves | check would flag all | `skipped:` + exit 0 |
| a new binary is added | flagged unless pinned | the point of it |

The first three floors are the ones that matter: each turns a green-on-nothing
into an exit 2. Three earlier versions of this program were green while looking
at the wrong text, and every one of those is a test in the bites file.

Two more, which are judgement rather than mechanism. The `which` filter means a
host missing a tool under-reports rather than over-blocks — the safe direction,
but it does make the answer host-dependent. And the folder-name-is-the-command
-name convention resolves `$RULE_DIR`; `tools/layout_lint.py` already enforces
it, so a divergence fails there first.

## Residue

Not attempted, deliberately:

- **`.mjs` / `.js` delegates.** Five files are counted and not scanned. A
  JavaScript extraction is a fourth parser for two live scripts, and both sit
  behind the out-of-band gate anyway.
- **A dynamic argv[0].** A Python `subprocess.run(cmd_from_config)` is
  unresolvable; it is left alone rather than guessed at.
- **The other clauses of item 10.** "A gate that cannot run headless exits 2"
  is `gate-steps-resolve`'s; `timeout-minutes` / `permissions` /
  `persist-credentials` on workflow jobs is `actionlint`'s. Neither is
  re-implemented here.
- **Whether the pin is the RIGHT version.** This asks only whether the binary is
  provisioned at all.
