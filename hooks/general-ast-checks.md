# general-ast-checks

Not a `general/hooks/<name>/README.md` folder — this is the dispatcher command
wired in `general/lefthook.yml` that runs a batch of AST-based hooks in one
pass. Documented here from its inline comment and the README's "The hook
contract" section, since the dispatcher itself has no dedicated folder (it
borrows another hook's folder purely to derive one internal path variable).

## What it does

One dispatcher process (`lib/amg_hooks/ast_dispatch.py`, engine
`lib/amg_hooks/astcheck.py`) discovers every `dispatch.py`-owned hook folder
under `general/hooks/` and judges them all in a single pass over the staged
index — one `git` read, one AST parse cache, shared across every check
instead of paid once per hook. Findings print as `hook: path:line: msg` and
are re-attributed to the owning hook by name. A `dispatch.py` hook declares a
`SCOPE` (file/tree/relation), trigger `GLOBS`, optional `EXCLUDES`, and a
`run(svc)` function; it is otherwise governed by the same checker contract as
a standalone `check.py`/`check.sh` hook (exit 0 clean, 1 findings, 2 cannot
run — any nonzero blocks the commit).

Command (verbatim from `general/lefthook.yml`):

```
'{amg_hooks}/lib/amg_hooks/amg-hooks-env {amg_hooks}/general/hooks/tracked-script-carries-no-hook-bypass commit -- env -u RULE_DIR python3 {amg_hooks}/lib/amg_hooks/ast_dispatch.py {amg_hooks}/general/hooks {staged_files}'
```

## The checks it batches

Each of the following is its own hook folder with its own `README.md` under
`general/hooks/`, each with its own statement, mechanism and tests — they
just fire through this one dispatcher command rather than a separate
`lefthook.yml` entry each. Statements, verbatim from each hook's own README:

- **comment-drift** — Prose that names a path, a line or a symbol names one that exists
- **discovery-never-fails-open** — A guard's discovery step never converts its own failure into a clean result
- **endpoint-urls-once** — A third-party endpoint host is declared in one module per environment
- **failover-walk-budget** — Every multi-provider failover walk is bounded by one wall-clock budget: a monotonic deadline, each attempt clipped to what remains, and a minimum-attempt floor
- **gate-can-fire** — A hook command's gate can actually fire
- **keyword-only-past-five** — A Python def takes at most five positional parameters — the rest go behind a bare `*` so callers name them
- **loguru-is-the-logger** — Logging is loguru with the house format — `import logging` is not the logger here
- **md-table-width** — Markdown table rows added by a commit stay under 70 characters
- **neutral-register** — Added lines carry none of the offense-register words the global CLAUDE.md bans — neutral professional engineering vocabulary is the house register, in files too
- **no-actions-invocations** — No script or package invokes GitHub Actions workflows — builds, CI and deploys are 100% local
- **no-runtime-self-skip** — A test never decides its own applicability at runtime
- **no-shell-true** — No code-execution or deserialization sink takes a value this repo did not write
- **no-silent-except** — An except block logs, re-raises, or explains — never swallows silently
- **no-sys-path-mutation** — No mutation of `sys.path` — imports resolve through the package layout, not through a patched search path
- **pathlib-over-os-path** — File-system paths use `pathlib.Path` — not `os.path.join` / `exists` / `dirname` / `basename`
- **state-file-replaced-atomically** — A state file another process polls is replaced by rename, never truncated and rewritten where a reader can catch it half-written
- **sweep-population-floor** — A guard whose verdict is computed over a discovered population proves it was non-empty
- **test-genre-declared** — A test module declares exactly one genre, as a registered pytest marker
- **test-seam-private-patch** — A newly added `monkeypatch.setattr` does not name a private seam
- **tests-reap-their-children** — A test that starts a `subprocess.Popen` must reap it on every path
- **tmux-kill-server-names-its-socket** — No tracked script runs `tmux kill-server` without naming a private socket
- **tmux-launch-one-door** — tmux sessions are started only through one wrapper function, never a raw subprocess call elsewhere
- **toolchain-pinned** — Every host binary a hook command can invoke is pinned in the consumer's installer
- **tracked-script-carries-no-hook-bypass** — No tracked `*.sh` or `*.py` ships a git-hook bypass or a sweeping `git add`
- **watcher-log-stamps-utc** — Every timestamp a repo-owned shell script writes carries an explicit UTC marker

Two folders under `general/hooks/` are deliberately not on this list:
`shipped-migration-immutable` has its own separate `run:` line in
`general/lefthook.yml` (a standalone `check.py`, not a `dispatch.py`), so it
is documented as its own lane, not as a dispatcher member. `commit-lane-fixtures`
holds amg-hooks' own meta-test runner ("This folder is the lane half. It is
not a hook") and never fires as a command in a consumer's gate at all.
