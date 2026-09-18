<!-- hook: repo-root-one-helper -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-grep
# Repo-root resolution in workspace package source goes through aii_lib.utils.paths.repo_root() — no hand-rolled parents[N] / .parent chains

## LANDED 2026-09-04

The door is `repo_root()` at `aii_lib/src/aii_lib/utils/paths.py:21-24`, and
it is now the only fixed hop count off `__file__` left in package source. The
command's whole-tree hit count went **11 -> 0**, which is what earns the
`--tree` form: the invariant holds over the whole codebase on every commit,
so a pre-existing violation surfaces instead of riding as an advisory.

The hazard is the one this repo's own splitting convention creates
(CLAUDE.md, "Splitting a module that got too big"): moving a file into a
`_foo/` sibling adds one directory level, every hop count in the moved file
then points one level short, and nothing says so. That is not hypothetical —
it had already happened, see below.

### The 11 sites, and what each became

Six resolved to the repo root and now call the door. The other five were
never repo-root resolution at all; they are package-relative, and they now
say so with the package's OWN location — at most one `.parent`, never a
count that a move can invalidate.

| site | was | now |
|---|---|---|
| _local.py:19 | .parent x5 | `repo_root()` |
| config.py:30 | .parent x4 | `repo_root()` |
| _cli/setup.py:319 | parents[4] | helper deleted |
| pipeline_config.py:134 | .parent x5 | `repo_root()` |
| db_backup_supervisor.py:21 | parents[3] | `repo_root()` |
| _remote/_common.py:37 | parents[4] | `repo_root()` |
| discovery.py:329 | parents[4] | root / "aii_lib" |
| executors/dataset.py:37 | .parent x4 | shared root |
| executors/evaluation.py:37 | .parent x4 | shared root |
| executors/experiment.py:37 | .parent x4 | shared root |
| executors/proof.py:37 | .parent x4 | shared root |

`_cli/setup.py`'s `_repo_root()` was a second in-package door; it is deleted
and its four call sites call `repo_root()` directly. The four executors each
spelled the SAME four-hop chain to reach the prompts tree, so they now share
one `WORKSPACE_TEMPLATE_ROOT` in `executors/base.py`, built from
`Path(aii_pipeline.__file__).parent` — the package's own location, which no
relocation of a submodule can move. `discovery.py` wants the `aii_lib`
package dir, one level BELOW the repo root, and now spells exactly that.

### Equivalence was measured, not argued

A probe recovered each site's expression by AST from `git show HEAD:<f>`
(not retyped), evaluated it with that module's real `__file__`, and compared
the Path against the post-change expression evaluated the same way. Then the
migrated modules were imported for real and their constants compared against
the expected paths.

| quantity | value |
|---|---|
| sites compared | 11 |
| byte-identical Paths | 10 |
| changed Paths | 1 |
| live-import checks | 11 |
| live-import mismatches | 0 |

### The one site whose value CHANGED — and why that is the point

`aii_runpod/.../deploy/_remote/_common.py` named its constant `_PKG_ROOT`
with a comment reading "Repo root as seen from this file
(`aii_runpod/src/aii_runpod/deploy/`)". That directory is the one the file
LEFT when `remote.py` was split into `_remote/` (`e94c06239`). The hop count
was never bumped, so the constant resolved to `<repo>/aii_runpod`, and:

- `<repo>/aii_runpod/.env` does not exist
- `<repo>/aii_runpod/aii_config` does not exist

Both use sites carry a cwd-relative fallback for an installed-package
layout, so both silently fell through to it — `Path(".env")` at
`_common.py:54`, `Path("aii_config")` at `_deploy_flow.py:248` and
`_redeploy.py:595`. Nothing failed: a deploy launched from the repo root
still found them by cwd. A deploy launched from anywhere else did not, which
is the exact cwd dependence `_repo_env_path`'s own docstring says this
constant exists to remove, and which `_redeploy.py` hits in Phase 3 — after
the fleet is already torn down. Routing it through the door restores the
documented behaviour and the constant is renamed `_REPO_ROOT`, matching what
it now holds. `test_redeploy_preflight.py`'s two `monkeypatch.setattr` sites
follow the rename; `_repo_env_path` stays in `_common.py`, so the patch
still bites.

This is the whole argument for a door in one file: the defect was invisible
because every reader of a hop count has to re-derive the depth by hand, and
the fallback made a wrong answer look like a working one.

### The regex is comment-guarded, and that was learned the hard way

`^[^#]*` in front of the alternation is the same guard
`rule-run-dir-reserved-names-one-door` uses, and it is here for a reason this
commit produced. The migration's whole value is the comments it leaves behind
saying what the code used to be — `_common.py` records that the constant was
`Path(__file__).resolve().parents[4]` and why that was wrong. Without the
guard the rule matched its OWN explanation and went red on the commit that
made it green: a door rule that forbids NAMING the anti-pattern would make
this repo's explain-yourself-in-prose habit unaffordable exactly where it pays
most.

The guard costs no enforcement. `^[^#]*` requires only that no `#` precede the
match ON THAT LINE, so a real chain with a trailing comment
(`X = Path(__file__).parents[4]  # note`) still matches, and a chain inside a
docstring — no `#` at all — still matches. Only text after a `#` is skipped,
and text after a `#` cannot resolve a path. Verified all four ways: the 11
HEAD sites are still 11 under the guarded form, the tree is still 0, a
trailing-comment chain is caught, and prose naming `parents[4]` is not.

### The pathspec is spelled `aii_server/*.py`, not `aii_server/**/*.py`

Same correction `rule-loguru-sink-single-source` and
`rule-wire-timestamp-via-helper` record, for the same reason. A git pathspec
without `:(glob)` magic matches with fnmatch and NO `FNM_PATHNAME`, so a
plain `*` already crosses `/` and reaches every depth, while `**/*.py`
demands a literal directory between the root and the file and silently drops
every TOP-LEVEL module. Measured on this tree it costs exactly the
`aii_server` root — 105 files against 108 — and the three it drops are
`aii_server.py`, `aii_server_cli.py` and `manage.py`, all process
entrypoints and all plausible places to resolve a repo root. The four
`*/src/` roots are unaffected, since their modules already sit a directory
down. Verified by planting: a `.parents[3]` chain at
`aii_server/_rr_probe.py` exits 0 under the `**` form and 1 under this one,
and the whole-tree count is 0 either way, so the widening costs nothing.

### Scope

Five packages' `src/` (plus `aii_server/`, which has no `src/` layer).
Excluded, by directory rather than by name: `**/tests/**`, `**/migrations/**`
and the door itself. `scripts/` is deliberately outside: a pre-commit hook
that imported `aii_lib` to find its own repo root would be a step backwards,
and those 10 sites are entry points that must run before anything is
importable. `claude_cred_manager` is excluded by design (it must
not import `aii_lib`) and has zero hits anyway.

The earlier body said "four divergent idioms measured" and an independent
verification corrected that to roughly 13 across source and scripts. Both
counts are retired: the enforced surface is 11 sites in package source, and
it is 0 today.

Delete-check: Yes — this WAS the deletion, and the rule now enforces the deleted
end-state rather than describing a backlog. The four executor copies became
one constant, `_cli/setup.py`'s private `_repo_root()` is gone, and every
remaining repo-root read is one call. What cannot be deleted is the last hop
count itself: `repo_root()` has to know how deep `paths.py` sits, so the
dimension collapses to exactly one line, which the command excludes by path.
