# A git dependency names an immutable rev: a release tag or a commit SHA, never a branch

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 1s | active |

## Why

`claude-agent-sdk` is declared as `git+...@main` in two manifests, and
`uv.lock` carries the entry derived from them. A branch ref is not a
version: two installs of the identical source tree can resolve different
code, with no commit deciding the change.

The independent verification of the old rule found the sharp edge, and it
is not the one the proposal named. An ordinary relock does NOT move the
SDK (`uv lock --dry-run` reports no changes; only `--upgrade` does). What
does move it is the image build: `uv.lock` is dockerignored out of both
build contexts and the images install with a plain `uv pip install`, so
every build re-resolves `@main` from the remote's HEAD. Two builds of one
repo SHA can ship different SDK versions, and the deployed image was
measured roughly 140 releases past the version the lock pins.

Two things made this worth mechanizing rather than asking an agent:

- The old rule's ledger read apply 24, fail 14, wip 7, and all seven WIP
  evidence lines were the same sentence rewritten — "pre-existing stock of
  exactly 2 branch-ref git deps ... this diff adds ZERO git deps". Seven
  agent turns spent re-deriving one grep.
- The command it proposed was inverted and could only ever pass.
  `rules-grep` follows grep's convention, so exit 1 means matches were
  found; the trailing `&& exit 1 || exit 0` read that backwards. Measured
  on the old text, a staged `git+...@main` gave exit 0 with the violation
  printed, and a clean manifest edit gave exit 1 with no output. Its
  pathspec also missed the root `pyproject.toml`, matching 6 of 7 tracked
  manifests.

## Mechanism

`check.py` parses each manifest with a real parser and asks the same
question of every git source it finds. Three parsers, never a line regex,
so a `git+` URL in a comment or a description string cannot become a
finding and a pin that moves lines cannot be missed.

| declaration | mechanism |
|---|---|
| `pkg @ git+...@ref` | tomllib; ref is the LAST `@` |
| optional-deps, PEP 735 groups | the same walk |
| `[tool.uv.sources]` | branch / rev / tag triage |
| `uv.lock` git source | tomllib, then query params |
| `package.json` git URL | json, four dep blocks |
| npm `github:` / `org/repo#ref` | shorthand forms |
| a git dep with no ref | flagged: default branch |

A ref is immutable when it is a 40-hex SHA or looks like a release tag;
a short denylist (main, master, dev, develop, staging, latest, head,
trunk) catches branch names a loose tag pattern would let through. The
ref is the FINAL `@` segment, so `git+ssh://git@host/x.git@main` reads
`main` rather than the userinfo.

Content comes from the index (`git show :<path>`), so an unstaged edit by
another agent in a shared checkout can neither cause nor hide a finding.
A path named on the command line that has no index entry is read from
disk, which lets a caller point the check at a file it has just written.

`CONFIG` at the top of `check.py` holds the three project-shaped knobs:
the manifest basenames that form the population, the branch denylist, and
the DEBT set. `--emit-debt` regenerates the DEBT literal.

## Stock

Measured against `/home/<user>/projects/research-monorepo` at HEAD `3f1060fa7`
and re-verified unchanged at `eaf82761c`. Population: 11 files — 7
`pyproject.toml`, `uv.lock`, 3 `package.json`. Whole-tree runtime
0.13-0.15 s over three runs; scoped to two manifests, 0.03 s.

Three findings, all one dependency, all shipped as DEBT:

```text
aii_lib/pyproject.toml:191      claude-agent-sdk pins 'main'
aii_pipeline/pyproject.toml:27  claude-agent-sdk pins 'main'
uv.lock:1125                    claude-agent-sdk source rev='main'
```

They are debt rather than findings because the fix is deploy-facing — it
changes which SDK the images install — so it belongs in a deliberate bump
commit, not in whatever commit next touches a manifest. With the DEBT set
shipped the hook exits 0 whole-tree today, and every other manifest is
gated from the first commit. DEBT is keyed on `(path, dependency name)`,
so a second bad dependency in an already-debted file still blocks, and
the same pin in a different manifest still blocks.

Removing an entry from DEBT is exactly the accepted fix: switch both
declarations to the registry release with a floor, or pin a rev and bump
it deliberately.

## Fragility

| change | effect | guard |
|---|---|---|
| manifests renamed away | population empty | exit 2 |
| a DEBT entry stops biting | hides a moved file | stale warning |
| a new manifest format | not covered | add to CONFIG |
| a manifest in a submodule | out of population | none |

The stale-DEBT warning is what makes a rotted exemption loud: a whole-tree
run prints every DEBT entry that suppressed nothing, because either the
pin was fixed (delete the entry) or the manifest moved and the exemption
is now hiding a file the check no longer sees. A moved manifest also fails
closed — the exemption stops matching and the pin blocks.

The vacuity guard covers total loss only. A pixi or poetry git table in a
file named something else is simply not in the population; add it to
`CONFIG["manifests"]`. No submodule of this repo currently carries a
manifest, so the population is the outer index and `--recurse-submodules`
is not used.

## Residue

The semantic half is dropped: whether tracking `main` is deliberate here,
or whether the declaration should move to the registry release. That is
the owner call the old rule body asked for, and no program can take it.
What survives is the whole enforceable statement — no branch ref, in any
manifest, ever.

Two narrower things the check deliberately does not do. It accepts a tag
as immutable by convention and does not verify that the remote's tag has
not been moved, which would need a network call. And it judges manifests
only: a `pip install git+...` inside a script or a build file is a
different population, covered for constraints by
`image-installs-lock-constrained` rather than for refs here.
