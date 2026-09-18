# Every dependency-resolving Python install in a container build file names a constraint

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 1s | active |

## Why

The manifests declare floors (`httpx>=0.28.0`), the build files install
with a bare `uv pip install`, and `uv.lock` is dockerignored out of both
build contexts. So an image layer resolves newest-of-the-day at the moment
it rebuilds — and it rebuilds at cache-miss moments, which this repo
records as rare and surprising (the two-day deploy outage of 2026-08-14/15
began with a single `mathlib_warmup` miss). A version can reach production
that no local venv and no CI run ever exercised, with no commit deciding
it. The frontend half already does this correctly with
`bun install --frozen-lockfile`; this brings the Python side to parity.

The census of install lines has drifted at every re-measurement — six when
the rule was written, eight at its verification, nine today — which is why
the check enumerates the lines rather than asserting a count.

Two things made this worth mechanizing rather than asking an agent:

- The old rule's ledger read apply 16, fail 7, waived 7, wip 1. Seven
  waivers on one rule is the shape of a gate that fires on the wrong
  thing.
- The command it proposed, `git grep -nE 'uv (pip install|sync)'`, printed
  13 hits of which 5 were prose — comments discussing install behaviour —
  a 38% false-positive rate, re-derived by hand at commit time. It also
  never saw `Dockerfile.server:112`, a plain `pip install`.

## Mechanism

`check.py` parses the build file rather than grepping it, then asks each
simple command whether it resolves dependency versions and, if so,
whether anything constrains it.

| shape | mechanism |
|---|---|
| `RUN uv pip install ...` | RUN body, simple commands |
| `pip` / `pip3` / `python -m pip` | the same head set |
| install second in an `&&` chain | quote-aware shell split |
| install split across `\` | logical instruction join |
| install inside a heredoc | body attached to its RUN |
| install behind `--mount=...` | RUN flags stripped first |
| a comment discussing installs | dropped by the parser |
| `VAR=x uv pip install ...` | per-command env honoured |
| `ENV UV_CONSTRAINT` earlier | tracked per stage |
| `uv sync`, `poetry install` | exempt: lock-exact |
| `bun install`, `apt-get install` | not Python resolution |

A command is satisfied by `-c` / `--constraint`, `--no-deps`, `--frozen`,
`--require-hashes` or `--locked`, or by `UV_CONSTRAINT`,
`UV_BUILD_CONSTRAINT` or `PIP_CONSTRAINT` in scope. Stage scoping is real:
`ENV` is cleared at every `FROM`, so the same install line is clean in one
stage and a finding in the next.

Content comes from the index (`git show :<path>`), so an unstaged edit by
another agent in a shared checkout can neither cause nor hide a finding.
This is visible in the numbers below: the converter measured
`Dockerfile.pipeline` at lines 86/367/372 from the working tree, which
carries 135 unstaged inserted lines in this checkout, while the index —
what the commit would contain — puts the same three installs at 55/239/244.

`CONFIG` at the top of `check.py` holds every project-shaped knob: the
build-file name pattern, the install and exempt head sets, the satisfying
flags, the constraint variables and the DEBT set. `--emit-debt`
regenerates the DEBT literal.

## Stock

Measured against `/home/<user>/projects/research-monorepo` at HEAD `3f1060fa7`
and re-verified unchanged at `eaf82761c`. Population: `Dockerfile.base`,
`Dockerfile.pipeline`, `Dockerfile.server`. Whole-tree runtime
0.03-0.04 s over three runs.

Nine unconstrained installs, no prose among them:

```text
Dockerfile.pipeline:55    uv pip install --system -e aii_lib[...] ...
Dockerfile.pipeline:239   uv pip install --system -e aii_lib[...] ...
Dockerfile.pipeline:244   uv pip install --python=.claude/skills/...
Dockerfile.server:76      uv pip install --system -e aii_lib[...] ...
Dockerfile.server:112     pip install ... lean-interact==0.10.5
Dockerfile.server:154     uv pip install --python=/repo/.venv/...
Dockerfile.server:365     uv pip install --python=.claude/skills/...
Dockerfile.server:485     uv pip install --system -e aii_lib[...] ...
Dockerfile.server:515     uv pip install --python=.claude/skills/...
```

All nine ship as DEBT, so the hook is green today. The fix they are debt
for is the deploy-facing one the old rule's own delete-check names:
`uv export --frozen -o constraints.txt` in the builder stage, then
`UV_CONSTRAINT` on each install. That changes what the images resolve, so
it belongs in its own commit and its own redeploy.

DEBT is keyed on `(path, normalized command)`, not on the line, so an
entry survives the file growing or the install moving — the nine lines
reduce to eight entries, because two `--python=.claude/skills/...`
installs in `Dockerfile.server` normalize to the same command. EDITING a
debted install line changes its text, drops it out of the set and blocks
it, deliberately: touching an install line is the moment to give it the
constraint. The same command in a different build file also blocks.

## Fragility

| change | effect | guard |
|---|---|---|
| no build file tracked | population empty | exit 2 |
| build files, no Python installer anywhere | out of scope | exit 0 |
| installer mentioned, zero head matches | keys on nothing | exit 2 |
| some installs move to a `.sh` | partly blind | none |
| a new installer | not covered | add to CONFIG |
| a new way to constrain | fails closed | add to CONFIG |

The third guard is the important one: a switch to another installer, or
moving the install into a shell script the build only `COPY`s and runs,
would otherwise leave the gate green over nothing. It fires only when at
least one Dockerfile mentions `uv`, `pip`/`pip3`, `python`/`python3`,
`poetry` or `pipenv` (`CONFIG["installer_name_re"]`, kept in lockstep with
`install_head_res` / `exempt_head_res`) but the head regexes matched none
of them — that is real drift. A tree whose Dockerfiles never mention a
Python installer at all (a Node-only build doing `RUN npm ci`, say) is
simply out of scope for this check and passes with a one-line
"no Python installer" message instead. Either guard fires only on total
loss; a partial move is silent, and the fix available for it is to widen
the population to `docker/*.sh` and run the same shell splitter over them.

## Residue

Whether the constraint file actually derives from the lock is dropped.
The check proves a constraint is referenced, not that `constraints.txt`
came from `uv export --frozen`; proving that needs builder-stage
provenance and belongs in a build-time assertion.

Non-Python installers are dropped deliberately. `bun install`,
`apt-get install` and their siblings are out of scope because the
statement is about the Python side reaching the parity the frontend
already has.
